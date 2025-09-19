"""
Layout detection using PubLayNet via layoutparser
"""

import logging
from typing import List, Dict, Optional, Tuple

try:
    import layoutparser as lp
    import torch
    from PIL import Image
    import cv2
    import numpy as np
    LAYOUT_AVAILABLE = True
except ImportError:
    LAYOUT_AVAILABLE = False
    # Create dummy imports for type hints
    class np:
        class ndarray:
            pass
    class lp:
        pass
    class torch:
        pass
    class Image:
        pass
    class cv2:
        pass

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class LayoutDetector:
    """
    Detects page layout regions using deep learning models.
    
    Supports PubLayNet model for academic document layout detection.
    Categories: Text, Title, List, Table, Figure
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.model = None
        
        if not LAYOUT_AVAILABLE:
            raise ImportError(
                "Layout detection requires: layoutparser, torch, PIL, opencv-python. "
                "Install with: pip install layoutparser torch pillow opencv-python"
            )
        
        if self.config.use_layout_detection:
            self._load_model()
    
    def _load_model(self):
        """Load the layout detection model"""
        try:
            if self.config.layout_model == "PubLayNet":
                # PubLayNet model for academic papers
                model_config = "lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config"
                self.model = lp.Detectron2LayoutModel(
                    config_path=model_config,
                    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", self.config.layout_confidence_threshold],
                    label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}
                )
                logger.info("Loaded PubLayNet model for layout detection")
            elif self.config.layout_model == "TableBank":
                # TableBank model specifically for table detection
                model_config = "lp://TableBank/faster_rcnn_R_50_FPN_3x/config"
                self.model = lp.Detectron2LayoutModel(
                    config_path=model_config,
                    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", self.config.layout_confidence_threshold],
                    label_map={0: "Table"}
                )
                logger.info("Loaded TableBank model for table detection")
            else:
                logger.warning(f"Unknown layout model: {self.config.layout_model}")
                
        except Exception as e:
            logger.error(f"Failed to load layout model: {e}")
            self.model = None
    
    def detect_layout(self, page, page_num: int) -> List[Dict]:
        """
        Detect layout regions on a PDF page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (0-indexed)
            
        Returns:
            List of detected regions with bounding boxes and types
        """
        if not self.model:
            logger.warning("Layout model not available, skipping layout detection")
            return []
        
        try:
            # Convert page to image
            page_image = self._page_to_image(page)
            if page_image is None:
                return []
            
            # Run layout detection
            layout_result = self.model.detect(page_image)
            
            # Convert results to our format
            regions = []
            for element in layout_result:
                region = {
                    'type': element.type,
                    'confidence': float(element.score) if hasattr(element, 'score') else 1.0,
                    'bbox': [float(element.x_1), float(element.y_1), 
                            float(element.x_2), float(element.y_2)],
                    'page': page_num,
                    'area': float((element.x_2 - element.x_1) * (element.y_2 - element.y_1))
                }
                regions.append(region)
            
            logger.debug(f"Detected {len(regions)} layout regions on page {page_num}")
            return regions
            
        except Exception as e:
            logger.error(f"Layout detection failed for page {page_num}: {e}")
            return []
    
    def _page_to_image(self, page) -> Optional[np.ndarray]:
        """Convert PDF page to image for layout detection"""
        try:
            # Get page as pixmap
            mat = page.get_pixmap(matrix=page.get_transformation(), dpi=150)
            
            # Convert to PIL Image
            img_data = mat.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # Convert to numpy array (RGB format)
            image_array = np.array(pil_image)
            
            return image_array
            
        except Exception as e:
            logger.error(f"Failed to convert page to image: {e}")
            return None
    
    def get_region_by_point(self, regions: List[Dict], x: float, y: float) -> Optional[Dict]:
        """Find which region contains a given point"""
        for region in regions:
            bbox = region['bbox']
            if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                return region
        return None
    
    def get_regions_by_type(self, regions: List[Dict], region_type: str) -> List[Dict]:
        """Get all regions of a specific type"""
        return [r for r in regions if r['type'].lower() == region_type.lower()]
    
    def merge_overlapping_regions(self, regions: List[Dict], overlap_threshold: float = 0.5) -> List[Dict]:
        """Merge regions that overlap significantly"""
        if not regions:
            return []
        
        merged = []
        used = set()
        
        for i, region1 in enumerate(regions):
            if i in used:
                continue
                
            current_group = [region1]
            used.add(i)
            
            for j, region2 in enumerate(regions[i+1:], i+1):
                if j in used:
                    continue
                
                if self._calculate_overlap(region1['bbox'], region2['bbox']) > overlap_threshold:
                    current_group.append(region2)
                    used.add(j)
            
            # Merge the group
            if len(current_group) == 1:
                merged.append(current_group[0])
            else:
                merged_region = self._merge_region_group(current_group)
                merged.append(merged_region)
        
        return merged
    
    def _calculate_overlap(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate overlap ratio between two bounding boxes"""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Calculate intersection
        x_overlap = max(0, min(x2_1, x2_2) - max(x1_1, x1_2))
        y_overlap = max(0, min(y2_1, y2_2) - max(y1_1, y1_2))
        intersection = x_overlap * y_overlap
        
        # Calculate union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _merge_region_group(self, regions: List[Dict]) -> Dict:
        """Merge a group of overlapping regions"""
        # Find bounding box that encompasses all regions
        min_x = min(r['bbox'][0] for r in regions)
        min_y = min(r['bbox'][1] for r in regions)
        max_x = max(r['bbox'][2] for r in regions)
        max_y = max(r['bbox'][3] for r in regions)
        
        # Use the type of the largest region
        largest_region = max(regions, key=lambda r: r['area'])
        
        # Average the confidence scores
        avg_confidence = sum(r['confidence'] for r in regions) / len(regions)
        
        return {
            'type': largest_region['type'],
            'confidence': avg_confidence,
            'bbox': [min_x, min_y, max_x, max_y],
            'page': largest_region['page'],
            'area': (max_x - min_x) * (max_y - min_y),
            'merged_from': len(regions)
        }


# Add missing import
import io
