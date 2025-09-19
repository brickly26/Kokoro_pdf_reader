#!/usr/bin/env python3
"""
Command-line interface for the Academic PDF Processing Pipeline

A comprehensive tool for extracting and categorizing content from academic PDFs.
Supports layout detection, table extraction, image processing, formula detection,
and more with configurable options and graceful degradation.
"""

import argparse
import sys
import json
import logging
from pathlib import Path
from typing import Optional

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

try:
    from pdf_pipeline import PDFProcessor, ProcessingConfig
except ImportError as e:
    print(f"Error importing PDF pipeline: {e}")
    print("Make sure all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)


def setup_logging(level: str = "INFO"):
    """Setup logging configuration"""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser"""
    parser = argparse.ArgumentParser(
        description="Academic PDF Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic processing
  python pdf_processor_cli.py input.pdf

  # Custom output directory
  python pdf_processor_cli.py input.pdf -o /path/to/output

  # Disable table extraction
  python pdf_processor_cli.py input.pdf --no-tables

  # Use OCR with custom confidence threshold
  python pdf_processor_cli.py input.pdf --ocr --layout-confidence 0.8

  # Generate only main text (no artifacts)
  python pdf_processor_cli.py input.pdf --text-only

  # Use custom configuration file
  python pdf_processor_cli.py input.pdf --config config.json

  # Verbose output with debugging
  python pdf_processor_cli.py input.pdf -v --debug
        """
    )
    
    # Input/output arguments
    parser.add_argument(
        "pdf_file",
        nargs="?",  # Make optional for utility commands
        help="Path to the PDF file to process"
    )
    
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for processed files (default: output)"
    )
    
    parser.add_argument(
        "--config",
        help="Path to JSON configuration file"
    )
    
    # Processing options
    processing_group = parser.add_argument_group("Processing Options")
    
    processing_group.add_argument(
        "--no-layout",
        action="store_true",
        help="Disable layout detection"
    )
    
    processing_group.add_argument(
        "--no-images",
        action="store_true",
        help="Disable image extraction"
    )
    
    processing_group.add_argument(
        "--no-tables",
        action="store_true",
        help="Disable table extraction"
    )
    
    processing_group.add_argument(
        "--no-formulas",
        action="store_true",
        help="Disable formula detection"
    )
    
    processing_group.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback"
    )
    
    processing_group.add_argument(
        "--text-only",
        action="store_true",
        help="Generate only main text file (disables artifact extraction)"
    )
    
    # OCR options
    ocr_group = parser.add_argument_group("OCR Options")
    
    ocr_group.add_argument(
        "--ocr",
        action="store_true",
        help="Force OCR processing even if text is extractable"
    )
    
    ocr_group.add_argument(
        "--ocr-engine",
        choices=["tesseract", "easyocr"],
        default="tesseract",
        help="OCR engine to use (default: tesseract)"
    )
    
    ocr_group.add_argument(
        "--ocr-languages",
        nargs="+",
        default=["eng"],
        help="OCR languages (default: eng)"
    )
    
    # Layout detection options
    layout_group = parser.add_argument_group("Layout Detection Options")
    
    layout_group.add_argument(
        "--layout-model",
        choices=["PubLayNet", "TableBank"],
        default="PubLayNet",
        help="Layout detection model (default: PubLayNet)"
    )
    
    layout_group.add_argument(
        "--layout-confidence",
        type=float,
        default=0.7,
        help="Layout detection confidence threshold (default: 0.7)"
    )
    
    # Table extraction options
    table_group = parser.add_argument_group("Table Extraction Options")
    
    table_group.add_argument(
        "--table-method",
        choices=["camelot", "tabula", "both"],
        default="camelot",
        help="Table extraction method (default: camelot)"
    )
    
    table_group.add_argument(
        "--table-flavor",
        choices=["lattice", "stream", "both"],
        default="lattice",
        help="Camelot table extraction flavor (default: lattice)"
    )
    
    table_group.add_argument(
        "--table-accuracy",
        type=float,
        default=80.0,
        help="Minimum table accuracy threshold (default: 80.0)"
    )
    
    # Image options
    image_group = parser.add_argument_group("Image Options")
    
    image_group.add_argument(
        "--image-dpi",
        type=int,
        default=150,
        help="DPI for extracted images (default: 150)"
    )
    
    image_group.add_argument(
        "--min-image-size",
        nargs=2,
        type=int,
        default=[50, 50],
        metavar=("WIDTH", "HEIGHT"),
        help="Minimum image size in pixels (default: 50 50)"
    )
    
    # Output options
    output_group = parser.add_argument_group("Output Options")
    
    output_group.add_argument(
        "--no-manifest",
        action="store_true",
        help="Don't generate JSON manifest"
    )
    
    output_group.add_argument(
        "--no-main-text",
        action="store_true",
        help="Don't generate main text file"
    )
    
    output_group.add_argument(
        "--include-headers-footers",
        action="store_true",
        help="Include headers and footers in main text"
    )
    
    output_group.add_argument(
        "--include-page-numbers",
        action="store_true",
        help="Include page numbers in main text"
    )
    
    # Logging options
    logging_group = parser.add_argument_group("Logging Options")
    
    logging_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    logging_group.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output and save debug files"
    )
    
    logging_group.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set specific log level"
    )
    
    # Utility options
    utility_group = parser.add_argument_group("Utility Options")
    
    utility_group.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate PDF structure, don't process"
    )
    
    utility_group.add_argument(
        "--estimate-complexity",
        action="store_true",
        help="Estimate processing complexity and exit"
    )
    
    utility_group.add_argument(
        "--list-dependencies",
        action="store_true",
        help="List available/missing dependencies and exit"
    )
    
    return parser


