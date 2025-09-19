"""
Configuration class for PDF processing pipeline
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import os


@dataclass
class ProcessingConfig:
    """Configuration for PDF processing pipeline"""
    
    # Output settings
    output_dir: str = "output"
    create_main_text: bool = True
    create_manifest: bool = True
    save_images: bool = True
    save_tables: bool = True
    
    # Layout detection settings
    use_layout_detection: bool = True
    layout_model: str = "PubLayNet"  # "PubLayNet" or "TableBank"
    layout_confidence_threshold: float = 0.7
    
    # Page region thresholds
    header_region_threshold: float = 0.1  # Top 10% of page
    footer_region_threshold: float = 0.9  # Bottom 10% of page
    margin_threshold: float = 0.05  # 5% margins
    
    # Text classification thresholds
    min_text_size: float = 8.0  # Minimum font size for body text
    title_size_ratio: float = 1.3  # Title must be 1.3x larger than median
    footnote_size_ratio: float = 0.9  # Footnotes are 90% of median size
    
    # Table extraction settings
    table_extraction_enabled: bool = True
    table_detection_method: str = "camelot"  # "camelot", "tabula", or "both"
    camelot_flavor: str = "lattice"  # "lattice" or "stream"
    table_accuracy_threshold: float = 80.0
    
    # Image extraction settings
    image_extraction_enabled: bool = True
    min_image_size: Tuple[int, int] = (50, 50)  # Minimum width, height
    image_dpi: int = 150
    save_image_formats: List[str] = field(default_factory=lambda: ["png", "jpg"])
    
    # Formula detection settings
    formula_detection_enabled: bool = True
    math_symbols: List[str] = field(default_factory=lambda: [
        "∫", "∑", "∏", "√", "∞", "α", "β", "γ", "δ", "ε", "θ", "λ", "μ", "π", "σ", "φ", "ψ", "ω",
        "±", "≤", "≥", "≠", "≈", "∝", "∂", "∇", "⊆", "⊇", "∈", "∉", "∪", "∩", "→", "←", "↔"
    ])
    math_keywords: List[str] = field(default_factory=lambda: [
        "theorem", "lemma", "proposition", "corollary", "proof", "equation", "formula"
    ])
    
    # Caption detection settings
    caption_keywords: List[str] = field(default_factory=lambda: [
        "figure", "fig", "table", "tab", "equation", "eq", "algorithm", "alg"
    ])
    caption_proximity_threshold: float = 100.0  # Max distance in points
    
    # OCR settings
    ocr_enabled: bool = True
    ocr_engine: str = "tesseract"  # "tesseract" or "easyocr"
    ocr_languages: List[str] = field(default_factory=lambda: ["eng"])
    ocr_fallback_threshold: float = 0.1  # Use OCR if <10% text extractable
    
    # Content filtering
    min_sentence_length: int = 10
    max_sentence_length: int = 1000
    exclude_headers_footers: bool = False  # Keep in manifest but mark as such
    exclude_page_numbers: bool = False
    
    # Processing options
    parallel_processing: bool = True
    max_workers: Optional[int] = None  # Use CPU count if None
    verbose: bool = False
    debug: bool = False
    
    # Advanced options
    preserve_reading_order: bool = True
    detect_columns: bool = True
    merge_nearby_text: bool = True
    text_merge_threshold: float = 5.0  # Points
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        if self.layout_confidence_threshold < 0 or self.layout_confidence_threshold > 1:
            raise ValueError("layout_confidence_threshold must be between 0 and 1")
        
        if self.header_region_threshold >= self.footer_region_threshold:
            raise ValueError("header_region_threshold must be less than footer_region_threshold")
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> 'ProcessingConfig':
        """Create config from dictionary"""
        return cls(**config_dict)
    
    def to_dict(self) -> Dict:
        """Convert config to dictionary"""
        return {
            field.name: getattr(self, field.name)
            for field in self.__dataclass_fields__.values()
        }
    
    def save(self, filepath: str):
        """Save configuration to JSON file"""
        import json
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'ProcessingConfig':
        """Load configuration from JSON file"""
        import json
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))
