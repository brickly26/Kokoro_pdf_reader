# Kokoro Read‑Along (Python Desktop App)

A minimal, runnable skeleton for a PDF “read‑along” player with sentence‑level audio using **Kokoro TTS** and text highlighting on the page.

https://github.com/hexgrad/kokoro (install the `kokoro` package)

## Features (MVP)

- Open a PDF
- Choose filters to skip images/headers/footers/footnotes/tables/formulas (heuristic)
- Extract sentences with bounding boxes (PyMuPDF)
- Generate one audio file per sentence (Kokoro)
- Click a sentence to play from there
- Page auto-scroll + highlight rectangles for the active sentence
- Library folder to keep PDFs and audios (local only)

> This is a skeleton focused on clarity. You can extend it with better heuristics, OCR, and a richer database.

## Requirements

- Python 3.10+ recommended
- System deps: On some platforms Kokoro may require **espeak-ng** for graphemes/phonemes.
- `pip install -r requirements.txt`

### requirements.txt

```text
PySide6
PyMuPDF
soundfile
kokoro>=0.9.4
```

> If you prefer ONNX: install `kokoro-onnx` and modify `tts/kokoro_engine.py` accordingly.

## Run

```bash
python -m app.main
```

## Packaging

Use PyInstaller for a single-file or folder build:

```bash
pip install pyinstaller
pyinstaller --noconfirm --name KokoroReadAlong --onefile app/main.py
```

## Project Layout

```
app/
  main.py
  ui/
    main_window.py
    filters_dialog.py
    pdf_canvas.py
  ingest/
    pdf_reader.py
  tts/
    kokoro_engine.py
  storage/
    library.py
  nlp/
    segment.py
  utils/
    audio_player.py
Library/            # stores per-document folders with audio/
```

## Notes

- Scanned PDFs: add an OCR pass before extraction.
- Highlighting uses PyMuPDF coordinates drawn on an image of the page; simple and robust.
- Audio chunks are WAV at 24kHz by default.

---

# Enhanced Academic PDF Processing Pipeline

In addition to the basic read-along functionality, this project now includes a **comprehensive academic PDF processing pipeline** that can extract and categorize different types of content from scholarly documents.

## 🚀 New Features

### Content Extraction

- **Layout Detection**: Uses PubLayNet via layoutparser to identify major document regions
- **Table Extraction**: Robust table detection and extraction with Camelot and Tabula
- **Image Processing**: Extract and organize embedded images and figures
- **Formula Detection**: Identify mathematical formulas using symbol analysis and OCR
- **Text Classification**: Advanced heuristics for headers, footers, footnotes, page numbers
- **Caption Matching**: Automatically associate captions with nearby figures and tables
- **OCR Fallback**: Support for scanned PDFs with Tesseract and EasyOCR

### Output Formats

- **Structured JSON Manifest**: Complete document structure with metadata
- **Clean Text Files**: Main narrative content without headers/footers
- **Organized Artifacts**: Images, tables (CSV/Excel/JSON), formulas saved separately
- **Detailed Reports**: Processing summaries and quality metrics

### Configuration Options

- **Modular Design**: Enable/disable specific extractors
- **Configurable Thresholds**: Adjust detection confidence levels
- **Multiple Output Formats**: Choose what artifacts to generate
- **Graceful Degradation**: Works even if optional dependencies are missing

## 📦 Enhanced Dependencies

The enhanced pipeline uses additional optional dependencies:

```bash
# Install all dependencies
pip install -r requirements.txt

# Or install core dependencies only
pip install PyMuPDF pillow numpy pandas

# Optional: Layout detection (requires GPU/CUDA for best performance)
pip install layoutparser detectron2 torchvision

# Optional: Table extraction
pip install camelot-py[cv] tabula-py

# Optional: OCR support
pip install pytesseract easyocr

# Optional: Mathematical processing
pip install sympy scipy
```

## 🖥️ Command Line Interface

Use the enhanced pipeline via command line:

