"""
Enhanced PDF Processing Pipeline

A comprehensive system for extracting and categorizing content from academic PDFs.
Supports layout detection, table extraction, image processing, formula detection,
and more with configurable options and graceful degradation.
"""

from .processor import PDFProcessor
from .config import ProcessingConfig
from .extractors import *

__all__ = ['PDFProcessor', 'ProcessingConfig']
