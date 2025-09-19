#!/usr/bin/env python3
"""
Test script for the Academic PDF Processing Pipeline

This script validates that the pipeline components are working correctly
and can import all necessary modules.
"""

import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

def test_imports():
    """Test that all pipeline components can be imported"""
    print("Testing imports...")
    
    try:
        from pdf_pipeline import PDFProcessor, ProcessingConfig
        print("✓ Main pipeline components imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import main components: {e}")
        return False
    
    try:
        from pdf_pipeline.extractors import (
            LayoutDetector, ImageExtractor, TableExtractor,
            TextClassifier, FormulaDetector, CaptionMatcher, OCRProcessor
        )
        print("✓ All extractors imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import extractors: {e}")
        return False
    
    try:
        from pdf_pipeline.utils import OutputManager, PDFUtils
        print("✓ Utility modules imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import utilities: {e}")
        return False
    
    return True


def test_configuration():
    """Test configuration creation and validation"""
    print("\\nTesting configuration...")
    
    try:
        from pdf_pipeline import ProcessingConfig
        
        # Test default configuration
        config = ProcessingConfig()
        print("✓ Default configuration created")
        
        # Test custom configuration
        custom_config = ProcessingConfig(
            output_dir="test_output",
            layout_confidence_threshold=0.8,
            table_accuracy_threshold=75.0
        )
        print("✓ Custom configuration created")
        
        # Test configuration serialization
        config_dict = custom_config.to_dict()
        loaded_config = ProcessingConfig.from_dict(config_dict)
        print("✓ Configuration serialization works")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def test_dependencies():
    """Test availability of optional dependencies"""
    print("\\nTesting dependencies...")
    
    dependencies = {
        "PyMuPDF": "fitz",
        "PIL": "PIL",
        "numpy": "numpy",
        "pandas": "pandas",
        "layoutparser": "layoutparser",
        "camelot": "camelot", 
        "pytesseract": "pytesseract",
        "cv2": "cv2"
    }
    
    available = []
    missing = []
    
    for name, module in dependencies.items():
        try:
            __import__(module)
            available.append(name)
        except ImportError:
            missing.append(name)
    
    print(f"✓ Available dependencies: {', '.join(available)}")
    if missing:
        print(f"⚠ Missing optional dependencies: {', '.join(missing)}")
    
    # Check if core dependencies are available
    core_deps = ["PyMuPDF", "PIL", "numpy", "pandas"]
    missing_core = [dep for dep in core_deps if dep in missing]
    
    if missing_core:
        print(f"✗ Missing core dependencies: {', '.join(missing_core)}")
        return False
    else:
        print("✓ All core dependencies available")
        return True


def test_processor_initialization():
    """Test processor initialization with graceful degradation"""
    print("\\nTesting processor initialization...")
    
    try:
        from pdf_pipeline import PDFProcessor, ProcessingConfig
        
        # Test with default config
        config = ProcessingConfig(output_dir="test_output")
        processor = PDFProcessor(config)
        print("✓ Processor initialized with default config")
        
        # Test extractor availability
        available_extractors = [name for name, extractor in processor.extractors.items() if extractor is not None]
        unavailable_extractors = [name for name, extractor in processor.extractors.items() if extractor is None]
        
        print(f"✓ Available extractors: {', '.join(available_extractors)}")
        if unavailable_extractors:
            print(f"⚠ Unavailable extractors (gracefully degraded): {', '.join(unavailable_extractors)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Processor initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cli_availability():
    """Test command-line interface availability"""
    print("\\nTesting CLI availability...")
    
    cli_path = Path(__file__).parent / "pdf_processor_cli.py"
    if cli_path.exists():
        print("✓ CLI script found")
        
        # Test CLI help (without running full command)
        try:
            import subprocess
            result = subprocess.run([
                sys.executable, str(cli_path), "--help"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print("✓ CLI help command works")
                return True
            else:
                print(f"✗ CLI help failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("⚠ CLI test timed out")
            return False
        except Exception as e:
            print(f"✗ CLI test failed: {e}")
            return False
    else:
        print("✗ CLI script not found")
        return False


def test_example_script():
    """Test example script availability"""
    print("\\nTesting example script...")
    
    example_path = Path(__file__).parent / "example_usage.py"
    if example_path.exists():
        print("✓ Example script found")
        return True
    else:
        print("✗ Example script not found")
        return False


def main():
    """Run all tests"""
    print("Academic PDF Processing Pipeline - Test Suite")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Configuration Test", test_configuration),
        ("Dependencies Test", test_dependencies),
        ("Processor Initialization Test", test_processor_initialization),
        ("CLI Availability Test", test_cli_availability),
        ("Example Script Test", test_example_script),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\\n{test_name}")
        print("-" * len(test_name))
        
        try:
            if test_func():
                passed += 1
                print("✓ PASSED")
            else:
                print("✗ FAILED")
        except Exception as e:
            print(f"✗ ERROR: {e}")
    
    print("\\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The pipeline is ready to use.")
        print("\\nNext steps:")
        print("1. Install optional dependencies: pip install -r requirements.txt")
        print("2. Try the CLI: python pdf_processor_cli.py --help")
        print("3. Run examples: python example_usage.py")
    else:
        print("⚠ Some tests failed. Check the output above for details.")
        print("\\nCommon fixes:")
        print("- Install missing dependencies: pip install -r requirements.txt")
        print("- Check Python path and imports")
        print("- Ensure all files are in the correct locations")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