def load_config_file(config_path: str) -> ProcessingConfig:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        return ProcessingConfig.from_dict(config_dict)
    except Exception as e:
        print(f"Error loading config file {config_path}: {e}")
        sys.exit(1)


def create_config_from_args(args) -> ProcessingConfig:
    """Create ProcessingConfig from command-line arguments"""
    config = ProcessingConfig()
    
    # Basic settings
    config.output_dir = args.output
    config.verbose = args.verbose or args.debug
    config.debug = args.debug
    
    # Processing options
    config.use_layout_detection = not args.no_layout
    config.image_extraction_enabled = not args.no_images
    config.table_extraction_enabled = not args.no_tables
    config.formula_detection_enabled = not args.no_formulas
    config.ocr_enabled = not args.no_ocr
    
    # Text-only mode
    if args.text_only:
        config.save_images = False
        config.save_tables = False
        config.image_extraction_enabled = False
        config.table_extraction_enabled = False
    
    # OCR settings
    if args.ocr:
        config.ocr_fallback_threshold = 1.0  # Force OCR
    config.ocr_engine = args.ocr_engine
    config.ocr_languages = args.ocr_languages
    
    # Layout detection
    config.layout_model = args.layout_model
    config.layout_confidence_threshold = args.layout_confidence
    
    # Table extraction
    config.table_detection_method = args.table_method
    config.camelot_flavor = args.table_flavor
    config.table_accuracy_threshold = args.table_accuracy
    
    # Image settings
    config.image_dpi = args.image_dpi
    config.min_image_size = tuple(args.min_image_size)
    
    # Output settings
    config.create_manifest = not args.no_manifest
    config.create_main_text = not args.no_main_text
    config.exclude_headers_footers = not args.include_headers_footers
    config.exclude_page_numbers = not args.include_page_numbers
    
    return config


def check_dependencies():
    """Check and report on available dependencies"""
    dependencies = {
        "Core": {
            "PyMuPDF": ("fitz", "Required for PDF processing"),
            "Pillow": ("PIL", "Required for image processing"),
            "NumPy": ("numpy", "Required for array operations"),
        },
        "Layout Detection": {
            "layoutparser": ("layoutparser", "Layout detection with PubLayNet"),
            "detectron2": ("detectron2", "Backend for layoutparser"),
            "torch": ("torch", "Required for detectron2"),
            "torchvision": ("torchvision", "Required for detectron2"),
        },
        "Table Extraction": {
            "camelot-py": ("camelot", "Table extraction"),
            "tabula-py": ("tabula", "Alternative table extraction"),
            "pandas": ("pandas", "Data processing"),
            "opencv-python": ("cv2", "Image processing for Camelot"),
        },
        "OCR": {
            "pytesseract": ("pytesseract", "Tesseract OCR"),
            "easyocr": ("easyocr", "Alternative OCR engine"),
        },
        "Mathematical": {
            "sympy": ("sympy", "Mathematical symbol processing"),
            "scipy": ("scipy", "Scientific computing"),
        }
    }
    
    print("Dependency Status:")
    print("=" * 50)
    
    for category, deps in dependencies.items():
        print(f"\\n{category}:")
        for name, (module, description) in deps.items():
            try:
                __import__(module)
                status = "✓ Available"
            except ImportError:
                status = "✗ Missing"
            
            print(f"  {name:<20} {status:<12} {description}")
    
    print("\\nNote: Some dependencies are optional. The pipeline will")
    print("gracefully degrade functionality if dependencies are missing.")


