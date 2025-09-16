# Kokoro Read‑Along (Python Desktop App)

A minimal, runnable skeleton for a PDF “read‑along” player with sentence‑level audio using **Kokoro TTS** and text highlighting on the page.

https://github.com/hexgrad/kokoro  (install the `kokoro` package)

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
