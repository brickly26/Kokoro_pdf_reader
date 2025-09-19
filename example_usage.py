#!/usr/bin/env python3
"""
Example usage of the Academic PDF Processing Pipeline

This script demonstrates how to use the PDF processing pipeline
programmatically with different configurations.
"""

import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from pdf_pipeline import PDFProcessor, ProcessingConfig


def basic_example():
    """Basic usage example"""
    print("=== Basic Example ===")
    
    # Create default configuration
    config = ProcessingConfig(
        output_dir="output_basic",
        verbose=True
    )
    
    # Initialize processor
    processor = PDFProcessor(config)
    
    # Process a PDF (replace with your PDF path)
    pdf_path = "path/to/your/document.pdf"  # Update this path
    
    try:
        results = processor.process_pdf(pdf_path)
        
        # Print summary
        summary = processor.get_summary()
        print("Extracted content:")
        for content_type, count in summary.items():
            print(f"  {content_type}: {count}")
        
        print(f"Processing completed in {results['metadata']['processing_time']:.2f} seconds")
        
    except FileNotFoundError:
        print(f"PDF file not found: {pdf_path}")
        print("Please update the pdf_path variable with a valid PDF file")


def advanced_example():
    """Advanced configuration example"""
    print("\\n=== Advanced Example ===")
    
    # Create custom configuration
    config = ProcessingConfig(
        output_dir="output_advanced",
        
        # Layout detection settings
        use_layout_detection=True,
        layout_model="PubLayNet",
        layout_confidence_threshold=0.8,
        
        # Table extraction settings
        table_extraction_enabled=True,
        table_detection_method="both",  # Use both Camelot and Tabula
        table_accuracy_threshold=75.0,
        
        # Image settings
        image_extraction_enabled=True,
        image_dpi=200,  # Higher resolution
        min_image_size=(100, 100),
        
        # Formula detection
        formula_detection_enabled=True,
        
        # OCR settings
        ocr_enabled=True,
        ocr_engine="tesseract",
        ocr_languages=["eng"],
        ocr_fallback_threshold=0.2,  # Use OCR if less than 20% text extractable
        
        # Output settings
        create_main_text=True,
        create_manifest=True,
        exclude_headers_footers=True,  # Cleaner main text
        
        # Performance settings
        parallel_processing=True,
        verbose=True
    )
    
    processor = PDFProcessor(config)
    
    pdf_path = "path/to/your/academic_paper.pdf"  # Update this path
    
    try:
        results = processor.process_pdf(pdf_path)
        
        print("Processing results:")
        print(f"  Total pages: {results['metadata']['total_pages']}")
        print(f"  Processing time: {results['metadata']['processing_time']:.2f}s")
        
        # Detailed summary
        content = results['content']
        print("\\nContent breakdown:")
        for content_type, items in content.items():
            if isinstance(items, list) and len(items) > 0:
                print(f"  {content_type}: {len(items)}")
                
                # Show first item details for some types
                if content_type in ['tables', 'formulas'] and len(items) > 0:
                    first_item = items[0]
                    if content_type == 'tables':
                        print(f"    First table: {first_item.get('rows', 0)} rows, "
                              f"{first_item.get('columns', 0)} columns, "
                              f"accuracy: {first_item.get('accuracy', 0):.1f}%")
                    elif content_type == 'formulas':
                        print(f"    First formula: '{first_item.get('text', '')[:50]}...' "
                              f"(score: {first_item.get('math_score', 0)})")
        
    except FileNotFoundError:
        print(f"PDF file not found: {pdf_path}")
        print("Please update the pdf_path variable with a valid PDF file")


def text_only_example():
    """Example for extracting only text content"""
    print("\\n=== Text-Only Example ===")
    
    config = ProcessingConfig(
        output_dir="output_text_only",
        
        # Disable all artifact generation
        save_images=False,
        save_tables=False,
        image_extraction_enabled=False,
        table_extraction_enabled=False,
        formula_detection_enabled=False,
        
        # Focus on text extraction
        create_main_text=True,
        create_manifest=True,
        
        # Clean text output
        exclude_headers_footers=True,
        exclude_page_numbers=True,
        
        verbose=True
    )
    
    processor = PDFProcessor(config)
    
    pdf_path = "path/to/your/document.pdf"  # Update this path
    
    try:
        results = processor.process_pdf(pdf_path)
        
        # Count text content
        text_blocks = results['content']['text_blocks']
        total_words = sum(len(block.get('text', '').split()) for block in text_blocks)
        
        print(f"Extracted {len(text_blocks)} text blocks")
        print(f"Total words: {total_words}")
        print("Main text saved to: output_text_only/text/main_text.txt")
        
    except FileNotFoundError:
        print(f"PDF file not found: {pdf_path}")
        print("Please update the pdf_path variable with a valid PDF file")


def configuration_file_example():
    """Example using configuration file"""
    print("\\n=== Configuration File Example ===")
    
    # Create a sample configuration
    config_dict = {
        "output_dir": "output_from_config",
        "use_layout_detection": True,
        "layout_confidence_threshold": 0.75,
        "table_extraction_enabled": True,
        "table_detection_method": "camelot",
        "image_extraction_enabled": True,
        "formula_detection_enabled": True,
        "ocr_enabled": True,
        "create_main_text": True,
        "verbose": True
    }
    
    # Save configuration to file
    import json
    config_path = "sample_config.json"
    with open(config_path, 'w') as f:
        json.dump(config_dict, f, indent=2)
    
    print(f"Created sample configuration: {config_path}")
    
    # Load configuration from file
    config = ProcessingConfig.load(config_path)
    
    processor = PDFProcessor(config)
    print("Configuration loaded successfully")
    print("You can now use this configuration with:")
    print(f"  python pdf_processor_cli.py your_file.pdf --config {config_path}")


def main():
    """Run all examples"""
    print("Academic PDF Processing Pipeline - Examples")
    print("=" * 50)
    
    # Check if we have the required modules
    try:
        from pdf_pipeline import PDFProcessor, ProcessingConfig
    except ImportError as e:
        print(f"Error: Could not import PDF pipeline: {e}")
        print("Make sure to install dependencies: pip install -r requirements.txt")
        return
    
    # Run examples
    basic_example()
    advanced_example()
    text_only_example()
    configuration_file_example()
    
    print("\\n" + "=" * 50)
    print("Examples completed!")
    print("\\nTo use the command-line interface:")
    print("  python pdf_processor_cli.py --help")
    print("\\nTo check dependencies:")
    print("  python pdf_processor_cli.py --list-dependencies")


if __name__ == "__main__":
    main()
