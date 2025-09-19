"""
Text classification for different content types in PDF documents
"""

import logging
import re
from typing import List, Dict, Optional, Tuple, Set
import statistics

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class TextClassifier:
    """
    Classifies text blocks into different categories:
    - Main text (body)
    - Titles/headings
    - Headers and footers
    - Footnotes
    - Page numbers
    - Lists
    - Captions
    
    Uses font analysis, position heuristics, and content patterns.
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        if not fitz:
            raise ImportError("PyMuPDF is required for text classification")
        
        # Compile regex patterns for efficiency
        self._compile_patterns()
        
        # Track document statistics for adaptive thresholds
        self.font_sizes = []
        self.median_font_size = None
        
    def _compile_patterns(self):
        """Compile regex patterns for text classification"""
        # Page number patterns
        self.page_number_pattern = re.compile(
            r'^\s*(?:page\s*)?(\d+|[ivxlcdm]+)\s*$',
            re.IGNORECASE
        )
        
        # Footnote patterns
        self.footnote_pattern = re.compile(
            r'^\s*[\d\*†‡§¶#]+\s*[\.:\-\s]',
            re.IGNORECASE
        )
        
        # Citation patterns
        self.citation_pattern = re.compile(
            r'\[\d+\]|\(\d{4}\)|et\s+al\.|ibid\.|op\.\s*cit\.',
            re.IGNORECASE
        )
        
        # List patterns
        self.list_patterns = [
            re.compile(r'^\s*[\d\w]\.\s+'),  # 1. numbered
            re.compile(r'^\s*[a-z]\)\s+'),   # a) lettered
            re.compile(r'^\s*[•·‣▪▫▸▹◦‧⁃]\s+'),  # bullet points
            re.compile(r'^\s*[-\*\+]\s+'),   # dash/asterisk bullets
        ]
        
        # Title patterns
        self.title_indicators = [
            'abstract', 'introduction', 'conclusion', 'discussion',
            'methodology', 'results', 'references', 'bibliography',
            'acknowledgments', 'appendix', 'chapter', 'section'
        ]
        
        # Caption patterns
        caption_keywords = '|'.join(self.config.caption_keywords)
        self.caption_pattern = re.compile(
            rf'^\s*(?:{caption_keywords})\s*[:\d\.]',
            re.IGNORECASE
        )
    
    def classify_text_blocks(self, page, page_num: int, layout_regions: List[Dict], results: Dict):
        """
        Classify all text blocks on a page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (0-indexed)
            layout_regions: Layout detection results
            results: Results dictionary to update
        """
        try:
            # Get page text with detailed formatting info
            text_dict = page.get_text("dict")
            page_rect = page.rect
            
            # Collect font size statistics for adaptive thresholds
            self._collect_font_statistics(text_dict)
            
            # Process text blocks
            for block in text_dict.get("blocks", []):
                if block.get("type", 0) == 1:  # Skip image blocks
                    continue
                
                self._process_text_block(block, page_num, page_rect, layout_regions, results)
            
        except Exception as e:
            logger.error(f"Text classification failed for page {page_num}: {e}")
    
    def _collect_font_statistics(self, text_dict: Dict):
        """Collect font size statistics for adaptive classification"""
        for block in text_dict.get("blocks", []):
            if block.get("type", 0) == 1:
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_size = span.get("size", 0)
                    if font_size > 0:
                        self.font_sizes.append(font_size)
        
        # Update median font size
        if self.font_sizes:
            self.median_font_size = statistics.median(self.font_sizes)
    
    def _process_text_block(self, block: Dict, page_num: int, page_rect, layout_regions: List[Dict], results: Dict):
        """Process a single text block"""
        block_bbox = block.get("bbox")
        if not block_bbox:
            return
        
        # Get layout region type if available
        layout_type = self._get_layout_type(block_bbox, layout_regions)
        
        # Process each line in the block
        for line in block.get("lines", []):
            self._process_text_line(line, page_num, page_rect, layout_type, results)
    
    def _process_text_line(self, line: Dict, page_num: int, page_rect, layout_type: Optional[str], results: Dict):
        """Process a single text line"""
        line_bbox = line.get("bbox")
        if not line_bbox:
            return
        
        # Combine all spans in the line
        text_parts = []
        font_info = []
        
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if text:
                text_parts.append(text)
                font_info.append({
                    'size': span.get("size", 0),
                    'flags': span.get("flags", 0),
                    'font': span.get("font", ""),
                    'color': span.get("color", 0)
                })
        
        if not text_parts:
            return
        
        full_text = " ".join(text_parts)
        
        # Classify the text line
        text_type = self._classify_text_line(
            full_text, line_bbox, page_rect, page_num, font_info, layout_type
        )
        
        # Create text entry
        text_entry = {
            'type': text_type,
            'text': full_text,
            'page': page_num,
            'bbox': list(line_bbox),
            'font_info': font_info,
            'layout_type': layout_type
        }
        
        # Add to appropriate category
        if text_type == 'title':
            results['content']['titles'].append(text_entry)
        elif text_type == 'header':
            results['content']['headers'].append(text_entry)
        elif text_type == 'footer':
            results['content']['footers'].append(text_entry)
        elif text_type == 'page_number':
            results['content']['page_numbers'].append(text_entry)
        elif text_type == 'footnote':
            results['content']['footnotes'].append(text_entry)
        elif text_type == 'list':
            results['content']['lists'].append(text_entry)
        elif text_type == 'caption':
            results['content']['captions'].append(text_entry)
        else:  # body text
            results['content']['text_blocks'].append(text_entry)
    
    def _classify_text_line(self, text: str, bbox: Tuple, page_rect, page_num: int, 
                           font_info: List[Dict], layout_type: Optional[str]) -> str:
        """Classify a single text line"""
        
        # Quick filters
        if len(text.strip()) == 0:
            return 'body'
        
        # Check page number
        if self._is_page_number(text, bbox, page_rect):
            return 'page_number'
        
        # Check header/footer by position
        if self._is_header_footer(bbox, page_rect):
            return 'header' if bbox[1] < page_rect.height * self.config.header_region_threshold else 'footer'
        
        # Check footnote
        if self._is_footnote(text, bbox, page_rect, font_info):
            return 'footnote'
        
        # Check caption
        if self._is_caption(text, layout_type):
            return 'caption'
        
        # Check list item
        if self._is_list_item(text):
            return 'list'
        
        # Check title/heading
        if self._is_title(text, font_info, layout_type):
            return 'title'
        
        return 'body'
    
    def _get_layout_type(self, bbox: Tuple, layout_regions: List[Dict]) -> Optional[str]:
        """Get layout type for a bounding box"""
        x0, y0, x1, y1 = bbox
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        
        for region in layout_regions:
            region_bbox = region.get('bbox')
            if region_bbox:
                rx0, ry0, rx1, ry1 = region_bbox
                if rx0 <= center_x <= rx1 and ry0 <= center_y <= ry1:
                    return region.get('type')
        
        return None
    
    def _is_page_number(self, text: str, bbox: Tuple, page_rect) -> bool:
        """Check if text is a page number"""
        # Must be short
        if len(text.strip()) > 10:
            return False
        
        # Must match page number pattern
        if not self.page_number_pattern.match(text):
            return False
        
        # Must be in header/footer region
        y_ratio = bbox[1] / page_rect.height
        if not (y_ratio < self.config.header_region_threshold or 
                y_ratio > self.config.footer_region_threshold):
            return False
        
        return True
    
    def _is_header_footer(self, bbox: Tuple, page_rect) -> bool:
        """Check if text is in header or footer region"""
        y_ratio = bbox[1] / page_rect.height
        return (y_ratio < self.config.header_region_threshold or 
                y_ratio > self.config.footer_region_threshold)
    
    def _is_footnote(self, text: str, bbox: Tuple, page_rect, font_info: List[Dict]) -> bool:
        """Check if text is a footnote"""
        # Must be in footer region
        y_ratio = bbox[3] / page_rect.height  # Use bottom of bbox
        if y_ratio < 0.7:  # Footnotes are typically in bottom 30% of page
            return False
        
        # Check font size (footnotes are typically smaller)
        if font_info and self.median_font_size:
            avg_size = sum(f.get('size', 0) for f in font_info) / len(font_info)
            if avg_size > self.median_font_size * self.config.footnote_size_ratio:
                return False
        
        # Check for footnote markers
        if self.footnote_pattern.match(text):
            return True
        
        # Check for citation patterns
        if self.citation_pattern.search(text):
            return True
        
        return False
    
    def _is_caption(self, text: str, layout_type: Optional[str]) -> bool:
        """Check if text is a caption"""
        # Layout detector might identify it as a caption
        if layout_type and 'caption' in layout_type.lower():
            return True
        
        # Check for caption patterns
        if self.caption_pattern.match(text):
            return True
        
        return False
    
    def _is_list_item(self, text: str) -> bool:
        """Check if text is a list item"""
        for pattern in self.list_patterns:
            if pattern.match(text):
                return True
        return False
    
    def _is_title(self, text: str, font_info: List[Dict], layout_type: Optional[str]) -> bool:
        """Check if text is a title or heading"""
        # Layout detector might identify it as a title
        if layout_type and layout_type.lower() == 'title':
            return True
        
        # Check font size (titles are typically larger)
        if font_info and self.median_font_size:
            avg_size = sum(f.get('size', 0) for f in font_info) / len(font_info)
            if avg_size >= self.median_font_size * self.config.title_size_ratio:
                return True
        
        # Check for title indicators
        text_lower = text.lower()
        for indicator in self.title_indicators:
            if indicator in text_lower:
                return True
        
        # Check font flags (bold, italic)
        if font_info:
            for f in font_info:
                flags = f.get('flags', 0)
                if flags & 2**4:  # Bold flag
                    return True
        
        # Short lines that are all caps might be headings
        if len(text) < 100 and text.isupper() and len(text.split()) <= 10:
            return True
        
        return False
    
    def post_process_classification(self, results: Dict):
        """Post-process classification results to fix common errors"""
        try:
            # Merge nearby text blocks of the same type
            self._merge_nearby_blocks(results)
            
            # Fix misclassified headers/footers
            self._fix_header_footer_classification(results)
            
            # Establish reading order
            self._establish_reading_order(results)
            
        except Exception as e:
            logger.error(f"Post-processing failed: {e}")
    
    def _merge_nearby_blocks(self, results: Dict):
        """Merge text blocks that are very close together"""
        for content_type in ['text_blocks', 'titles', 'captions']:
            blocks = results['content'].get(content_type, [])
            if len(blocks) <= 1:
                continue
            
            # Sort by page and position
            blocks.sort(key=lambda x: (x['page'], x['bbox'][1]))
            
            merged = []
            i = 0
            while i < len(blocks):
                current = blocks[i]
                
                # Look for blocks to merge with current
                merge_group = [current]
                j = i + 1
                
                while j < len(blocks):
                    next_block = blocks[j]
                    
                    # Must be on same page
                    if next_block['page'] != current['page']:
                        break
                    
                    # Must be close vertically
                    vertical_gap = next_block['bbox'][1] - current['bbox'][3]
                    if vertical_gap > self.config.text_merge_threshold:
                        break
                    
                    # Must have similar horizontal alignment
                    current_x = current['bbox'][0]
                    next_x = next_block['bbox'][0]
                    if abs(current_x - next_x) > 20:  # Allow some variance
                        break
                    
                    merge_group.append(next_block)
                    current = next_block
                    j += 1
                
                # Merge the group
                if len(merge_group) == 1:
                    merged.append(merge_group[0])
                else:
                    merged_block = self._merge_text_group(merge_group)
                    merged.append(merged_block)
                
                i = j
            
            results['content'][content_type] = merged
    
    def _merge_text_group(self, blocks: List[Dict]) -> Dict:
        """Merge a group of text blocks"""
        # Combine text
        texts = [block['text'] for block in blocks]
        combined_text = ' '.join(texts)
        
        # Calculate combined bounding box
        min_x = min(block['bbox'][0] for block in blocks)
        min_y = min(block['bbox'][1] for block in blocks)
        max_x = max(block['bbox'][2] for block in blocks)
        max_y = max(block['bbox'][3] for block in blocks)
        
        # Use properties from first block
        merged = blocks[0].copy()
        merged['text'] = combined_text
        merged['bbox'] = [min_x, min_y, max_x, max_y]
        merged['merged_from'] = len(blocks)
        
        return merged
    
    def _fix_header_footer_classification(self, results: Dict):
        """Fix common header/footer misclassifications"""
        # Look for repeated text that should be headers/footers
        all_text_blocks = []
        for content_type in ['text_blocks', 'headers', 'footers']:
            all_text_blocks.extend(results['content'].get(content_type, []))
        
        # Group by text content
        text_groups = {}
        for block in all_text_blocks:
            text = block['text'].strip()
            if len(text) < 5:  # Skip very short text
                continue
            
            if text not in text_groups:
                text_groups[text] = []
            text_groups[text].append(block)
        
        # Find repeated text (appears on multiple pages)
        for text, blocks in text_groups.items():
            if len(blocks) >= 3:  # Appears on at least 3 pages
                # Check if all instances are in header/footer regions
                in_header_footer = all(
                    self._is_header_footer(block['bbox'], {'height': 800})  # Approximate page height
                    for block in blocks
                )
                
                if in_header_footer:
                    # Move to headers or footers
                    avg_y = sum(block['bbox'][1] for block in blocks) / len(blocks)
                    target_type = 'headers' if avg_y < 100 else 'footers'
                    
                    # Remove from current locations
                    for content_type in ['text_blocks', 'headers', 'footers']:
                        results['content'][content_type] = [
                            block for block in results['content'].get(content_type, [])
                            if block['text'].strip() != text
                        ]
                    
                    # Add to target type
                    for block in blocks:
                        block['type'] = target_type[:-1]  # Remove 's'
                        results['content'][target_type].append(block)
    
    def _establish_reading_order(self, results: Dict):
        """Establish reading order for text blocks"""
        if not self.config.preserve_reading_order:
            return
        
        # Sort all text content by page and position
        for content_type in results['content'].values():
            if isinstance(content_type, list):
                content_type.sort(key=lambda x: (
                    x.get('page', 0),
                    x.get('bbox', [0, 0, 0, 0])[1],  # Y position
                    x.get('bbox', [0, 0, 0, 0])[0]   # X position
                ))
