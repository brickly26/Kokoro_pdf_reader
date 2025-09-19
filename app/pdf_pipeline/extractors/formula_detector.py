"""
Mathematical formula detection in PDF documents
"""

import logging
import re
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import sympy
    from sympy.parsing.latex import parse_latex
    SYMPY_AVAILABLE = True
except ImportError:
    SYMPY_AVAILABLE = False

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class FormulaDetector:
    """
    Detects mathematical formulas and equations in PDF documents.
    
    Uses multiple detection methods:
    1. Math symbol detection in text
    2. LaTeX-like pattern recognition
    3. Font analysis (math fonts)
    4. Position and context analysis
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        if not fitz:
            raise ImportError("PyMuPDF is required for formula detection")
        
        # Create formulas output directory
        self.formulas_dir = Path(self.config.output_dir) / "formulas"
        self.formulas_dir.mkdir(parents=True, exist_ok=True)
        
        # Compile patterns
        self._compile_patterns()
        
        # Math fonts commonly used in PDFs
        self.math_fonts = {
            'symbol', 'mathematic', 'times-roman', 'cmr', 'cmmi', 'cmsy', 'cmex',
            'msam', 'msbm', 'eufm', 'eurm', 'stix', 'xits', 'latinmodern'
        }
        
        self.detected_count = 0
    
    def _compile_patterns(self):
        """Compile regex patterns for formula detection"""
        
        # LaTeX-like patterns
        self.latex_patterns = [
            re.compile(r'\\[a-zA-Z]+\{[^}]*\}'),  # \command{content}
            re.compile(r'\\[a-zA-Z]+'),           # \command
            re.compile(r'\$[^$]+\$'),             # $equation$
            re.compile(r'\\\([^)]+\\\)'),         # \(equation\)
            re.compile(r'\\\[[^\]]+\\\]'),        # \[equation\]
            re.compile(r'\\begin\{[^}]+\}.*?\\end\{[^}]+\}', re.DOTALL),  # \begin{env}...\end{env}
        ]
        
        # Mathematical operator patterns
        self.operator_patterns = [
            re.compile(r'[∫∑∏∂∇△▽]'),  # Integral, sum, product, partial derivatives
            re.compile(r'[≤≥≠≈≡∝∞]'),  # Comparison and special symbols
            re.compile(r'[∈∉⊂⊃⊆⊇∪∩]'),  # Set theory symbols
            re.compile(r'[→←↔⇒⇐⇔]'),    # Arrows
            re.compile(r'[αβγδεζηθικλμνξοπρστυφχψω]'),  # Greek letters (lowercase)
            re.compile(r'[ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]'),  # Greek letters (uppercase)
        ]
        
        # Mathematical expression patterns
        self.expression_patterns = [
            re.compile(r'[a-zA-Z]+[₀-₉]+'),       # Subscripts
            re.compile(r'[a-zA-Z]+[⁰-⁹]+'),       # Superscripts
            re.compile(r'[a-zA-Z]+_\{[^}]+\}'),   # LaTeX subscripts
            re.compile(r'[a-zA-Z]+\^\{[^}]+\}'),  # LaTeX superscripts
            re.compile(r'√[^√\s]+'),              # Square roots
            re.compile(r'\([^)]*[+\-*/^=][^)]*\)'), # Expressions in parentheses
            re.compile(r'[a-zA-Z]\s*[=]\s*[^=\s][^=]*'), # Equations
        ]
        
        # Fraction patterns
        self.fraction_patterns = [
            re.compile(r'\d+/\d+'),               # Simple fractions
            re.compile(r'\\frac\{[^}]+\}\{[^}]+\}'), # LaTeX fractions
            re.compile(r'[a-zA-Z0-9]+\s*/\s*[a-zA-Z0-9]+'), # Variable fractions
        ]
        
        # Mathematical context keywords
        self.math_context_keywords = set(self.config.math_keywords + [
            'formula', 'equation', 'expression', 'function', 'derivative',
            'integral', 'matrix', 'vector', 'probability', 'statistic',
            'hypothesis', 'correlation', 'regression', 'optimization'
        ])
    
    def detect_formulas(self, page, page_num: int, results: Dict):
        """
        Detect mathematical formulas on a PDF page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (0-indexed)
            results: Results dictionary to update
        """
        if not self.config.formula_detection_enabled:
            return
        
        try:
            # Get text with detailed formatting
            text_dict = page.get_text("dict")
            
            # Detect formulas in text spans
            formula_candidates = []
            
            for block in text_dict.get("blocks", []):
                if block.get("type", 0) == 1:  # Skip image blocks
                    continue
                
                candidates = self._detect_formulas_in_block(block, page_num)
                formula_candidates.extend(candidates)
            
            # Filter and validate candidates
            validated_formulas = self._validate_formula_candidates(formula_candidates)
            
            # Save formulas
            for formula_info in validated_formulas:
                self._save_formula(formula_info, page_num, results)
            
            logger.debug(f"Detected {len(validated_formulas)} formulas on page {page_num}")
            
        except Exception as e:
            logger.error(f"Formula detection failed for page {page_num}: {e}")
    
    def _detect_formulas_in_block(self, block: Dict, page_num: int) -> List[Dict]:
        """Detect formula candidates in a text block"""
        candidates = []
        
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                
                # Check for mathematical content
                formula_info = self._analyze_span_for_math(span, page_num)
                if formula_info:
                    candidates.append(formula_info)
        
        return candidates
    
    def _analyze_span_for_math(self, span: Dict, page_num: int) -> Optional[Dict]:
        """Analyze a text span for mathematical content"""
        text = span.get("text", "")
        font = span.get("font", "").lower()
        size = span.get("size", 0)
        flags = span.get("flags", 0)
        bbox = span.get("bbox")
        
        # Calculate math score
        math_score = 0
        detected_features = []
        
        # Check for math symbols
        symbol_count = 0
        for symbol in self.config.math_symbols:
            if symbol in text:
                symbol_count += text.count(symbol)
        
        if symbol_count > 0:
            math_score += min(symbol_count * 10, 50)
            detected_features.append(f"math_symbols({symbol_count})")
        
        # Check for mathematical patterns
        for pattern in self.operator_patterns:
            if pattern.search(text):
                math_score += 15
                detected_features.append("operators")
                break
        
        for pattern in self.expression_patterns:
            if pattern.search(text):
                math_score += 10
                detected_features.append("expressions")
                break
        
        for pattern in self.fraction_patterns:
            if pattern.search(text):
                math_score += 20
                detected_features.append("fractions")
                break
        
        for pattern in self.latex_patterns:
            if pattern.search(text):
                math_score += 25
                detected_features.append("latex")
                break
        
        # Check math font
        for math_font in self.math_fonts:
            if math_font in font:
                math_score += 15
                detected_features.append(f"math_font({math_font})")
                break
        
        # Check for italic text (often used for variables)
        if flags & 2**1:  # Italic flag
            # Count variable-like patterns
            var_count = len(re.findall(r'\\b[a-zA-Z]\\b', text))
            if var_count > 0:
                math_score += min(var_count * 5, 15)
                detected_features.append(f"variables({var_count})")
        
        # Check for numbers with operators
        if re.search(r'\\d+\\s*[+\\-*/=]\\s*\\d+', text):
            math_score += 10
            detected_features.append("arithmetic")
        
        # Penalty for common words (reduces false positives)
        word_count = len(text.split())
        if word_count > 5:
            common_words = len(re.findall(r'\\b(?:the|and|or|is|are|was|were|in|on|at|to|for|of|with)\\b', text.lower()))
            if common_words > word_count * 0.3:
                math_score -= 20
                detected_features.append(f"common_words_penalty({common_words})")
        
        # Minimum score threshold
        if math_score < 15:
            return None
        
        return {
            'text': text,
            'bbox': bbox,
            'page': page_num,
            'font': font,
            'size': size,
            'flags': flags,
            'math_score': math_score,
            'features': detected_features,
            'span_info': span
        }
    
    def _validate_formula_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Validate and filter formula candidates"""
        if not candidates:
            return []
        
        validated = []
        
        for candidate in candidates:
            # Additional validation checks
            text = candidate['text']
            
            # Skip very short text unless it has high math score
            if len(text.strip()) < 3 and candidate['math_score'] < 30:
                continue
            
            # Skip very long text unless it has very high math score
            if len(text) > 200 and candidate['math_score'] < 50:
                continue
            
            # Check for context clues
            context_boost = self._check_mathematical_context(candidate)
            candidate['math_score'] += context_boost
            
            # Final score threshold
            if candidate['math_score'] >= 20:
                validated.append(candidate)
        
        # Remove duplicates (same text on same page)
        seen = set()
        unique_validated = []
        for candidate in validated:
            key = (candidate['page'], candidate['text'].strip())
            if key not in seen:
                seen.add(key)
                unique_validated.append(candidate)
        
        return unique_validated
    
    def _check_mathematical_context(self, candidate: Dict) -> int:
        """Check if formula appears in mathematical context"""
        # This is a simplified version - in practice, you'd analyze surrounding text
        text = candidate['text'].lower()
        
        context_score = 0
        
        # Check for math keywords in the text itself
        for keyword in self.math_context_keywords:
            if keyword in text:
                context_score += 5
        
        # Check for equation-like structure
        if '=' in text and len(text.split('=')) == 2:
            context_score += 10
        
        # Check for function-like patterns
        if re.search(r'[a-zA-Z]+\\([^)]*\\)', text):
            context_score += 8
        
        return context_score
    
    def _save_formula(self, formula_info: Dict, page_num: int, results: Dict):
        """Save a detected formula"""
        try:
            self.detected_count += 1
            
            # Create formula entry
            formula_entry = {
                'type': 'formula',
                'text': formula_info['text'],
                'page': page_num,
                'bbox': formula_info['bbox'],
                'math_score': formula_info['math_score'],
                'features': formula_info['features'],
                'font_info': {
                    'font': formula_info['font'],
                    'size': formula_info['size'],
                    'flags': formula_info['flags']
                }
            }
            
            # Try to parse with SymPy if available
            if SYMPY_AVAILABLE:
                try:
                    # Attempt to parse as LaTeX
                    if any('latex' in feature for feature in formula_info['features']):
                        parsed = parse_latex(formula_info['text'])
                        formula_entry['sympy_parsed'] = str(parsed)
                        formula_entry['is_valid_latex'] = True
                except:
                    formula_entry['is_valid_latex'] = False
            
            # Save formula text to file
            formula_filename = f"page_{page_num:03d}_formula_{self.detected_count:03d}.txt"
            formula_path = self.formulas_dir / formula_filename
            
            with open(formula_path, 'w', encoding='utf-8') as f:
                f.write(f"Formula from page {page_num + 1}:\\n")
                f.write(f"Math Score: {formula_info['math_score']}\\n")
                f.write(f"Features: {', '.join(formula_info['features'])}\\n")
                f.write(f"Font: {formula_info['font']}\\n")
                f.write(f"Text: {formula_info['text']}\\n")
                
                if 'sympy_parsed' in formula_entry:
                    f.write(f"\\nParsed: {formula_entry['sympy_parsed']}\\n")
            
            formula_entry['file_path'] = str(formula_path)
            
            # Add to results
            results['content']['formulas'].append(formula_entry)
            
            logger.debug(f"Saved formula: {formula_info['text'][:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to save formula: {e}")
    
    def extract_equation_images(self, page, page_num: int, layout_regions: List[Dict]) -> List[Dict]:
        """Extract images that might contain equations"""
        equation_images = []
        
        if not self.config.save_images:
            return equation_images
        
        try:
            # Look for figure regions that might contain equations
            figure_regions = [r for r in layout_regions if r.get('type', '').lower() == 'figure']
            
            for region in figure_regions:
                bbox = region.get('bbox')
                if not bbox:
                    continue
                
                # Check if this region is near mathematical text
                nearby_math = self._find_nearby_math_text(page, bbox)
                
                if nearby_math:
                    # Extract this region as an image
                    image_data = self._extract_region_as_image(page, bbox, page_num)
                    if image_data:
                        equation_images.append({
                            'type': 'equation_image',
                            'bbox': bbox,
                            'page': page_num,
                            'nearby_math': nearby_math,
                            'image_data': image_data
                        })
        
        except Exception as e:
            logger.warning(f"Equation image extraction failed for page {page_num}: {e}")
        
        return equation_images
    
    def _find_nearby_math_text(self, page, bbox: List[float]) -> List[str]:
        """Find mathematical text near a bounding box"""
        # This is a simplified implementation
        nearby_math = []
        
        try:
            text_dict = page.get_text("dict")
            
            for block in text_dict.get("blocks", []):
                if block.get("type", 0) == 1:
                    continue
                
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_bbox = span.get("bbox")
                        text = span.get("text", "")
                        
                        if span_bbox and text:
                            # Check if span is near the region
                            distance = self._calculate_bbox_distance(bbox, span_bbox)
                            if distance < 100:  # Within 100 points
                                # Check if text contains math
                                if any(symbol in text for symbol in self.config.math_symbols):
                                    nearby_math.append(text)
        
        except Exception:
            pass
        
        return nearby_math
    
    def _calculate_bbox_distance(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate minimum distance between two bounding boxes"""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Calculate distance between closest edges
        dx = max(0, max(x1_1 - x2_2, x1_2 - x2_1))
        dy = max(0, max(y1_1 - y2_2, y1_2 - y2_1))
        
        return (dx**2 + dy**2)**0.5
    
    def _extract_region_as_image(self, page, bbox: List[float], page_num: int) -> Optional[bytes]:
        """Extract a page region as an image"""
        try:
            # Create rect from bbox
            rect = fitz.Rect(bbox)
            
            # Add some padding
            rect.x0 -= 5
            rect.y0 -= 5
            rect.x1 += 5
            rect.y1 += 5
            
            # Ensure rect is within page bounds
            rect &= page.rect
            
            # Render the region
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat, clip=rect)
            
            return pix.tobytes("png")
            
        except Exception as e:
            logger.debug(f"Failed to extract region as image: {e}")
            return None