```bash
# Basic usage
python pdf_processor_cli.py document.pdf

# Custom output directory
python pdf_processor_cli.py document.pdf -o /path/to/output

# Disable specific features
python pdf_processor_cli.py document.pdf --no-tables --no-images

# Force OCR processing
python pdf_processor_cli.py document.pdf --ocr

# Use custom configuration
python pdf_processor_cli.py document.pdf --config my_config.json

# Check available dependencies
python pdf_processor_cli.py --list-dependencies

# Get help
python pdf_processor_cli.py --help
```

## 📝 Programmatic Usage

```python
from app.pdf_pipeline import PDFProcessor, ProcessingConfig

# Create configuration
config = ProcessingConfig(
    output_dir="my_output",
    use_layout_detection=True,
    table_extraction_enabled=True,
    formula_detection_enabled=True,
    verbose=True
)

# Process PDF
processor = PDFProcessor(config)
results = processor.process_pdf("document.pdf")

# Access results
print(f"Found {len(results['content']['tables'])} tables")
print(f"Found {len(results['content']['formulas'])} formulas")
print(f"Processing took {results['metadata']['processing_time']:.2f}s")
```

## 📂 Output Structure

The pipeline generates organized output:

```
output/
├── manifest.json              # Complete processing results
├── text/
│   ├── main_text.txt         # Clean narrative text
│   └── main_text.md          # Markdown version
├── images/
│   ├── page_001_image_001.png
│   └── ...
├── tables/
│   ├── page_002_table_001.csv
│   ├── page_002_table_001.xlsx
│   ├── page_002_table_001_metadata.json
│   └── ...
├── formulas/
│   ├── page_003_formula_001.txt
│   └── ...
└── reports/
    ├── summary.txt           # Human-readable summary
    ├── summary.json          # Detailed statistics
    └── *_report.json         # Per-content-type reports
```

## 🎯 Use Cases

### Academic Research

- Extract tables and figures from research papers
- Process literature reviews and systematic reviews
- Convert scanned papers to searchable text

### Document Analysis

- Analyze document structure and layout
- Extract specific content types for further processing
- Generate clean text versions of complex documents

### Data Extraction

- Batch process PDF collections
- Extract structured data for analysis
- Convert legacy documents to modern formats

## ⚙️ Configuration

Create custom configurations:

```json
{
  "output_dir": "output",
  "use_layout_detection": true,
  "layout_confidence_threshold": 0.7,
  "table_extraction_enabled": true,
  "table_detection_method": "camelot",
  "image_extraction_enabled": true,
  "formula_detection_enabled": true,
  "ocr_enabled": true,
  "ocr_engine": "tesseract",
  "create_main_text": true,
  "exclude_headers_footers": true,
  "verbose": true
}
```

## 🔧 Performance Tips

1. **GPU Acceleration**: Install CUDA-enabled PyTorch for faster layout detection
2. **Parallel Processing**: Enable `parallel_processing` for multi-core systems
3. **Selective Processing**: Disable unused extractors to speed up processing
4. **Batch Processing**: Process multiple documents in sequence for efficiency

## 🚨 Troubleshooting

### Common Issues

**Missing Dependencies**

```bash
python pdf_processor_cli.py --list-dependencies
```

**Low Layout Detection Accuracy**

- Adjust `layout_confidence_threshold` (default: 0.7)
- Try different layout models (`PubLayNet` vs `TableBank`)

**Table Extraction Issues**

- Try different methods: `camelot`, `tabula`, or `both`
- Adjust `table_accuracy_threshold`

**OCR Problems**

- Ensure Tesseract is installed system-wide
- Try different OCR engines (`tesseract` vs `easyocr`)

## 📋 Examples

See `example_usage.py` for detailed examples of:

- Basic document processing
- Advanced configuration options
- Text-only extraction
- Configuration file usage

## 🤝 Integration

The enhanced pipeline integrates seamlessly with the original read-along functionality:

1. Use the pipeline to extract clean text
2. Feed results to the original TTS and highlighting system
3. Enjoy enhanced accuracy and better content filtering

Both systems share the same PyMuPDF foundation and can be used together or independently.
