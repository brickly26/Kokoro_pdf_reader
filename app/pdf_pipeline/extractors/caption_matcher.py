"""
Caption matching for figures and tables in PDF documents
"""

import logging
import re
from typing import List, Dict, Optional, Tuple, Set
import math

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class CaptionMatcher:
    """
    Matches captions with their corresponding figures and tables.
    
    Uses spatial analysis and text patterns to associate captions
    with nearby visual elements.
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        # Compile caption patterns
        self._compile_patterns()
        
    def _compile_patterns(self):
        """Compile regex patterns for caption detection"""
        # Basic caption patterns
        keywords = '|'.join(self.config.caption_keywords)
        
        self.caption_patterns = [
            re.compile(rf'^\\s*({keywords})\\s+(\\d+[\\w\\.]*)[:\\.\\s]', re.IGNORECASE),  # "Figure 1:"
            re.compile(rf'^\\s*({keywords})\\s+(\\d+[\\w\\.]*)', re.IGNORECASE),          # "Figure 1"
            re.compile(rf'({keywords})\\s+(\\d+[\\w\\.]*)[:\\.\\s]', re.IGNORECASE),      # "Figure 1:" anywhere
        ]
        
        # More specific patterns for different types
        self.figure_patterns = [
            re.compile(r'^\\s*(fig|figure)\\s+(\\d+[\\w\\.]*)', re.IGNORECASE),
            re.compile(r'^\\s*(fig|figure)\\s*[:\\.\\s]', re.IGNORECASE),
        ]
        
        self.table_patterns = [
            re.compile(r'^\\s*(tab|table)\\s+(\\d+[\\w\\.]*)', re.IGNORECASE),
            re.compile(r'^\\s*(tab|table)\\s*[:\\.\\s]', re.IGNORECASE),
        ]
        
        self.equation_patterns = [
            re.compile(r'^\\s*(eq|equation)\\s+(\\d+[\\w\\.]*)', re.IGNORECASE),
            re.compile(r'^\\s*(eq|equation)\\s*[:\\.\\s]', re.IGNORECASE),
        ]
        
        # Algorithm and listing patterns
        self.algorithm_patterns = [
            re.compile(r'^\\s*(alg|algorithm)\\s+(\\d+[\\w\\.]*)', re.IGNORECASE),
            re.compile(r'^\\s*(listing)\\s+(\\d+[\\w\\.]*)', re.IGNORECASE),
        ]
    
    def match_captions(self, results: Dict):
        """
        Match captions with their corresponding visual elements.
        
        Args:
            results: Results dictionary containing all extracted content
        """
        try:
            # Get all potential captions and visual elements
            captions = results['content'].get('captions', [])
            text_blocks = results['content'].get('text_blocks', [])
            
            # Find additional captions in text blocks
            additional_captions = self._find_captions_in_text(text_blocks)
            all_captions = captions + additional_captions
            
            # Get visual elements to match
            figures = results['content'].get('figures', [])
            images = results['content'].get('images', [])
            tables = results['content'].get('tables', [])
            formulas = results['content'].get('formulas', [])
            
            # Combine figures and images for matching
            visual_elements = []
            visual_elements.extend([{**fig, 'element_type': 'figure'} for fig in figures])
            visual_elements.extend([{**img, 'element_type': 'image'} for img in images])
            visual_elements.extend([{**tbl, 'element_type': 'table'} for tbl in tables])
            visual_elements.extend([{**frm, 'element_type': 'formula'} for frm in formulas])
            
            # Perform matching
            matches = self._perform_caption_matching(all_captions, visual_elements)
            
            # Update results with matches
            self._update_results_with_matches(results, matches)
            
            logger.debug(f"Matched {len(matches)} captions with visual elements")
            
        except Exception as e:
            logger.error(f"Caption matching failed: {e}")
    
    def _find_captions_in_text(self, text_blocks: List[Dict]) -> List[Dict]:
        """Find caption-like text in regular text blocks"""
        captions = []
        
        for block in text_blocks:
            text = block.get('text', '')
            
            # Check if text matches caption patterns
            caption_info = self._analyze_text_for_caption(text)
            if caption_info:
                caption_entry = {
                    'type': 'caption',
                    'text': text,
                    'page': block.get('page'),
                    'bbox': block.get('bbox'),
                    'caption_type': caption_info['caption_type'],
                    'caption_number': caption_info.get('number'),
                    'source': 'text_analysis',
                    'original_block': block
                }
                captions.append(caption_entry)
        
        return captions
    
    def _analyze_text_for_caption(self, text: str) -> Optional[Dict]:
        """Analyze text to determine if it's a caption"""
        text_stripped = text.strip()
        
        # Skip very long text (unlikely to be captions)
        if len(text_stripped) > 500:
            return None
        
        # Check each pattern type
        for pattern in self.figure_patterns:
            match = pattern.search(text_stripped)
            if match:
                return {
                    'caption_type': 'figure',
                    'number': match.group(2) if match.lastindex >= 2 else None
                }
        
        for pattern in self.table_patterns:
            match = pattern.search(text_stripped)
            if match:
                return {
                    'caption_type': 'table',
                    'number': match.group(2) if match.lastindex >= 2 else None
                }
        
        for pattern in self.equation_patterns:
            match = pattern.search(text_stripped)
            if match:
                return {
                    'caption_type': 'equation',
                    'number': match.group(2) if match.lastindex >= 2 else None
                }
        
        for pattern in self.algorithm_patterns:
            match = pattern.search(text_stripped)
            if match:
                return {
                    'caption_type': 'algorithm',
                    'number': match.group(2) if match.lastindex >= 2 else None
                }
        
        # Check general caption patterns
        for pattern in self.caption_patterns:
            match = pattern.search(text_stripped)
            if match:
                return {
                    'caption_type': match.group(1).lower(),
                    'number': match.group(2) if match.lastindex >= 2 else None
                }
        
        return None
    
    def _perform_caption_matching(self, captions: List[Dict], visual_elements: List[Dict]) -> List[Dict]:
        """Perform spatial matching between captions and visual elements"""
        matches = []
        used_elements = set()
        used_captions = set()
        
        # Sort captions and elements by page and position for better matching
        captions.sort(key=lambda x: (x.get('page', 0), x.get('bbox', [0, 0, 0, 0])[1]))
        visual_elements.sort(key=lambda x: (x.get('page', 0), x.get('bbox', [0, 0, 0, 0])[1]))
        
        for i, caption in enumerate(captions):
            if i in used_captions:
                continue
            
            caption_type = caption.get('caption_type')
            caption_bbox = caption.get('bbox')
            caption_page = caption.get('page')
            
            if not caption_bbox or caption_page is None:
                continue
            
            # Find best matching visual element
            best_match = None
            best_score = 0
            best_element_idx = None
            
            for j, element in enumerate(visual_elements):
                if j in used_elements:
                    continue
                
                element_bbox = element.get('bbox')
                element_page = element.get('page')
                element_type = element.get('element_type')
                
                if not element_bbox or element_page is None:
                    continue
                
                # Calculate matching score
                score = self._calculate_matching_score(
                    caption, element, caption_type, element_type
                )
                
                if score > best_score and score > 0.3:  # Minimum threshold
                    best_score = score
                    best_match = element
                    best_element_idx = j
            
            if best_match:
                match = {
                    'caption': caption,
                    'element': best_match,
                    'score': best_score,
                    'match_type': f"{caption_type}_{best_match['element_type']}"
                }
                matches.append(match)
                used_captions.add(i)
                used_elements.add(best_element_idx)
        
        return matches
    
    def _calculate_matching_score(self, caption: Dict, element: Dict, 
                                 caption_type: Optional[str], element_type: str) -> float:
        """Calculate matching score between caption and visual element"""
        score = 0
        
        caption_bbox = caption.get('bbox')
        element_bbox = element.get('bbox')
        caption_page = caption.get('page')
        element_page = element.get('page')
        
        # Must be on same page or adjacent pages
        if caption_page == element_page:
            page_score = 1.0
        elif abs(caption_page - element_page) == 1:
            page_score = 0.5
        else:
            return 0  # Too far apart
        
        score += page_score * 0.3
        
        # Calculate spatial proximity
        distance = self._calculate_bbox_distance(caption_bbox, element_bbox)
        proximity_score = max(0, 1 - (distance / self.config.caption_proximity_threshold))
        score += proximity_score * 0.4
        
        # Type matching bonus
        type_score = self._calculate_type_matching_score(caption_type, element_type)
        score += type_score * 0.3
        
        return score
    
    def _calculate_bbox_distance(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate minimum distance between two bounding boxes"""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Calculate distance between closest edges
        dx = max(0, max(x1_1 - x2_2, x1_2 - x2_1))
        dy = max(0, max(y1_1 - y2_2, y1_2 - y2_1))
        
        return math.sqrt(dx**2 + dy**2)
    
    def _calculate_type_matching_score(self, caption_type: Optional[str], element_type: str) -> float:
        """Calculate how well caption type matches element type"""
        if not caption_type:
            return 0.1  # Small bonus for any match
        
        caption_type = caption_type.lower()
        element_type = element_type.lower()
        
        # Direct matches
        type_matches = {
            'figure': ['figure', 'image'],
            'fig': ['figure', 'image'],
            'table': ['table'],
            'tab': ['table'],
            'equation': ['formula'],
            'eq': ['formula'],
            'algorithm': ['figure', 'image'],  # Algorithms often appear as images
            'listing': ['figure', 'image']
        }
        
        if caption_type in type_matches:
            if element_type in type_matches[caption_type]:
                return 1.0
        
        # Partial matches
        if 'fig' in caption_type and element_type in ['figure', 'image']:
            return 0.8
        if 'tab' in caption_type and element_type == 'table':
            return 0.8
        if 'eq' in caption_type and element_type == 'formula':
            return 0.8
        
        return 0.1  # Small bonus for any attempt
    
    def _update_results_with_matches(self, results: Dict, matches: List[Dict]):
        """Update results with caption-element matches"""
        
        # Remove matched captions from text_blocks if they came from there
        matched_text_blocks = set()
        for match in matches:
            caption = match['caption']
            if caption.get('source') == 'text_analysis':
                original_block = caption.get('original_block')
                if original_block:
                    matched_text_blocks.add(id(original_block))
        
        # Filter out matched text blocks
        if matched_text_blocks:
            results['content']['text_blocks'] = [
                block for block in results['content']['text_blocks']
                if id(block) not in matched_text_blocks
            ]
        
        # Add matched captions to the captions list
        new_captions = []
        for match in matches:
            caption = match['caption']
            element = match['element']
            
            # Enhance caption with match information
            enhanced_caption = caption.copy()
            enhanced_caption.update({
                'matched_element': {
                    'type': element['element_type'],
                    'page': element.get('page'),
                    'bbox': element.get('bbox'),
                    'id': id(element)
                },
                'match_score': match['score'],
                'match_type': match['match_type']
            })
            new_captions.append(enhanced_caption)
            
            # Add reference to caption in the element
            element['caption'] = {
                'text': caption['text'],
                'page': caption.get('page'),
                'bbox': caption.get('bbox'),
                'caption_type': caption.get('caption_type'),
                'number': caption.get('caption_number')
            }
        
        # Update captions in results
        existing_captions = results['content'].get('captions', [])
        
        # Remove captions that were matched from text analysis
        existing_captions = [
            cap for cap in existing_captions
            if not any(cap is match['caption'] for match in matches 
                      if match['caption'].get('source') != 'text_analysis')
        ]
        
        # Add new matched captions
        results['content']['captions'] = existing_captions + new_captions
        
        # Create summary of matches
        match_summary = {
            'total_matches': len(matches),
            'by_type': {},
            'unmatched_captions': 0,
            'unmatched_elements': 0
        }
        
        for match in matches:
            match_type = match['match_type']
            if match_type not in match_summary['by_type']:
                match_summary['by_type'][match_type] = 0
            match_summary['by_type'][match_type] += 1
        
        # Count unmatched items
        all_captions = results['content'].get('captions', [])
        matched_caption_ids = {id(match['caption']) for match in matches}
        match_summary['unmatched_captions'] = len([
            cap for cap in all_captions if id(cap) not in matched_caption_ids
        ])
        
        # Add summary to results metadata
        if 'caption_matching' not in results['metadata']:
            results['metadata']['caption_matching'] = {}
        results['metadata']['caption_matching'].update(match_summary)
    
    def find_orphaned_captions(self, results: Dict) -> List[Dict]:
        """Find captions that couldn't be matched to any visual element"""
        all_captions = results['content'].get('captions', [])
        orphaned = []
        
        for caption in all_captions:
            if 'matched_element' not in caption:
                orphaned.append(caption)
        
        return orphaned
    
    def find_orphaned_elements(self, results: Dict) -> List[Dict]:
        """Find visual elements that don't have associated captions"""
        orphaned = []
        
        for content_type in ['figures', 'images', 'tables', 'formulas']:
            elements = results['content'].get(content_type, [])
            for element in elements:
                if 'caption' not in element:
                    orphaned.append({**element, 'element_type': content_type[:-1]})
        
        return orphaned
