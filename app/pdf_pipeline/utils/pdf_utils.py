"""
PDF utility functions for the processing pipeline
"""

import logging
from typing import List, Dict, Tuple, Optional, Union
import statistics
import re

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)


class PDFUtils:
    """
    Utility functions for PDF processing operations.
    
    Provides common operations for analyzing PDF structure,
    coordinate transformations, and content validation.
    """
    
    def __init__(self):
        if not fitz:
            raise ImportError("PyMuPDF is required for PDF utilities")
    
    @staticmethod
    def get_page_dimensions(page) -> Dict[str, float]:
        """Get page dimensions and properties"""
        rect = page.rect
        return {
            'width': rect.width,
            'height': rect.height,
            'x0': rect.x0,
            'y0': rect.y0,
            'x1': rect.x1,
            'y1': rect.y1
        }
    
    @staticmethod
    def normalize_bbox(bbox: List[float], page_rect) -> List[float]:
        """Normalize bounding box coordinates to page dimensions"""
        page_width = page_rect.width
        page_height = page_rect.height
        
        return [
            bbox[0] / page_width,   # x0
            bbox[1] / page_height,  # y0
            bbox[2] / page_width,   # x1
            bbox[3] / page_height   # y1
        ]
    
    @staticmethod
    def denormalize_bbox(normalized_bbox: List[float], page_rect) -> List[float]:
        """Convert normalized coordinates back to absolute coordinates"""
        page_width = page_rect.width
        page_height = page_rect.height
        
        return [
            normalized_bbox[0] * page_width,   # x0
            normalized_bbox[1] * page_height,  # y0
            normalized_bbox[2] * page_width,   # x1
            normalized_bbox[3] * page_height   # y1
        ]
    
    @staticmethod
    def bbox_area(bbox: List[float]) -> float:
        """Calculate area of bounding box"""
        return abs((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    
    @staticmethod
    def bbox_overlap(bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate overlap area between two bounding boxes"""
        x_overlap = max(0, min(bbox1[2], bbox2[2]) - max(bbox1[0], bbox2[0]))
        y_overlap = max(0, min(bbox1[3], bbox2[3]) - max(bbox1[1], bbox2[1]))
        return x_overlap * y_overlap
    
    @staticmethod
    def bbox_overlap_ratio(bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate overlap ratio (intersection over union)"""
        intersection = PDFUtils.bbox_overlap(bbox1, bbox2)
        if intersection == 0:
            return 0.0
        
        area1 = PDFUtils.bbox_area(bbox1)
        area2 = PDFUtils.bbox_area(bbox2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def bbox_distance(bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate minimum distance between two bounding boxes"""
        # Calculate distance between closest edges
        dx = max(0, max(bbox1[0] - bbox2[2], bbox2[0] - bbox1[2]))
        dy = max(0, max(bbox1[1] - bbox2[3], bbox2[1] - bbox1[3]))
        return (dx**2 + dy**2)**0.5
    
    @staticmethod
    def bbox_center(bbox: List[float]) -> Tuple[float, float]:
        """Get center point of bounding box"""
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    
    @staticmethod
    def expand_bbox(bbox: List[float], margin: float) -> List[float]:
        """Expand bounding box by margin on all sides"""
        return [
            bbox[0] - margin,
            bbox[1] - margin,
            bbox[2] + margin,
            bbox[3] + margin
        ]
    
    @staticmethod
    def merge_bboxes(bboxes: List[List[float]]) -> List[float]:
        """Merge multiple bounding boxes into one encompassing box"""
        if not bboxes:
            return [0, 0, 0, 0]
        
        min_x = min(bbox[0] for bbox in bboxes)
        min_y = min(bbox[1] for bbox in bboxes)
        max_x = max(bbox[2] for bbox in bboxes)
        max_y = max(bbox[3] for bbox in bboxes)
        
        return [min_x, min_y, max_x, max_y]
    
    @staticmethod
    def is_bbox_inside(inner_bbox: List[float], outer_bbox: List[float], 
                      tolerance: float = 0.0) -> bool:
        """Check if one bounding box is inside another"""
        return (inner_bbox[0] >= outer_bbox[0] - tolerance and
                inner_bbox[1] >= outer_bbox[1] - tolerance and
                inner_bbox[2] <= outer_bbox[2] + tolerance and
                inner_bbox[3] <= outer_bbox[3] + tolerance)
    
    @staticmethod
    def analyze_text_properties(page) -> Dict:
        """Analyze text properties across a page"""
        text_dict = page.get_text("dict")
        
        font_sizes = []
        font_names = []
        text_lengths = []
        colors = []
        
        for block in text_dict.get("blocks", []):
            if block.get("type", 0) == 1:  # Skip image blocks
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        font_sizes.append(span.get("size", 0))
                        font_names.append(span.get("font", ""))
                        text_lengths.append(len(text))
                        colors.append(span.get("color", 0))
        
        properties = {
            'total_text_spans': len(font_sizes),
            'unique_fonts': len(set(font_names)) if font_names else 0,
            'unique_colors': len(set(colors)) if colors else 0
        }
        
        if font_sizes:
            properties.update({
                'min_font_size': min(font_sizes),
                'max_font_size': max(font_sizes),
                'median_font_size': statistics.median(font_sizes),
                'font_size_std': statistics.stdev(font_sizes) if len(font_sizes) > 1 else 0
            })
        
        if text_lengths:
            properties.update({
                'min_text_length': min(text_lengths),
                'max_text_length': max(text_lengths),
                'median_text_length': statistics.median(text_lengths),
                'total_characters': sum(text_lengths)
            })
        
        return properties
    
    @staticmethod
    def detect_reading_order(text_blocks: List[Dict]) -> List[Dict]:
        """Detect and establish reading order for text blocks"""
        if not text_blocks:
            return text_blocks
        
        # Group by page first
        pages = {}
        for block in text_blocks:
            page_num = block.get('page', 0)
            if page_num not in pages:
                pages[page_num] = []
            pages[page_num].append(block)
        
        # Sort within each page
        ordered_blocks = []
        for page_num in sorted(pages.keys()):
            page_blocks = pages[page_num]
            
            # Detect columns
            columns = PDFUtils._detect_columns(page_blocks)
            
            if len(columns) > 1:
                # Multi-column layout - sort by column, then by Y position
                for column in columns:
                    column_blocks = sorted(column, key=lambda x: x.get('bbox', [0, 0, 0, 0])[1])
                    ordered_blocks.extend(column_blocks)
            else:
                # Single column - sort by Y position, then X position
                page_blocks.sort(key=lambda x: (
                    x.get('bbox', [0, 0, 0, 0])[1],  # Y position
                    x.get('bbox', [0, 0, 0, 0])[0]   # X position
                ))
                ordered_blocks.extend(page_blocks)
        
        # Add reading order indices
        for i, block in enumerate(ordered_blocks):
            block['reading_order'] = i
        
        return ordered_blocks
    
    @staticmethod
    def _detect_columns(text_blocks: List[Dict]) -> List[List[Dict]]:
        """Detect column layout in text blocks"""
        if not text_blocks:
            return []
        
        # Get X positions of all blocks
        x_positions = [block.get('bbox', [0, 0, 0, 0])[0] for block in text_blocks]
        
        if not x_positions:
            return [text_blocks]
        
        # Simple column detection based on X position clustering
        x_positions.sort()
        
        # Find gaps in X positions that might indicate column boundaries
        gaps = []
        for i in range(1, len(x_positions)):
            gap = x_positions[i] - x_positions[i-1]
            if gap > 50:  # Arbitrary threshold for column gap
                gaps.append((x_positions[i-1], x_positions[i]))
        
        if not gaps:
            return [text_blocks]  # Single column
        
        # Group blocks by columns
        columns = []
        
        # First column
        first_column = [block for block in text_blocks 
                       if block.get('bbox', [0, 0, 0, 0])[0] < gaps[0][1]]
        if first_column:
            columns.append(first_column)
        
        # Middle columns
        for i in range(len(gaps) - 1):
            column = [block for block in text_blocks 
                     if gaps[i][1] <= block.get('bbox', [0, 0, 0, 0])[0] < gaps[i+1][1]]
            if column:
                columns.append(column)
        
        # Last column
        last_column = [block for block in text_blocks 
                      if block.get('bbox', [0, 0, 0, 0])[0] >= gaps[-1][1]]
        if last_column:
            columns.append(last_column)
        
        return columns if len(columns) > 1 else [text_blocks]
    
    @staticmethod
    def validate_pdf_structure(document) -> Dict:
        """Validate PDF structure and identify potential issues"""
        validation_report = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'metadata': {}
        }
        
        try:
            # Basic metadata
            validation_report['metadata'] = {
                'page_count': document.page_count,
                'is_encrypted': document.is_encrypted,
                'is_pdf': document.is_pdf,
                'metadata': document.metadata
            }
            
            # Check for empty pages
            empty_pages = []
            for page_num in range(document.page_count):
                page = document[page_num]
                text = page.get_text().strip()
                if not text:
                    empty_pages.append(page_num)
            
            if empty_pages:
                validation_report['warnings'].append(
                    f"Empty pages found: {empty_pages}"
                )
            
            # Check for scanned pages (pages with images but no text)
            scanned_pages = []
            for page_num in range(min(10, document.page_count)):  # Check first 10 pages
                page = document[page_num]
                text = page.get_text().strip()
                images = page.get_images()
                
                if not text and images:
                    scanned_pages.append(page_num)
            
            if scanned_pages:
                validation_report['warnings'].append(
                    f"Likely scanned pages found: {scanned_pages}"
                )
            
            # Check for very large pages (might indicate unusual format)
            large_pages = []
            for page_num in range(document.page_count):
                page = document[page_num]
                rect = page.rect
                if rect.width > 2000 or rect.height > 2000:  # Arbitrary threshold
                    large_pages.append(page_num)
            
            if large_pages:
                validation_report['warnings'].append(
                    f"Unusually large pages found: {large_pages}"
                )
            
        except Exception as e:
            validation_report['is_valid'] = False
            validation_report['issues'].append(f"Validation error: {str(e)}")
        
        return validation_report
    
    @staticmethod
    def estimate_processing_complexity(document) -> Dict:
        """Estimate processing complexity of a PDF document"""
        complexity = {
            'overall_score': 0,
            'factors': {},
            'recommendations': []
        }
        
        try:
            # Sample first few pages for analysis
            sample_size = min(5, document.page_count)
            
            total_images = 0
            total_text_blocks = 0
            total_tables = 0
            font_diversity = set()
            
            for page_num in range(sample_size):
                page = document[page_num]
                
                # Count images
                images = page.get_images()
                total_images += len(images)
                
                # Analyze text structure
                text_dict = page.get_text("dict")
                blocks = text_dict.get("blocks", [])
                text_blocks = [b for b in blocks if b.get("type", 0) == 0]
                total_text_blocks += len(text_blocks)
                
                # Collect font information
                for block in text_blocks:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_diversity.add(span.get("font", ""))
                
                # Try to detect tables
                try:
                    tables = page.find_tables()
                    total_tables += len(tables.tables)
                except:
                    pass
            
            # Calculate complexity factors
            complexity['factors'] = {
                'page_count': document.page_count,
                'avg_images_per_page': total_images / sample_size,
                'avg_text_blocks_per_page': total_text_blocks / sample_size,
                'avg_tables_per_page': total_tables / sample_size,
                'font_diversity': len(font_diversity),
                'is_likely_scanned': total_text_blocks < (sample_size * 2)  # Very few text blocks
            }
            
            # Calculate overall complexity score (0-100)
            score = 0
            
            # Page count factor
            if document.page_count > 100:
                score += 20
            elif document.page_count > 50:
                score += 10
            elif document.page_count > 20:
                score += 5
            
            # Content complexity
            if complexity['factors']['avg_images_per_page'] > 5:
                score += 15
            elif complexity['factors']['avg_images_per_page'] > 2:
                score += 10
            
            if complexity['factors']['avg_tables_per_page'] > 2:
                score += 15
            elif complexity['factors']['avg_tables_per_page'] > 0.5:
                score += 10
            
            if complexity['factors']['font_diversity'] > 20:
                score += 15
            elif complexity['factors']['font_diversity'] > 10:
                score += 10
            
            if complexity['factors']['is_likely_scanned']:
                score += 25
                complexity['recommendations'].append("Document appears to be scanned - OCR will be required")
            
            # Text density
            if complexity['factors']['avg_text_blocks_per_page'] > 50:
                score += 10
                complexity['recommendations'].append("High text density detected - processing may take longer")
            
            complexity['overall_score'] = min(100, score)
            
            # Add processing recommendations
            if complexity['overall_score'] > 70:
                complexity['recommendations'].append("High complexity document - enable all processing options")
            elif complexity['overall_score'] > 40:
                complexity['recommendations'].append("Medium complexity document - standard processing recommended")
            else:
                complexity['recommendations'].append("Low complexity document - fast processing possible")
            
        except Exception as e:
            complexity['factors']['error'] = str(e)
        
        return complexity
