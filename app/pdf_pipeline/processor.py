"""
Main PDF Processing Pipeline

Orchestrates the extraction and categorization of content from academic PDFs
using multiple specialized extractors and analysis techniques.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import asdict
import time

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .config import ProcessingConfig
from .extractors.layout_detector import LayoutDetector
from .extractors.image_extractor import ImageExtractor
from .extractors.table_extractor import TableExtractor
from .extractors.text_classifier import TextClassifier
from .extractors.formula_detector import FormulaDetector
from .extractors.caption_matcher import CaptionMatcher
from .extractors.ocr_processor import OCRProcessor
from .utils.output_manager import OutputManager
from .utils.pdf_utils import PDFUtils


logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Main class for processing academic PDFs with comprehensive content extraction.
    
    Supports:
    - Layout detection using PubLayNet
    - Table extraction with Camelot
    - Image extraction and organization
    - Formula detection
    - Text classification (headers, footers, etc.)
    - Caption matching
    - OCR fallback for scanned documents
    """
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        """Initialize the PDF processor with configuration"""
        self.config = config or ProcessingConfig()
        self._setup_logging()
        
        # Initialize extractors with graceful degradation
        self.extractors = {}
        self._initialize_extractors()
        
        # Initialize utilities
        self.output_manager = OutputManager(self.config)
        self.pdf_utils = PDFUtils()
        
        # Processing state
        self.document = None
        self.results = {}
        
    def _setup_logging(self):
        """Setup logging based on configuration"""
        level = logging.DEBUG if self.config.debug else (
            logging.INFO if self.config.verbose else logging.WARNING
        )
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
    def _initialize_extractors(self):
        """Initialize all extractors with graceful degradation"""
        extractor_classes = [
            ('layout_detector', LayoutDetector),
            ('image_extractor', ImageExtractor),
            ('table_extractor', TableExtractor),
            ('text_classifier', TextClassifier),
            ('formula_detector', FormulaDetector),
            ('caption_matcher', CaptionMatcher),
            ('ocr_processor', OCRProcessor),
        ]
        
        for name, extractor_class in extractor_classes:
            try:
                self.extractors[name] = extractor_class(self.config)
                logger.info(f"Initialized {name}")
            except ImportError as e:
                logger.warning(f"Could not initialize {name}: {e}")
                self.extractors[name] = None
            except Exception as e:
                logger.error(f"Error initializing {name}: {e}")
                self.extractors[name] = None
    
    def process_pdf(self, pdf_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a PDF file and extract all content types.
        
        Args:
            pdf_path: Path to the PDF file
            output_dir: Optional output directory (overrides config)
            
        Returns:
            Dictionary containing all extracted content and metadata
        """
        if not fitz:
            raise ImportError("PyMuPDF is required but not available")
            
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Setup output directory
        if output_dir:
            original_output_dir = self.config.output_dir
            self.config.output_dir = output_dir
            self.output_manager = OutputManager(self.config)
        
        try:
            logger.info(f"Starting PDF processing: {pdf_path}")
            start_time = time.time()
            
            # Open PDF document
            self.document = fitz.open(str(pdf_path))
            logger.info(f"Opened PDF with {self.document.page_count} pages")
            
            # Initialize results structure
            self.results = {
                'metadata': {
                    'source_file': str(pdf_path),
                    'total_pages': self.document.page_count,
                    'processing_time': 0,
                    'timestamp': time.time(),
                    'config': asdict(self.config)
                },
                'content': {
                    'text_blocks': [],
                    'titles': [],
                    'tables': [],
                    'figures': [],
                    'images': [],
                    'formulas': [],
                    'captions': [],
                    'headers': [],
                    'footers': [],
                    'page_numbers': [],
                    'footnotes': [],
                    'lists': []
                },
                'artifacts': {
                    'images': [],
                    'tables': [],
                    'text_file': None
                }
            }
            
            # Check if OCR is needed
            text_extractable = self._check_text_extractability()
            if text_extractable < self.config.ocr_fallback_threshold:
                logger.info(f"Low text extractability ({text_extractable:.1%}), using OCR")
                self._process_with_ocr()
            else:
                self._process_with_text_extraction()
            
            # Post-processing steps
            self._match_captions()
            self._classify_reading_order()
            self._generate_outputs()
            
            # Finalize results
            self.results['metadata']['processing_time'] = time.time() - start_time
            logger.info(f"PDF processing completed in {self.results['metadata']['processing_time']:.2f}s")
            
            return self.results
            
        finally:
            if self.document:
                self.document.close()
            
            # Restore original output directory if changed
            if output_dir:
                self.config.output_dir = original_output_dir
                self.output_manager = OutputManager(self.config)
    
    def _check_text_extractability(self) -> float:
        """Check what percentage of pages have extractable text"""
        if not self.document:
            return 0.0
            
        pages_with_text = 0
        for page_num in range(min(10, self.document.page_count)):  # Sample first 10 pages
            page = self.document[page_num]
            text = page.get_text().strip()
            if len(text) > 50:  # Arbitrary threshold for meaningful text
                pages_with_text += 1
        
        return pages_with_text / min(10, self.document.page_count)
    
    def _process_with_text_extraction(self):
        """Process PDF using native text extraction"""
        logger.info("Processing with native text extraction")
        
        for page_num in range(self.document.page_count):
            page = self.document[page_num]
            logger.debug(f"Processing page {page_num + 1}")
            
            # Layout detection
            layout_regions = self._detect_layout(page, page_num)
            
            # Extract different content types
            self._extract_text_blocks(page, page_num, layout_regions)
            self._extract_images(page, page_num)
            self._extract_tables(page, page_num)
            self._detect_formulas(page, page_num)
    
    def _process_with_ocr(self):
        """Process PDF using OCR"""
        if not self.extractors['ocr_processor']:
            logger.error("OCR processor not available")
            return
            
        logger.info("Processing with OCR")
        self.extractors['ocr_processor'].process_document(self.document, self.results)
    
    def _detect_layout(self, page, page_num: int) -> List[Dict]:
        """Detect page layout regions"""
        if not self.extractors['layout_detector']:
            return []
        
        try:
            return self.extractors['layout_detector'].detect_layout(page, page_num)
        except Exception as e:
            logger.warning(f"Layout detection failed for page {page_num}: {e}")
            return []
    
    def _extract_text_blocks(self, page, page_num: int, layout_regions: List[Dict]):
        """Extract and classify text blocks"""
        if not self.extractors['text_classifier']:
            return
        
        try:
            self.extractors['text_classifier'].classify_text_blocks(
                page, page_num, layout_regions, self.results
            )
        except Exception as e:
            logger.warning(f"Text classification failed for page {page_num}: {e}")
    
    def _extract_images(self, page, page_num: int):
        """Extract images from the page"""
        if not self.extractors['image_extractor']:
            return
        
        try:
            self.extractors['image_extractor'].extract_images(page, page_num, self.results)
        except Exception as e:
            logger.warning(f"Image extraction failed for page {page_num}: {e}")
    
    def _extract_tables(self, page, page_num: int):
        """Extract tables from the page"""
        if not self.extractors['table_extractor']:
            return
        
        try:
            self.extractors['table_extractor'].extract_tables(page, page_num, self.results)
        except Exception as e:
            logger.warning(f"Table extraction failed for page {page_num}: {e}")
    
    def _detect_formulas(self, page, page_num: int):
        """Detect mathematical formulas"""
        if not self.extractors['formula_detector']:
            return
        
        try:
            self.extractors['formula_detector'].detect_formulas(page, page_num, self.results)
        except Exception as e:
            logger.warning(f"Formula detection failed for page {page_num}: {e}")
    
    def _match_captions(self):
        """Match captions with figures and tables"""
        if not self.extractors['caption_matcher']:
            return
        
        try:
            self.extractors['caption_matcher'].match_captions(self.results)
        except Exception as e:
            logger.warning(f"Caption matching failed: {e}")
    
    def _classify_reading_order(self):
        """Establish reading order for content blocks"""
        if not self.config.preserve_reading_order:
            return
        
        # Sort content by page and vertical position
        for content_type in self.results['content'].values():
            if isinstance(content_type, list):
                content_type.sort(key=lambda x: (x.get('page', 0), x.get('bbox', [0, 0, 0, 0])[1]))
    
    def _generate_outputs(self):
        """Generate all output files"""
        try:
            self.output_manager.generate_outputs(self.results)
        except Exception as e:
            logger.error(f"Output generation failed: {e}")
    
    def get_summary(self) -> Dict[str, int]:
        """Get a summary of extracted content"""
        if not self.results:
            return {}
        
        return {
            content_type: len(content_list) 
            for content_type, content_list in self.results['content'].items()
            if isinstance(content_list, list)
        }
    
    def save_results(self, filepath: str):
        """Save processing results to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