def validate_pdf(pdf_path: str):
    """Validate PDF structure"""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        
        from pdf_pipeline.utils.pdf_utils import PDFUtils
        validation = PDFUtils.validate_pdf_structure(doc)
        
        print("PDF Validation Results:")
        print("=" * 30)
        print(f"Valid: {validation['is_valid']}")
        print(f"Pages: {validation['metadata']['page_count']}")
        print(f"Encrypted: {validation['metadata']['is_encrypted']}")
        
        if validation['issues']:
            print("\\nIssues:")
            for issue in validation['issues']:
                print(f"  - {issue}")
        
        if validation['warnings']:
            print("\\nWarnings:")
            for warning in validation['warnings']:
                print(f"  - {warning}")
        
        doc.close()
        
    except Exception as e:
        print(f"Validation failed: {e}")
        sys.exit(1)


def estimate_complexity(pdf_path: str):
    """Estimate processing complexity"""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        
        from pdf_pipeline.utils.pdf_utils import PDFUtils
        complexity = PDFUtils.estimate_processing_complexity(doc)
        
        print("Processing Complexity Estimate:")
        print("=" * 35)
        print(f"Overall Score: {complexity['overall_score']}/100")
        
        print("\\nFactors:")
        for factor, value in complexity['factors'].items():
            if isinstance(value, float):
                print(f"  {factor.replace('_', ' ').title()}: {value:.2f}")
            else:
                print(f"  {factor.replace('_', ' ').title()}: {value}")
        
        if complexity['recommendations']:
            print("\\nRecommendations:")
            for rec in complexity['recommendations']:
                print(f"  - {rec}")
        
        doc.close()
        
    except Exception as e:
        print(f"Complexity estimation failed: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    if args.log_level:
        log_level = args.log_level
    elif args.debug:
        log_level = "DEBUG"
    elif args.verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"
    
    setup_logging(log_level)
    
    # Handle utility options
    if args.list_dependencies:
        check_dependencies()
        return
    
    # Check if PDF file is required
    if not args.pdf_file:
        if args.validate_only or args.estimate_complexity:
            print("Error: PDF file is required for validation and complexity estimation")
            sys.exit(1)
        else:
            print("Error: PDF file is required")
            parser.print_help()
            sys.exit(1)
    
    # Validate PDF file exists
    pdf_path = Path(args.pdf_file)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    
    # Handle validation and complexity estimation
    if args.validate_only:
        validate_pdf(str(pdf_path))
        return
    
    if args.estimate_complexity:
        estimate_complexity(str(pdf_path))
        return
    
    # Create configuration
    if args.config:
        config = load_config_file(args.config)
        # Override with command-line arguments
        config.output_dir = args.output
        if args.verbose or args.debug:
            config.verbose = True
        if args.debug:
            config.debug = True
    else:
        config = create_config_from_args(args)
    
    # Create output directory
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing PDF: {pdf_path}")
    print(f"Output directory: {output_dir}")
    
    try:
        # Initialize processor
        processor = PDFProcessor(config)
        
        # Process PDF
        results = processor.process_pdf(str(pdf_path))
        
        # Print summary
        print("\\nProcessing completed successfully!")
        print("=" * 40)
        
        summary = processor.get_summary()
        for content_type, count in summary.items():
            if count > 0:
                print(f"{content_type.replace('_', ' ').title()}: {count}")
        
        processing_time = results['metadata'].get('processing_time', 0)
        print(f"\\nProcessing time: {processing_time:.2f} seconds")
        
        print(f"\\nResults saved to: {output_dir}")
        print("Main files:")
        print(f"  - Manifest: {output_dir}/manifest.json")
        if config.create_main_text:
            print(f"  - Main text: {output_dir}/text/main_text.txt")
        print(f"  - Summary: {output_dir}/reports/summary.txt")
        
    except KeyboardInterrupt:
        print("\\nProcessing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.exception("Processing failed")
        print(f"\\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
