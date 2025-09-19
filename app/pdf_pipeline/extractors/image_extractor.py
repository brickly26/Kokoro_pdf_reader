"""
Image extraction from PDF documents
"""

import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import hashlib

try:
    import fitz  # PyMuPDF
    from PIL import Image
    import numpy as np
except ImportError:
    fitz = None
    Image = None
    np = None

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class ImageExtractor:
    """
    Extracts images from PDF documents with proper organization and metadata.
    
    Handles both embedded images and page-rendered images,
    with deduplication and format conversion.
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        if not fitz:
            raise ImportError("PyMuPDF is required for image extraction")
        if not Image:
            raise ImportError("PIL is required for image processing")
            
        # Create images output directory
        self.images_dir = Path(self.config.output_dir) / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Track extracted images to avoid duplicates
        self.image_hashes = set()
        self.extracted_count = 0
    
    def extract_images(self, page, page_num: int, results: Dict):
        """
        Extract all images from a PDF page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (0-indexed)
            results: Results dictionary to update
        """
        if not self.config.image_extraction_enabled:
            return
        
        try:
            # Extract embedded images
            embedded_images = self._extract_embedded_images(page, page_num)
            
            # Extract vector graphics as images if needed
            vector_images = self._extract_vector_graphics(page, page_num)
            
            # Combine and process all images
            all_images = embedded_images + vector_images
            
            # Filter and save images
            for image_info in all_images:
                if self._should_save_image(image_info):
                    saved_path = self._save_image(image_info, page_num)
                    if saved_path:
                        image_entry = {
                            'type': 'image',
                            'page': page_num,
                            'bbox': image_info.get('bbox'),
                            'file_path': str(saved_path),
                            'format': image_info.get('format'),
                            'size': image_info.get('size'),
                            'dpi': image_info.get('dpi'),
                            'colorspace': image_info.get('colorspace'),
                            'is_vector': image_info.get('is_vector', False)
                        }
                        results['content']['images'].append(image_entry)
                        results['artifacts']['images'].append(str(saved_path))
            
            logger.debug(f"Extracted {len(all_images)} images from page {page_num}")
            
        except Exception as e:
            logger.error(f"Image extraction failed for page {page_num}: {e}")
    
    def _extract_embedded_images(self, page, page_num: int) -> List[Dict]:
        """Extract embedded raster images from the page"""
        images = []
        
        try:
            # Get image list from page
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]  # Cross-reference number
                
                # Extract image data
                base_image = page.parent.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Get image info
                image_info = page.get_image_info()
                bbox = None
                for info in image_info:
                    if info.get("xref") == xref:
                        bbox = info.get("bbox")
                        break
                
                # Create PIL Image to get additional info
                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    size = pil_image.size
                    format_name = pil_image.format or image_ext
                    colorspace = pil_image.mode
                except Exception:
                    size = (base_image.get("width", 0), base_image.get("height", 0))
                    format_name = image_ext
                    colorspace = "unknown"
                
                image_data = {
                    'bytes': image_bytes,
                    'format': format_name.lower(),
                    'size': size,
                    'bbox': bbox,
                    'colorspace': colorspace,
                    'xref': xref,
                    'is_vector': False,
                    'page_index': img_index
                }
                
                images.append(image_data)
                
        except Exception as e:
            logger.warning(f"Failed to extract embedded images from page {page_num}: {e}")
        
        return images
    
    def _extract_vector_graphics(self, page, page_num: int) -> List[Dict]:
        """Extract vector graphics by rendering specific regions"""
        images = []
        
        if not self.config.save_image_formats or 'vector' not in self.config.save_image_formats:
            return images
        
        try:
            # Look for drawing objects that might be vector graphics
            drawings = page.get_drawings()
            
            if not drawings:
                return images
            
            # Group nearby drawings into regions
            regions = self._group_drawings_into_regions(drawings)
            
            for i, region in enumerate(regions):
                # Render this region as an image
                clip_rect = fitz.Rect(region['bbox'])
                
                # Add some padding
                padding = 10
                clip_rect.x0 -= padding
                clip_rect.y0 -= padding
                clip_rect.x1 += padding
                clip_rect.y1 += padding
                
                # Ensure clip rect is within page bounds
                page_rect = page.rect
                clip_rect &= page_rect
                
                if clip_rect.is_empty:
                    continue
                
                # Render the region
                mat = fitz.Matrix(self.config.image_dpi / 72, self.config.image_dpi / 72)
                pix = page.get_pixmap(matrix=mat, clip=clip_rect)
                
                if pix.width < self.config.min_image_size[0] or pix.height < self.config.min_image_size[1]:
                    continue
                
                image_data = {
                    'bytes': pix.tobytes("png"),
                    'format': 'png',
                    'size': (pix.width, pix.height),
                    'bbox': list(clip_rect),
                    'colorspace': 'RGB',
                    'is_vector': True,
                    'dpi': self.config.image_dpi,
                    'drawing_count': len(region['drawings'])
                }
                
                images.append(image_data)
                
        except Exception as e:
            logger.warning(f"Failed to extract vector graphics from page {page_num}: {e}")
        
        return images
    
    def _group_drawings_into_regions(self, drawings) -> List[Dict]:
        """Group nearby drawings into image regions"""
        if not drawings:
            return []
        
        # Convert drawings to bounding boxes
        drawing_boxes = []
        for drawing in drawings:
            items = drawing.get("items", [])
            if not items:
                continue
            
            # Find bounding box of all items in this drawing
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            
            for item in items:
                if "rect" in item:
                    rect = item["rect"]
                    min_x = min(min_x, rect.x0)
                    min_y = min(min_y, rect.y0)
                    max_x = max(max_x, rect.x1)
                    max_y = max(max_y, rect.y1)
            
            if min_x != float('inf'):
                drawing_boxes.append({
                    'bbox': [min_x, min_y, max_x, max_y],
                    'drawing': drawing
                })
        
        # Group overlapping or nearby boxes
        regions = []
        used = set()
        
        for i, box1 in enumerate(drawing_boxes):
            if i in used:
                continue
            
            region_drawings = [box1['drawing']]
            region_bbox = box1['bbox'][:]
            used.add(i)
            
            # Find nearby drawings
            for j, box2 in enumerate(drawing_boxes[i+1:], i+1):
                if j in used:
                    continue
                
                if self._are_boxes_nearby(region_bbox, box2['bbox'], threshold=50):
                    region_drawings.append(box2['drawing'])
                    # Expand region bbox
                    region_bbox[0] = min(region_bbox[0], box2['bbox'][0])
                    region_bbox[1] = min(region_bbox[1], box2['bbox'][1])
                    region_bbox[2] = max(region_bbox[2], box2['bbox'][2])
                    region_bbox[3] = max(region_bbox[3], box2['bbox'][3])
                    used.add(j)
            
            regions.append({
                'bbox': region_bbox,
                'drawings': region_drawings
            })
        
        return regions
    
    def _are_boxes_nearby(self, bbox1: List[float], bbox2: List[float], threshold: float) -> bool:
        """Check if two bounding boxes are nearby"""
        # Calculate minimum distance between boxes
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Check for overlap first
        if not (x2_1 < x1_2 or x2_2 < x1_1 or y2_1 < y1_2 or y2_2 < y1_1):
            return True
        
        # Calculate distance between closest edges
        dx = max(0, max(x1_1 - x2_2, x1_2 - x2_1))
        dy = max(0, max(y1_1 - y2_2, y1_2 - y2_1))
        distance = (dx**2 + dy**2)**0.5
        
        return distance <= threshold
    
    def _should_save_image(self, image_info: Dict) -> bool:
        """Determine if an image should be saved"""
        # Check minimum size
        size = image_info.get('size', (0, 0))
        if size[0] < self.config.min_image_size[0] or size[1] < self.config.min_image_size[1]:
            return False
        
        # Check for duplicates using hash
        image_bytes = image_info.get('bytes')
        if image_bytes:
            image_hash = hashlib.md5(image_bytes).hexdigest()
            if image_hash in self.image_hashes:
                return False
            self.image_hashes.add(image_hash)
        
        return True
    
    def _save_image(self, image_info: Dict, page_num: int) -> Optional[Path]:
        """Save an image to disk"""
        try:
            # Determine file extension
            format_name = image_info.get('format', 'png')
            if format_name not in self.config.save_image_formats:
                # Convert to preferred format
                format_name = self.config.save_image_formats[0]
            
            # Generate filename
            self.extracted_count += 1
            if image_info.get('is_vector'):
                filename = f"page_{page_num:03d}_vector_{self.extracted_count:03d}.{format_name}"
            else:
                filename = f"page_{page_num:03d}_image_{self.extracted_count:03d}.{format_name}"
            
            file_path = self.images_dir / filename
            
            # Save image
            image_bytes = image_info.get('bytes')
            if image_bytes:
                if format_name == image_info.get('format'):
                    # Save directly
                    with open(file_path, 'wb') as f:
                        f.write(image_bytes)
                else:
                    # Convert format
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    pil_image.save(file_path, format=format_name.upper())
            
            logger.debug(f"Saved image: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            return None


# Add missing import
import io
