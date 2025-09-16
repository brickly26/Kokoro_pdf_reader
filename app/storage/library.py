from pathlib import Path
import sqlite3, hashlib, shutil, os
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
        self.conn = sqlite3.connect(DB)
        self.conn.executescript(SCHEMA)

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

    def save_chunks(self, document_id: str, sentences, chunks):
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
                (document_id, i, s.page_index, s.text, "", apath, dur, "", 1.0)
            )
        self.conn.commit()
