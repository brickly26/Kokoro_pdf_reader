"""
Table extraction from PDF documents using Camelot and Tabula
"""

import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import tempfile

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False

try:
    import tabula
    TABULA_AVAILABLE = True
except ImportError:
    TABULA_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    # Create a dummy pandas for type hints
    class pd:
        class DataFrame:
            pass

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class TableExtractor:
    """
    Extracts tables from PDF documents using multiple methods.
    
    Supports Camelot (lattice and stream) and Tabula for robust table detection.
    Exports tables in multiple formats (CSV, Excel, JSON).
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        # Check available extractors
        self.available_methods = []
        if CAMELOT_AVAILABLE and self.config.table_extraction_enabled:
            self.available_methods.append('camelot')
        if TABULA_AVAILABLE and self.config.table_extraction_enabled:
            self.available_methods.append('tabula')
        
        if not self.available_methods:
            if self.config.table_extraction_enabled:
                logger.warning("No table extraction libraries available")
            return
        
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas is required for table processing")
        
        # Create tables output directory
        self.tables_dir = Path(self.config.output_dir) / "tables"
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        
        self.extracted_count = 0
    
    def extract_tables(self, page, page_num: int, results: Dict):
        """
        Extract tables from a PDF page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (0-indexed)
            results: Results dictionary to update
        """
        if not self.config.table_extraction_enabled or not self.available_methods:
            return
        
        try:
            # Get PDF file path - we need the original file for Camelot/Tabula
            pdf_path = self._get_pdf_path_from_page(page)
            if not pdf_path:
                logger.warning(f"Could not determine PDF path for page {page_num}")
                return
            
            tables = []
            
            # Try different extraction methods
            if 'camelot' in self.available_methods and self.config.table_detection_method in ['camelot', 'both']:
                camelot_tables = self._extract_with_camelot(pdf_path, page_num)
                tables.extend(camelot_tables)
            
            if 'tabula' in self.available_methods and self.config.table_detection_method in ['tabula', 'both']:
                tabula_tables = self._extract_with_tabula(pdf_path, page_num)
                tables.extend(tabula_tables)
            
            # Process and save tables
            for table_info in tables:
                if self._should_save_table(table_info):
                    saved_files = self._save_table(table_info, page_num)
                    if saved_files:
                        table_entry = {
                            'type': 'table',
                            'page': page_num,
                            'bbox': table_info.get('bbox'),
                            'method': table_info.get('method'),
                            'accuracy': table_info.get('accuracy'),
                            'rows': table_info.get('rows', 0),
                            'columns': table_info.get('columns', 0),
                            'files': saved_files,
                            'has_header': table_info.get('has_header', False)
                        }
                        results['content']['tables'].append(table_entry)
                        results['artifacts']['tables'].extend(saved_files)
            
            logger.debug(f"Extracted {len(tables)} tables from page {page_num}")
            
        except Exception as e:
            logger.error(f"Table extraction failed for page {page_num}: {e}")
    
    def _get_pdf_path_from_page(self, page) -> Optional[str]:
        """Get the PDF file path from a page object"""
        try:
            return page.parent.name
        except:
            return None
    
    def _extract_with_camelot(self, pdf_path: str, page_num: int) -> List[Dict]:
        """Extract tables using Camelot"""
        tables = []
        
        try:
            # Camelot uses 1-based page numbers
            camelot_page = str(page_num + 1)
            
            # Try lattice method first (better for tables with lines)
            if self.config.camelot_flavor in ['lattice', 'both']:
                try:
                    lattice_tables = camelot.read_pdf(
                        pdf_path,
                        pages=camelot_page,
                        flavor='lattice'
                    )
                    
                    for i, table in enumerate(lattice_tables):
                        if table.accuracy >= self.config.table_accuracy_threshold:
                            table_info = {
                                'method': 'camelot_lattice',
                                'dataframe': table.df,
                                'accuracy': table.accuracy,
                                'bbox': self._camelot_bbox_to_list(table._bbox) if hasattr(table, '_bbox') else None,
                                'rows': len(table.df),
                                'columns': len(table.df.columns),
                                'has_header': self._detect_table_header(table.df),
                                'camelot_table': table
                            }
                            tables.append(table_info)
                except Exception as e:
                    logger.debug(f"Camelot lattice failed for page {page_num}: {e}")
            
            # Try stream method (better for tables without lines)
            if self.config.camelot_flavor in ['stream', 'both']:
                try:
                    stream_tables = camelot.read_pdf(
                        pdf_path,
                        pages=camelot_page,
                        flavor='stream'
                    )
                    
                    for i, table in enumerate(stream_tables):
                        if table.accuracy >= self.config.table_accuracy_threshold:
                            table_info = {
                                'method': 'camelot_stream',
                                'dataframe': table.df,
                                'accuracy': table.accuracy,
                                'bbox': self._camelot_bbox_to_list(table._bbox) if hasattr(table, '_bbox') else None,
                                'rows': len(table.df),
                                'columns': len(table.df.columns),
                                'has_header': self._detect_table_header(table.df),
                                'camelot_table': table
                            }
                            tables.append(table_info)
                except Exception as e:
                    logger.debug(f"Camelot stream failed for page {page_num}: {e}")
                    
        except Exception as e:
            logger.warning(f"Camelot extraction failed for page {page_num}: {e}")
        
        return tables
    
    def _extract_with_tabula(self, pdf_path: str, page_num: int) -> List[Dict]:
        """Extract tables using Tabula"""
        tables = []
        
        try:
            # Tabula uses 1-based page numbers
            tabula_page = page_num + 1
            
            # Extract tables
            dfs = tabula.read_pdf(
                pdf_path,
                pages=tabula_page,
                multiple_tables=True,
                pandas_options={'header': 'infer'}
            )
            
            for i, df in enumerate(dfs):
                if len(df) > 0 and len(df.columns) > 1:  # Basic validation
                    table_info = {
                        'method': 'tabula',
                        'dataframe': df,
                        'accuracy': self._estimate_tabula_accuracy(df),
                        'bbox': None,  # Tabula doesn't provide bbox info
                        'rows': len(df),
                        'columns': len(df.columns),
                        'has_header': self._detect_table_header(df),
                        'tabula_index': i
                    }
                    tables.append(table_info)
                    
        except Exception as e:
            logger.warning(f"Tabula extraction failed for page {page_num}: {e}")
        
        return tables
    
    def _camelot_bbox_to_list(self, bbox) -> Optional[List[float]]:
        """Convert Camelot bbox to list format"""
        try:
            if hasattr(bbox, 'x0'):
                return [bbox.x0, bbox.y0, bbox.x1, bbox.y1]
            elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                return list(bbox[:4])
        except:
            pass
        return None
    
    def _detect_table_header(self, df: pd.DataFrame) -> bool:
        """Detect if table has a header row"""
        if len(df) == 0:
            return False
        
        # Check if first row looks like headers
        first_row = df.iloc[0]
        
        # Headers are typically strings and different from data below
        first_row_str_count = sum(1 for x in first_row if isinstance(x, str) and len(str(x).strip()) > 0)
        
        if first_row_str_count > len(df.columns) * 0.7:  # 70% of columns have string values
            return True
        
        # Check if column names look meaningful
        meaningful_names = sum(1 for col in df.columns 
                              if isinstance(col, str) and len(col.strip()) > 2 and not col.startswith('Unnamed'))
        
        if meaningful_names > len(df.columns) * 0.5:  # 50% of columns have meaningful names
            return True
        
        return False
    
    def _estimate_tabula_accuracy(self, df: pd.DataFrame) -> float:
        """Estimate accuracy for Tabula tables (which don't provide this metric)"""
        if len(df) == 0:
            return 0.0
        
        # Simple heuristic based on data quality
        total_cells = len(df) * len(df.columns)
        non_empty_cells = 0
        
        for _, row in df.iterrows():
            for value in row:
                if pd.notna(value) and str(value).strip():
                    non_empty_cells += 1
        
        # Base accuracy on fill rate
        fill_rate = non_empty_cells / total_cells if total_cells > 0 else 0
        
        # Boost accuracy if table has reasonable structure
        if len(df) >= 2 and len(df.columns) >= 2:
            fill_rate += 0.1
        
        return min(100.0, fill_rate * 100)
    
    def _should_save_table(self, table_info: Dict) -> bool:
        """Determine if a table should be saved"""
        # Check minimum accuracy
        accuracy = table_info.get('accuracy', 0)
        if accuracy < self.config.table_accuracy_threshold:
            return False
        
        # Check minimum size
        rows = table_info.get('rows', 0)
        columns = table_info.get('columns', 0)
        if rows < 2 or columns < 2:
            return False
        
        return True
    
    def _save_table(self, table_info: Dict, page_num: int) -> List[str]:
        """Save a table in multiple formats"""
        saved_files = []
        
        try:
            df = table_info.get('dataframe')
            if df is None:
                return saved_files
            
            self.extracted_count += 1
            method = table_info.get('method', 'unknown')
            base_filename = f"page_{page_num:03d}_table_{self.extracted_count:03d}_{method}"
            
            # Save as CSV
            csv_path = self.tables_dir / f"{base_filename}.csv"
            df.to_csv(csv_path, index=False)
            saved_files.append(str(csv_path))
            
            # Save as Excel
            try:
                excel_path = self.tables_dir / f"{base_filename}.xlsx"
                df.to_excel(excel_path, index=False)
                saved_files.append(str(excel_path))
            except Exception as e:
                logger.debug(f"Could not save Excel file: {e}")
            
            # Save as JSON
            try:
                json_path = self.tables_dir / f"{base_filename}.json"
                df.to_json(json_path, orient='records', indent=2)
                saved_files.append(str(json_path))
            except Exception as e:
                logger.debug(f"Could not save JSON file: {e}")
            
            # Save metadata
            try:
                metadata = {
                    'method': table_info.get('method'),
                    'accuracy': table_info.get('accuracy'),
                    'bbox': table_info.get('bbox'),
                    'rows': table_info.get('rows'),
                    'columns': table_info.get('columns'),
                    'has_header': table_info.get('has_header'),
                    'page': page_num
                }
                
                metadata_path = self.tables_dir / f"{base_filename}_metadata.json"
                import json
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                saved_files.append(str(metadata_path))
            except Exception as e:
                logger.debug(f"Could not save metadata: {e}")
            
            logger.debug(f"Saved table files: {saved_files}")
            return saved_files
            
        except Exception as e:
            logger.error(f"Failed to save table: {e}")
            return []
    
    def merge_overlapping_tables(self, tables: List[Dict], overlap_threshold: float = 0.5) -> List[Dict]:
        """Merge tables that overlap significantly (e.g., detected by multiple methods)"""
        if not tables:
            return []
        
        # Group tables by those that have bounding boxes
        tables_with_bbox = [t for t in tables if t.get('bbox')]
        tables_without_bbox = [t for t in tables if not t.get('bbox')]
        
        if not tables_with_bbox:
            return tables  # Can't merge without position information
        
        merged = []
        used = set()
        
        for i, table1 in enumerate(tables_with_bbox):
            if i in used:
                continue
            
            current_group = [table1]
            used.add(i)
            
            for j, table2 in enumerate(tables_with_bbox[i+1:], i+1):
                if j in used:
                    continue
                
                if self._calculate_table_overlap(table1['bbox'], table2['bbox']) > overlap_threshold:
                    current_group.append(table2)
                    used.add(j)
            
            # Choose best table from group (highest accuracy)
            best_table = max(current_group, key=lambda t: t.get('accuracy', 0))
            merged.append(best_table)
        
        # Add tables without bbox (can't merge these)
        merged.extend(tables_without_bbox)
        
        return merged
    
    def _calculate_table_overlap(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate overlap ratio between two table bounding boxes"""
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
