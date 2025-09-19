from pathlib import Path
import sqlite3, hashlib, shutil, os, json
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[2] / "Library"
ROOT.mkdir(parents=True, exist_ok=True)

DB = ROOT / "library.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY,
  title TEXT,
  file_path TEXT,
  page_count INTEGER,
  added_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id TEXT,
  order_idx INTEGER,
  page_index INTEGER,
  text TEXT,
  bbox_json TEXT,
  audio_path TEXT,
  duration_sec REAL,
  voice TEXT,
  speed REAL
);
"""

class Library:
    def __init__(self):
        # Allow usage from FastAPI threadpool workers
        self.conn = sqlite3.connect(DB, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self._migrate_schema()

    def _migrate_schema(self):
        cur = self.conn.cursor()
        # Add columns to chunks if missing
        cur.execute("PRAGMA table_info(chunks)")
        cols = {r[1] for r in cur.fetchall()}  # name at index 1
        if "section" not in cols:
            cur.execute("ALTER TABLE chunks ADD COLUMN section TEXT")
        if "merged_start_ms" not in cols:
            cur.execute("ALTER TABLE chunks ADD COLUMN merged_start_ms INTEGER")
        if "merged_end_ms" not in cols:
            cur.execute("ALTER TABLE chunks ADD COLUMN merged_end_ms INTEGER")
        if "sample_rate" not in cols:
            cur.execute("ALTER TABLE chunks ADD COLUMN sample_rate INTEGER")
        # Add merged audio path to documents
        cur.execute("PRAGMA table_info(documents)")
        dcols = {r[1] for r in cur.fetchall()}
        if "merged_audio_path" not in dcols:
            cur.execute("ALTER TABLE documents ADD COLUMN merged_audio_path TEXT")
        if "merged_sr" not in dcols:
            cur.execute("ALTER TABLE documents ADD COLUMN merged_sr INTEGER")
        self.conn.commit()

    def _doc_id(self, pdf_path: str) -> str:
        h = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]
        return h

    def ensure_document(self, pdf_path: str) -> str:
        pid = self._doc_id(pdf_path)
        # copy source pdf for permanence
        doc_dir = ROOT / pid
        doc_dir.mkdir(parents=True, exist_ok=True)
        dest = doc_dir / "source.pdf"
        if not dest.exists():
            try:
                shutil.copy2(pdf_path, dest)
            except Exception:
                pass
        self.conn.execute(
            "INSERT OR IGNORE INTO documents(id, title, file_path, page_count) VALUES(?,?,?,?)",
            (pid, Path(pdf_path).name, dest.as_posix(), 0)
        )
        self.conn.commit()
        return pid

    def audio_dir(self, document_id: str) -> str:
        p = ROOT / document_id / "audio"
        p.mkdir(parents=True, exist_ok=True)
        return p.as_posix()

    # Backward-compatible API
    def save_chunks(self, document_id: str, sentences, chunks, voice: str = "", speed: float = 1.0):
        # sentences: list[Sentence]; chunks: list[(idx, text, path, dur)]
        cur = self.conn.cursor()
        cur.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        for i, s in enumerate(sentences):
            apath = ""
            dur = 0.0
            if i < len(chunks):
                _idx, _txt, apath, dur = chunks[i]
            cur.execute(
                "INSERT INTO chunks(document_id, order_idx, page_index, text, bbox_json, audio_path, duration_sec, voice, speed) VALUES(?,?,?,?,?,?,?,?,?)",
                (document_id, i, s.page_index, s.text, json.dumps(getattr(s, "word_boxes", [])), apath, dur, voice, speed)
            )
        self.conn.commit()

    def list_documents(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, title, file_path, page_count, added_at FROM documents ORDER BY added_at DESC")
        return cur.fetchall()

    def get_document(self, document_id: str):
        cur = self.conn.cursor()
        cur.execute("SELECT id, title, file_path, page_count, added_at, merged_audio_path, merged_sr FROM documents WHERE id=?", (document_id,))
        return cur.fetchone()

    def get_chunks(self, document_id: str):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT order_idx, page_index, text, bbox_json, audio_path, duration_sec, voice, speed FROM chunks WHERE document_id=? ORDER BY order_idx ASC",
            (document_id,)
        )
        return cur.fetchall()

    # New APIs for chunk metadata and merged audio
    def save_chunk_records(self, document_id: str, records, voice: str, speed: float, merged_audio_path: str, sample_rate: int):
        """records: iterable of dict with keys: order_idx, page_index, section, text, boxes, audio_path, duration_sec, start_ms, end_ms"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        for r in records:
            cur.execute(
                "INSERT INTO chunks(document_id, order_idx, page_index, text, bbox_json, audio_path, duration_sec, voice, speed, section, merged_start_ms, merged_end_ms, sample_rate) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    document_id,
                    int(r.get("order_idx", 0)),
                    int(r.get("page_index", 0)),
                    r.get("text", ""),
                    json.dumps(r.get("boxes", [])),
                    r.get("audio_path", ""),
                    float(r.get("duration_sec", 0.0)),
                    voice,
                    speed,
                    r.get("section", "body"),
                    int(r.get("start_ms", 0)),
                    int(r.get("end_ms", 0)),
                    int(sample_rate),
                )
            )
        # Update documents merged audio info
        self.conn.execute(
            "UPDATE documents SET merged_audio_path=?, merged_sr=? WHERE id=?",
            (merged_audio_path, int(sample_rate), document_id)
        )
        self.conn.commit()

    def get_chunk_records(self, document_id: str):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT order_idx, page_index, text, bbox_json, audio_path, duration_sec, voice, speed, section, merged_start_ms, merged_end_ms, sample_rate FROM chunks WHERE document_id=? ORDER BY order_idx ASC",
            (document_id,)
        )
        rows = cur.fetchall()
        out = []
        for (order_idx, page_index, text, bbox_json, audio_path, duration_sec, voice, speed, section, start_ms, end_ms, sr) in rows:
            try:
                boxes = json.loads(bbox_json) if bbox_json else []
            except Exception:
                boxes = []
            out.append({
                "order_idx": order_idx,
                "page_index": page_index,
                "text": text,
                "boxes": boxes,
                "audio_path": audio_path,
                "duration_sec": duration_sec,
                "voice": voice,
                "speed": speed,
                "section": section or "body",
                "start_ms": start_ms or 0,
                "end_ms": end_ms or 0,
                "sample_rate": sr or 24000,
            })
        return out

    def delete_document(self, document_id: str):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        cur.execute("DELETE FROM documents WHERE id=?", (document_id,))
        self.conn.commit()
        # remove on-disk folder
        doc_dir = ROOT / document_id
        try:
            if doc_dir.exists():
                shutil.rmtree(doc_dir)
        except Exception:
            pass
