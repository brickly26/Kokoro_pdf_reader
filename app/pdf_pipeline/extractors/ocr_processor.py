"""
OCR processing for scanned PDF documents
"""

import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union
import io

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    # Create dummy imports for type hints
    class np:
        class ndarray:
            pass
    class cv2:
        pass

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class OCRProcessor:
    """
    OCR processing for scanned PDF documents.
    
    Supports multiple OCR engines:
    - Tesseract (default)
    - EasyOCR (alternative)
    
    Includes image preprocessing for better OCR results.
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        if not fitz:
            raise ImportError("PyMuPDF is required for OCR processing")
        
        # Check available OCR engines
        self.available_engines = []
        if TESSERACT_AVAILABLE and self.config.ocr_enabled:
            self.available_engines.append('tesseract')
        if EASYOCR_AVAILABLE and self.config.ocr_enabled:
            self.available_engines.append('easyocr')
        
        if not self.available_engines and self.config.ocr_enabled:
            logger.warning("No OCR engines available")
            return
        
        # Initialize OCR engines
        self.ocr_engines = {}
        self._initialize_engines()
        
        # Create OCR output directory
        self.ocr_dir = Path(self.config.output_dir) / "ocr"
        self.ocr_dir.mkdir(parents=True, exist_ok=True)
        
    def _initialize_engines(self):
        """Initialize available OCR engines"""
        
        if 'tesseract' in self.available_engines:
            try:
                # Test Tesseract installation
                pytesseract.get_tesseract_version()
                self.ocr_engines['tesseract'] = {'initialized': True}
                logger.info("Tesseract OCR engine initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Tesseract: {e}")
                self.available_engines.remove('tesseract')
        
        if 'easyocr' in self.available_engines:
            try:
                # Initialize EasyOCR reader
                reader = easyocr.Reader(self.config.ocr_languages, gpu=False)
                self.ocr_engines['easyocr'] = {'reader': reader}
                logger.info("EasyOCR engine initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize EasyOCR: {e}")
                self.available_engines.remove('easyocr')
    
    def process_document(self, document, results: Dict):
        """
        Process entire document with OCR.
        
        Args:
            document: PyMuPDF document object
            results: Results dictionary to update
        """
        if not self.config.ocr_enabled or not self.available_engines:
            logger.warning("OCR processing skipped - no engines available")
            return
        
        try:
            logger.info(f"Starting OCR processing for {document.page_count} pages")
            
            for page_num in range(document.page_count):
                page = document[page_num]
                logger.debug(f"OCR processing page {page_num + 1}")
                
                # Process page with OCR
                ocr_results = self._process_page_with_ocr(page, page_num)
                
                # Add OCR results to document results
                self._add_ocr_results_to_document(ocr_results, page_num, results)
            
            logger.info("OCR processing completed")
            
        except Exception as e:
            logger.error(f"OCR document processing failed: {e}")
    
    def _process_page_with_ocr(self, page, page_num: int) -> List[Dict]:
        """Process a single page with OCR"""
        ocr_results = []
        
        try:
            # Convert page to image
            page_image = self._page_to_image(page)
            if page_image is None:
                return ocr_results
            
            # Preprocess image for better OCR
            processed_image = self._preprocess_image(page_image)
            
            # Run OCR with selected engine
            engine = self.config.ocr_engine
            if engine not in self.available_engines:
                engine = self.available_engines[0]  # Use first available
            
            if engine == 'tesseract':
                ocr_results = self._run_tesseract_ocr(processed_image, page_num)
            elif engine == 'easyocr':
                ocr_results = self._run_easyocr_ocr(processed_image, page_num)
            
            # Save processed image for debugging if needed
            if self.config.debug:
                self._save_debug_image(processed_image, page_num)
            
        except Exception as e:
            logger.error(f"OCR processing failed for page {page_num}: {e}")
        
        return ocr_results
    
    def _page_to_image(self, page) -> Optional[np.ndarray]:
        """Convert PDF page to image for OCR"""
        try:
            # Get page as high-resolution pixmap
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img_data = pix.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # Convert to numpy array
            image_array = np.array(pil_image)
            
            # Convert RGB to BGR for OpenCV compatibility
            if len(image_array.shape) == 3:
                image_array = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
            
            return image_array
            
        except Exception as e:
            logger.error(f"Failed to convert page to image: {e}")
            return None
    
    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results"""
        if not CV2_AVAILABLE:
            return image
        
        try:
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Apply preprocessing steps
            # 1. Noise reduction
            denoised = cv2.medianBlur(gray, 3)
            
            # 2. Threshold to binary
            _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # 3. Dilation and erosion to improve text connectivity
            kernel = np.ones((1, 1), np.uint8)
            processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            return processed
            
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}")
            return image
    
    def _run_tesseract_ocr(self, image: np.ndarray, page_num: int) -> List[Dict]:
        """Run Tesseract OCR on image"""
        ocr_results = []
        
        try:
            # Convert numpy array to PIL Image for Tesseract
            if len(image.shape) == 3:
                pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            else:
                pil_image = Image.fromarray(image)
            
            # Configure Tesseract
            config = '--oem 3 --psm 6'  # Use LSTM and assume uniform text block
            
            # Get detailed OCR data
            data = pytesseract.image_to_data(
                pil_image, 
                lang='+'.join(self.config.ocr_languages),
                config=config,
                output_type=pytesseract.Output.DICT
            )
            
            # Process OCR results
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                text = data['text'][i].strip()
                conf = int(data['conf'][i])
                
                if text and conf > 0:  # Filter out empty text and low confidence
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    
                    ocr_result = {
                        'text': text,
                        'bbox': [x, y, x + w, y + h],
                        'confidence': conf,
                        'page': page_num,
                        'engine': 'tesseract',
                        'word_num': data['word_num'][i],
                        'line_num': data['line_num'][i],
                        'par_num': data['par_num'][i],
                        'block_num': data['block_num'][i]
                    }
                    ocr_results.append(ocr_result)
            
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
        
        return ocr_results
    
    def _run_easyocr_ocr(self, image: np.ndarray, page_num: int) -> List[Dict]:
        """Run EasyOCR on image"""
        ocr_results = []
        
        try:
            reader = self.ocr_engines['easyocr']['reader']
            
            # Run OCR
            results = reader.readtext(image)
            
            # Process results
            for result in results:
                bbox_coords, text, confidence = result
                
                if text.strip() and confidence > 0.1:  # Filter low confidence
                    # Convert bbox format
                    x_coords = [point[0] for point in bbox_coords]
                    y_coords = [point[1] for point in bbox_coords]
                    bbox = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
                    
                    ocr_result = {
                        'text': text.strip(),
                        'bbox': bbox,
                        'confidence': int(confidence * 100),  # Convert to percentage
                        'page': page_num,
                        'engine': 'easyocr',
                        'original_bbox': bbox_coords
                    }
                    ocr_results.append(ocr_result)
            
        except Exception as e:
            logger.error(f"EasyOCR failed: {e}")
        
        return ocr_results
    
    def _add_ocr_results_to_document(self, ocr_results: List[Dict], page_num: int, results: Dict):
        """Add OCR results to document results structure"""
        
        # Group OCR results into text blocks
        text_blocks = self._group_ocr_into_blocks(ocr_results)
        
        # Add to results
        for block in text_blocks:
            text_entry = {
                'type': 'body',  # Default to body text
                'text': block['text'],
                'page': page_num,
                'bbox': block['bbox'],
                'source': 'ocr',
                'engine': block.get('engine'),
                'confidence': block.get('confidence'),
                'word_count': len(block['text'].split())
            }
            results['content']['text_blocks'].append(text_entry)
        
        # Save raw OCR data
        self._save_ocr_data(ocr_results, page_num)
    
    def _group_ocr_into_blocks(self, ocr_results: List[Dict]) -> List[Dict]:
        """Group individual OCR words into coherent text blocks"""
        if not ocr_results:
            return []
        
        # Sort by reading order (top-to-bottom, left-to-right)
        ocr_results.sort(key=lambda x: (x['bbox'][1], x['bbox'][0]))
        
        blocks = []
        current_block = None
        
        for ocr_result in ocr_results:
            if current_block is None:
                # Start new block
                current_block = {
                    'text': ocr_result['text'],
                    'bbox': ocr_result['bbox'][:],
                    'confidence': ocr_result['confidence'],
                    'engine': ocr_result['engine'],
                    'word_count': 1
                }
            else:
                # Check if this word should be added to current block
                if self._should_merge_with_block(ocr_result, current_block):
                    # Merge with current block
                    current_block['text'] += ' ' + ocr_result['text']
                    current_block['bbox'] = self._expand_bbox(current_block['bbox'], ocr_result['bbox'])
                    current_block['confidence'] = (current_block['confidence'] + ocr_result['confidence']) / 2
                    current_block['word_count'] += 1
                else:
                    # Start new block
                    blocks.append(current_block)
                    current_block = {
                        'text': ocr_result['text'],
                        'bbox': ocr_result['bbox'][:],
                        'confidence': ocr_result['confidence'],
                        'engine': ocr_result['engine'],
                        'word_count': 1
                    }
        
        # Add final block
        if current_block:
            blocks.append(current_block)
        
        return blocks
    
    def _should_merge_with_block(self, ocr_result: Dict, current_block: Dict) -> bool:
        """Determine if OCR result should be merged with current block"""
        
        # Check horizontal alignment
        ocr_bbox = ocr_result['bbox']
        block_bbox = current_block['bbox']
        
        # Vertical overlap check
        ocr_y_center = (ocr_bbox[1] + ocr_bbox[3]) / 2
        if not (block_bbox[1] <= ocr_y_center <= block_bbox[3]):
            # Check if they're on the same line (within reasonable distance)
            vertical_distance = min(
                abs(ocr_bbox[1] - block_bbox[3]),
                abs(ocr_bbox[3] - block_bbox[1])
            )
            if vertical_distance > 20:  # More than 20 pixels apart vertically
                return False
        
        # Horizontal distance check
        horizontal_distance = max(0, ocr_bbox[0] - block_bbox[2])
        if horizontal_distance > 50:  # More than 50 pixels apart horizontally
            return False
        
        # Don't merge if block is getting too long
        if current_block['word_count'] > 100:  # Arbitrary limit
            return False
        
        return True
    
    def _expand_bbox(self, bbox1: List[float], bbox2: List[float]) -> List[float]:
        """Expand bbox1 to include bbox2"""
        return [
            min(bbox1[0], bbox2[0]),  # min x
            min(bbox1[1], bbox2[1]),  # min y
            max(bbox1[2], bbox2[2]),  # max x
            max(bbox1[3], bbox2[3])   # max y
        ]
    
    def _save_ocr_data(self, ocr_results: List[Dict], page_num: int):
        """Save raw OCR data for debugging"""
        if not self.config.debug:
            return
        
        try:
            import json
            
            ocr_file = self.ocr_dir / f"page_{page_num:03d}_ocr_data.json"
            with open(ocr_file, 'w', encoding='utf-8') as f:
                json.dump(ocr_results, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.debug(f"Failed to save OCR data: {e}")
    
    def _save_debug_image(self, image: np.ndarray, page_num: int):
        """Save processed image for debugging"""
        try:
            debug_file = self.ocr_dir / f"page_{page_num:03d}_processed.png"
            cv2.imwrite(str(debug_file), image)
            
        except Exception as e:
            logger.debug(f"Failed to save debug image: {e}")
    
    def estimate_ocr_quality(self, ocr_results: List[Dict]) -> Dict:
        """Estimate the quality of OCR results"""
        if not ocr_results:
            return {'overall_quality': 0.0, 'details': {}}
        
        # Calculate average confidence
        confidences = [r['confidence'] for r in ocr_results if 'confidence' in r]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Count words and characters
        total_words = len(ocr_results)
        total_chars = sum(len(r['text']) for r in ocr_results)
        
        # Estimate quality based on various factors
        quality_score = avg_confidence / 100  # Normalize to 0-1
        
        # Penalize for very short words (likely OCR errors)
        short_words = sum(1 for r in ocr_results if len(r['text'].strip()) <= 2)
        if total_words > 0:
            short_word_ratio = short_words / total_words
            quality_score *= (1 - short_word_ratio * 0.5)
        
        return {
            'overall_quality': quality_score,
            'details': {
                'average_confidence': avg_confidence,
                'total_words': total_words,
                'total_characters': total_chars,
                'short_words': short_words,
                'short_word_ratio': short_words / total_words if total_words > 0 else 0
            }
        }
