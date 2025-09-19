from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from app.storage.library import Library, ROOT as LIB_ROOT
from app.ingest.pdf_reader import extract_chunks
from app.tts.kokoro_engine import KokoroTTS, KokoroNotAvailable
from pathlib import Path

BACKEND_BASE = "http://127.0.0.1:8000"

app = FastAPI(title="Kokoro Read-Along API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Library directory so the renderer can load PDFs and audio via HTTP
app.mount("/files", StaticFiles(directory=LIB_ROOT.as_posix()), name="files")

lib = Library()

class CreateProjectBody(BaseModel):
    path: str

class GenerateBody(BaseModel):
    voice: str = "af_heart"
    speed: float = 1.0

@app.get("/projects")
def list_projects():
    rows = lib.list_documents()
    return [
        {"id": r[0], "title": r[1], "file_path": r[2], "added_at": r[4]}
        for r in rows
    ]

import threading
from threading import Thread

# Track processing state
processing_projects = {}  # doc_id -> {"status": "processing"/"completed"/"failed", "progress": 0-100}

@app.post("/projects")
def create_project(body: CreateProjectBody):
    pdf_path = Path(body.path)
    if not pdf_path.exists():
        return {"error": "File not found"}
    
    # Create document first
    doc_id = lib.ensure_document(pdf_path.as_posix())
    
    # Extract chunks immediately
    chunks = extract_chunks(pdf_path.as_posix())
    records = []
    for c in chunks:
        records.append({
            "order_idx": c.order_idx,
            "page_index": c.page_index,
            "section": c.section,
            "text": c.text,
            "boxes": c.boxes,
            "audio_path": "",
            "duration_sec": 0.0,
            "start_ms": 0,
            "end_ms": 0,
        })
    
    # Save chunks without audio first
    lib.save_chunk_records(doc_id, records, voice="", speed=1.0, merged_audio_path="", sample_rate=24000)
    
    # Start background audio generation
    processing_projects[doc_id] = {"status": "processing", "progress": 0}
    thread = Thread(target=generate_audio_background, args=(doc_id, records))
    thread.daemon = True
    thread.start()
    
    return {"id": doc_id, "processing": True}

def generate_audio_background(doc_id: str, records: list):
    try:
        processing_projects[doc_id]["progress"] = 10
        out_dir = Path(lib.audio_dir(doc_id))
        
        processing_projects[doc_id]["progress"] = 20
        tts = KokoroTTS(voice="af_heart", speed=1.0)
        texts = [r.get("text", "") for r in records]
        
        processing_projects[doc_id]["progress"] = 30
        paths, merged_path, sr, offsets = tts.synth_chunks(texts, out_dir)
        
        processing_projects[doc_id]["progress"] = 80
        # Update records with audio info
        by_idx = {idx: (p, d) for (idx, _txt, p, d) in paths}
        for i, r in enumerate(records):
            if i in by_idx:
                p, d = by_idx[i]
                r["audio_path"] = p
                r["duration_sec"] = float(d)
            if i < len(offsets):
                r["start_ms"], r["end_ms"] = offsets[i]
        
        processing_projects[doc_id]["progress"] = 90
        # Save everything
        lib.save_chunk_records(doc_id, records, voice="af_heart", speed=1.0, merged_audio_path=merged_path, sample_rate=sr)
        
        processing_projects[doc_id] = {"status": "completed", "progress": 100}
        
    except Exception as e:
        processing_projects[doc_id] = {"status": "failed", "progress": 0, "error": str(e)}

@app.get("/projects/{doc_id}/status")
def get_project_status(doc_id: str):
    if doc_id in processing_projects:
        return processing_projects[doc_id]
    
    # Check if project has audio already
    doc = lib.get_document(doc_id)
    if doc and doc[5]:  # merged_audio_path exists
        return {"status": "completed", "progress": 100}
    
    return {"status": "unknown", "progress": 0}

@app.get("/projects/{doc_id}")
def get_project(doc_id: str):
    doc = lib.get_document(doc_id)
    if not doc:
        return {"error": "not_found"}
    _id, title, file_path, page_count, added_at, merged_path, merged_sr = doc
    chunks = lib.get_chunk_records(doc_id)
    # Build absolute HTTP URL for PDF
    file_url = f"{BACKEND_BASE}/files/{doc_id}/source.pdf"
    merged_url = (f"{BACKEND_BASE}{merged_path}" if merged_path and not merged_path.startswith("http") and merged_path.startswith(LIB_ROOT.as_posix()) else merged_path)
    return {
        "id": doc_id,
        "title": title,
        "file_path": file_path,
        "file_url": file_url,
        "page_count": page_count,
        "added_at": added_at,
        "merged_audio_path": merged_url,
        "merged_sr": merged_sr,
        "chunks": chunks,
    }

@app.post("/projects/{doc_id}/generate")
def generate_project(doc_id: str, body: GenerateBody):
    doc = lib.get_document(doc_id)
    if not doc:
        return {"error": "not_found"}
    _id, _title, file_path, _pc, _added, _merged, _msr = doc
    out_dir = Path(lib.audio_dir(doc_id))
    try:
        tts = KokoroTTS(voice=body.voice, speed=body.speed)
    except KokoroNotAvailable as e:
        return {"error": str(e)}
    recs = lib.get_chunk_records(doc_id)
    texts = [r.get("text", "") for r in recs]
    paths, merged_path, sr, offsets = tts.synth_chunks(texts, out_dir)
    by_idx = {idx: (p, d) for (idx, _txt, p, d) in paths}
    for i, r in enumerate(recs):
        if i in by_idx:
            p, d = by_idx[i]
            r["audio_path"] = p
            r["duration_sec"] = float(d)
        if i < len(offsets):
            r["start_ms"], r["end_ms"] = offsets[i]
    lib.save_chunk_records(doc_id, recs, voice=body.voice, speed=body.speed, merged_audio_path=merged_path, sample_rate=sr)
    merged_url = f"{BACKEND_BASE}/files/{doc_id}/audio/merged.wav"
    return {"ok": True, "merged_audio_path": merged_url, "sample_rate": sr}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
