"""
Output management for PDF processing pipeline
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import datetime

from ..config import ProcessingConfig

logger = logging.getLogger(__name__)


class OutputManager:
    """
    Manages all output generation for the PDF processing pipeline.
    
    Handles:
    - JSON manifest generation
    - Plain text file creation
    - File organization
    - Summary reports
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        
        # Create output directory structure
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.subdirs = {}
        subdirectories = ['images', 'tables', 'formulas', 'text', 'reports']
        for subdir in subdirectories:
            path = self.output_dir / subdir
            path.mkdir(exist_ok=True)
            self.subdirs[subdir] = path
    
    def generate_outputs(self, results: Dict):
        """
        Generate all output files from processing results.
        
        Args:
            results: Complete processing results dictionary
        """
        try:
            logger.info("Generating output files")
            
            # Generate JSON manifest
            if self.config.create_manifest:
                self._generate_manifest(results)
            
            # Generate plain text file
            if self.config.create_main_text:
                self._generate_main_text(results)
            
            # Generate summary report
            self._generate_summary_report(results)
            
            # Generate detailed reports
            self._generate_detailed_reports(results)
            
            # Generate file listing
            self._generate_file_listing(results)
            
            logger.info(f"All output files generated in: {self.output_dir}")
            
        except Exception as e:
            logger.error(f"Output generation failed: {e}")
            raise
    
    def _generate_manifest(self, results: Dict):
        """Generate comprehensive JSON manifest"""
        try:
            manifest = {
                'metadata': results.get('metadata', {}),
                'processing_info': {
                    'pipeline_version': '1.0.0',
                    'generated_at': datetime.datetime.now().isoformat(),
                    'output_directory': str(self.output_dir),
                    'configuration': self.config.to_dict()
                },
                'content': results.get('content', {}),
                'artifacts': results.get('artifacts', {}),
                'statistics': self._generate_statistics(results),
                'file_organization': self._get_file_organization()
            }
            
            # Clean up the manifest (remove non-serializable items)
            manifest = self._clean_for_json(manifest)
            
            # Save manifest
            manifest_path = self.output_dir / "manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Generated manifest: {manifest_path}")
            
        except Exception as e:
            logger.error(f"Failed to generate manifest: {e}")
    
    def _generate_main_text(self, results: Dict):
        """Generate plain text file with main narrative content"""
        try:
            text_blocks = results['content'].get('text_blocks', [])
            
            if not text_blocks:
                logger.warning("No text blocks found for main text generation")
                return
            
            # Sort by page and position
            sorted_blocks = sorted(text_blocks, key=lambda x: (
                x.get('page', 0),
                x.get('bbox', [0, 0, 0, 0])[1]  # Y position
            ))
            
            # Filter out headers, footers, etc. if configured
            main_text_blocks = []
            for block in sorted_blocks:
                block_type = block.get('type', 'body')
                
                # Skip non-body text based on configuration
                if self.config.exclude_headers_footers and block_type in ['header', 'footer']:
                    continue
                if self.config.exclude_page_numbers and block_type == 'page_number':
                    continue
                
                # Include body text and titles
                if block_type in ['body', 'title']:
                    main_text_blocks.append(block)
            
            # Generate text content
            text_content = []
            current_page = None
            
            for block in main_text_blocks:
                page = block.get('page', 0)
                text = block.get('text', '').strip()
                
                if not text:
                    continue
                
                # Add page separator
                if current_page is not None and page != current_page:
                    text_content.append(f"\\n\\n=== Page {page + 1} ===\\n")
                elif current_page is None:
                    text_content.append(f"=== Page {page + 1} ===\\n")
                
                # Add text with some formatting
                block_type = block.get('type', 'body')
                if block_type == 'title':
                    text_content.append(f"\\n## {text}\\n")
                else:
                    text_content.append(text)
                
                current_page = page
            
            # Write to file
            text_path = self.subdirs['text'] / "main_text.txt"
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write('\\n'.join(text_content))
            
            logger.info(f"Generated main text file: {text_path}")
            
            # Also save as markdown
            self._generate_markdown_text(main_text_blocks)
            
        except Exception as e:
            logger.error(f"Failed to generate main text: {e}")
    
    def _generate_markdown_text(self, text_blocks: List[Dict]):
        """Generate markdown version of main text"""
        try:
            markdown_content = []
            current_page = None
            
            for block in text_blocks:
                page = block.get('page', 0)
                text = block.get('text', '').strip()
                block_type = block.get('type', 'body')
                
                if not text:
                    continue
                
                # Add page break
                if current_page is not None and page != current_page:
                    markdown_content.append(f"\\n\\n---\\n")
                    markdown_content.append(f"\\n## Page {page + 1}\\n")
                elif current_page is None:
                    markdown_content.append(f"# Document Content\\n\\n## Page {page + 1}\\n")
                
                # Format based on type
                if block_type == 'title':
                    markdown_content.append(f"\\n### {text}\\n")
                else:
                    markdown_content.append(f"{text}\\n")
                
                current_page = page
            
            # Save markdown
            md_path = self.subdirs['text'] / "main_text.md"
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write('\\n'.join(markdown_content))
            
            logger.info(f"Generated markdown text: {md_path}")
            
        except Exception as e:
            logger.debug(f"Failed to generate markdown: {e}")
    
    def _generate_summary_report(self, results: Dict):
        """Generate summary report"""
        try:
            summary = {
                'document_info': {
                    'source_file': results['metadata'].get('source_file'),
                    'total_pages': results['metadata'].get('total_pages'),
                    'processing_time': results['metadata'].get('processing_time'),
                },
                'content_summary': self._generate_statistics(results),
                'processing_details': {
                    'layout_detection': 'layout_detector' in results['metadata'].get('config', {}),
                    'ocr_used': any(
                        block.get('source') == 'ocr' 
                        for block in results['content'].get('text_blocks', [])
                    ),
                    'table_extraction_method': results['metadata'].get('config', {}).get('table_detection_method'),
                    'formula_detection': len(results['content'].get('formulas', [])) > 0,
                },
                'quality_metrics': self._calculate_quality_metrics(results),
                'file_locations': {
                    'manifest': 'manifest.json',
                    'main_text': 'text/main_text.txt',
                    'images': 'images/',
                    'tables': 'tables/',
                    'formulas': 'formulas/'
                }
            }
            
            # Save as JSON
            summary_path = self.subdirs['reports'] / "summary.json"
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, default=str)
            
            # Save as human-readable text
            self._generate_text_summary(summary)
            
            logger.info(f"Generated summary report: {summary_path}")
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
    
    def _generate_text_summary(self, summary: Dict):
        """Generate human-readable text summary"""
        try:
            lines = []
            lines.append("PDF PROCESSING SUMMARY")
            lines.append("=" * 50)
            lines.append("")
            
            # Document info
            doc_info = summary.get('document_info', {})
            lines.append(f"Source File: {doc_info.get('source_file', 'Unknown')}")
            lines.append(f"Total Pages: {doc_info.get('total_pages', 'Unknown')}")
            processing_time = doc_info.get('processing_time', 0)
            if processing_time:
                lines.append(f"Processing Time: {processing_time:.2f} seconds")
            lines.append("")
            
            # Content summary
            content = summary.get('content_summary', {})
            lines.append("CONTENT EXTRACTED:")
            lines.append("-" * 20)
            for content_type, count in content.items():
                if isinstance(count, int) and count > 0:
                    lines.append(f"  {content_type.replace('_', ' ').title()}: {count}")
            lines.append("")
            
            # Processing details
            details = summary.get('processing_details', {})
            lines.append("PROCESSING METHODS:")
            lines.append("-" * 20)
            lines.append(f"  Layout Detection: {'Yes' if details.get('layout_detection') else 'No'}")
            lines.append(f"  OCR Used: {'Yes' if details.get('ocr_used') else 'No'}")
            if details.get('table_extraction_method'):
                lines.append(f"  Table Extraction: {details['table_extraction_method']}")
            lines.append(f"  Formula Detection: {'Yes' if details.get('formula_detection') else 'No'}")
            lines.append("")
            
            # Quality metrics
            quality = summary.get('quality_metrics', {})
            if quality:
                lines.append("QUALITY METRICS:")
                lines.append("-" * 20)
                for metric, value in quality.items():
                    if isinstance(value, float):
                        lines.append(f"  {metric.replace('_', ' ').title()}: {value:.2f}")
                    else:
                        lines.append(f"  {metric.replace('_', ' ').title()}: {value}")
                lines.append("")
            
            # File locations
            lines.append("OUTPUT FILES:")
            lines.append("-" * 20)
            locations = summary.get('file_locations', {})
            for name, path in locations.items():
                lines.append(f"  {name.replace('_', ' ').title()}: {path}")
            
            # Save text summary
            summary_text_path = self.subdirs['reports'] / "summary.txt"
            with open(summary_text_path, 'w', encoding='utf-8') as f:
                f.write('\\n'.join(lines))
            
        except Exception as e:
            logger.debug(f"Failed to generate text summary: {e}")
    
    def _generate_detailed_reports(self, results: Dict):
        """Generate detailed reports for each content type"""
        try:
            content = results.get('content', {})
            
            # Generate detailed reports for each content type
            for content_type, items in content.items():
                if isinstance(items, list) and items:
                    self._generate_content_type_report(content_type, items)
            
        except Exception as e:
            logger.error(f"Failed to generate detailed reports: {e}")
    
    def _generate_content_type_report(self, content_type: str, items: List[Dict]):
        """Generate detailed report for a specific content type"""
        try:
            report = {
                'content_type': content_type,
                'total_count': len(items),
                'items': []
            }
            
            for i, item in enumerate(items):
                item_info = {
                    'index': i + 1,
                    'page': item.get('page'),
                    'bbox': item.get('bbox'),
                    'text': item.get('text', '')[:200] + '...' if len(item.get('text', '')) > 200 else item.get('text', ''),
                }
                
                # Add type-specific information
                if content_type == 'tables':
                    item_info.update({
                        'rows': item.get('rows'),
                        'columns': item.get('columns'),
                        'accuracy': item.get('accuracy'),
                        'method': item.get('method')
                    })
                elif content_type == 'formulas':
                    item_info.update({
                        'math_score': item.get('math_score'),
                        'features': item.get('features')
                    })
                elif content_type == 'images':
                    item_info.update({
                        'size': item.get('size'),
                        'format': item.get('format'),
                        'file_path': item.get('file_path')
                    })
                
                report['items'].append(item_info)
            
            # Save report
            report_path = self.subdirs['reports'] / f"{content_type}_report.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            
        except Exception as e:
            logger.debug(f"Failed to generate {content_type} report: {e}")
    
    def _generate_file_listing(self, results: Dict):
        """Generate listing of all output files"""
        try:
            file_listing = {
                'generated_at': datetime.datetime.now().isoformat(),
                'base_directory': str(self.output_dir),
                'files': []
            }
            
            # Scan output directory
            for file_path in self.output_dir.rglob('*'):
                if file_path.is_file():
                    relative_path = file_path.relative_to(self.output_dir)
                    file_info = {
                        'path': str(relative_path),
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'type': self._get_file_type(file_path),
                        'created': datetime.datetime.fromtimestamp(file_path.stat().st_ctime).isoformat()
                    }
                    file_listing['files'].append(file_info)
            
            # Sort by path
            file_listing['files'].sort(key=lambda x: x['path'])
            
            # Save listing
            listing_path = self.output_dir / "file_listing.json"
            with open(listing_path, 'w', encoding='utf-8') as f:
                json.dump(file_listing, f, indent=2)
            
        except Exception as e:
            logger.debug(f"Failed to generate file listing: {e}")
    
    def _generate_statistics(self, results: Dict) -> Dict:
        """Generate statistics from processing results"""
        content = results.get('content', {})
        stats = {}
        
        for content_type, items in content.items():
            if isinstance(items, list):
                stats[content_type] = len(items)
        
        # Add derived statistics
        stats['total_content_items'] = sum(stats.values())
        
        # Text statistics
        text_blocks = content.get('text_blocks', [])
        if text_blocks:
            total_chars = sum(len(block.get('text', '')) for block in text_blocks)
            total_words = sum(len(block.get('text', '').split()) for block in text_blocks)
            stats['total_characters'] = total_chars
            stats['total_words'] = total_words
            stats['average_words_per_block'] = total_words / len(text_blocks)
        
        return stats
    
    def _calculate_quality_metrics(self, results: Dict) -> Dict:
        """Calculate quality metrics for the extraction"""
        metrics = {}
        
        try:
            content = results.get('content', {})
            
            # Text quality metrics
            text_blocks = content.get('text_blocks', [])
            if text_blocks:
                # Calculate OCR vs native text ratio
                ocr_blocks = [b for b in text_blocks if b.get('source') == 'ocr']
                metrics['ocr_text_ratio'] = len(ocr_blocks) / len(text_blocks)
                
                # Average confidence for OCR text
                ocr_confidences = [b.get('confidence', 0) for b in ocr_blocks if b.get('confidence')]
                if ocr_confidences:
                    metrics['average_ocr_confidence'] = sum(ocr_confidences) / len(ocr_confidences)
            
            # Table quality metrics
            tables = content.get('tables', [])
            if tables:
                table_accuracies = [t.get('accuracy', 0) for t in tables if t.get('accuracy')]
                if table_accuracies:
                    metrics['average_table_accuracy'] = sum(table_accuracies) / len(table_accuracies)
            
            # Formula detection confidence
            formulas = content.get('formulas', [])
            if formulas:
                formula_scores = [f.get('math_score', 0) for f in formulas if f.get('math_score')]
                if formula_scores:
                    metrics['average_formula_score'] = sum(formula_scores) / len(formula_scores)
        
        except Exception as e:
            logger.debug(f"Failed to calculate quality metrics: {e}")
        
        return metrics
    
    def _get_file_organization(self) -> Dict:
        """Get file organization structure"""
        return {
            'base_directory': str(self.output_dir),
            'subdirectories': {
                name: str(path) for name, path in self.subdirs.items()
            },
            'structure': {
                'manifest.json': 'Main processing results and metadata',
                'text/': 'Plain text and markdown output',
                'images/': 'Extracted images and figures',
                'tables/': 'Extracted tables in multiple formats',
                'formulas/': 'Detected mathematical formulas',
                'reports/': 'Summary and detailed reports',
                'file_listing.json': 'Complete listing of generated files'
            }
        }
    
    def _get_file_type(self, file_path: Path) -> str:
        """Determine file type from extension"""
        suffix = file_path.suffix.lower()
        
        type_mapping = {
            '.json': 'JSON data',
            '.txt': 'Plain text',
            '.md': 'Markdown',
            '.csv': 'CSV table',
            '.xlsx': 'Excel table',
            '.png': 'PNG image',
            '.jpg': 'JPEG image',
            '.jpeg': 'JPEG image',
            '.pdf': 'PDF document'
        }
        
        return type_mapping.get(suffix, 'Unknown')
    
    def _clean_for_json(self, obj: Any) -> Any:
        """Clean object for JSON serialization"""
        if isinstance(obj, dict):
            return {k: self._clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_for_json(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return str(obj)  # Convert objects to string representation
        else:
            return obj
