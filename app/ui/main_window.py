from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QFileDialog, QLabel, QMessageBox, QSplitter, QSlider, QComboBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt, QUrl, QThread, Signal, QObject
from PySide6.QtGui import QAction
from app.ui.filters_dialog import FiltersDialog
from app.ui.pdf_canvas import PdfCanvas
from app.ingest.pdf_reader import extract_sentences, Sentence, DEFAULT_FILTERS
from app.tts.kokoro_engine import KokoroTTS, KokoroNotAvailable
from app.utils.audio_player import AudioPlayer
from app.storage.library import Library
from pathlib import Path
import os, json

class TTSWorker(QObject):
    progressed = Signal(int, int)  # done, total
    finished = Signal(list, str)   # chunks_info, err
    def __init__(self, sentences, out_dir, voice, speed):
        super().__init__()
        self.sentences = sentences
        self.out_dir = out_dir
        self.voice = voice
        self.speed = speed

    def run(self):
        try:
            tts = KokoroTTS(voice=self.voice, speed=self.speed)
            done = 0
            total = max(1, len(self.sentences))
            def on_progress(idx_done, total_count):
                self.progressed.emit(idx_done, total_count)
            chunks = tts.synth_sentences([s.text for s in self.sentences], Path(self.out_dir), on_progress=on_progress)
            # chunks: list of (idx, text, path, dur)
            self.finished.emit(chunks, "")
        except KokoroNotAvailable as e:
            self.finished.emit([], str(e))
        except Exception as e:
            self.finished.emit([], f"Unexpected error: {e!r}")

class ReaderMainWindow(QMainWindow):
    backRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kokoro Read‑Along")
        self.library = Library()
        self.current_pdf_path = None
        self.current_sentences: list[Sentence] = []
        self.current_chunks = []  # list of tuples returned by Kokoro
        self.filters = DEFAULT_FILTERS.copy()
        self._progress_dialog = None

        # --- UI ---
        self.canvas = PdfCanvas()
        self.sent_list = QListWidget()
        self.play_btn = QPushButton("▶ Play selected")
        self.back_btn = QPushButton("← Back to Home")
        self.gen_btn = QPushButton("Generate Audio")
        self.filter_btn = QPushButton("Filters…")
        self.voice_combo = QComboBox(); self.voice_combo.addItems(["af_heart", "af_alloy", "af_sky", "af_river"])
        self.speed_slider = QSlider(Qt.Horizontal); self.speed_slider.setMinimum(50); self.speed_slider.setMaximum(150); self.speed_slider.setValue(100)
        self.status = QLabel("Ready")

        left = QWidget(); lyt = QVBoxLayout(left)
        lyt.addWidget(self.back_btn)
        lyt.addWidget(self.filter_btn)
        row = QHBoxLayout()
        row.addWidget(QLabel("Voice:")); row.addWidget(self.voice_combo)
        lyt.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Speed:")); row2.addWidget(self.speed_slider)
        lyt.addLayout(row2)
        lyt.addWidget(self.gen_btn)
        lyt.addWidget(QLabel("Sentences"))
        lyt.addWidget(self.sent_list, 1)
        lyt.addWidget(self.play_btn)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.canvas)
        split.setStretchFactor(1, 1)

        central = QWidget(); clyt = QVBoxLayout(central)
        clyt.addWidget(split, 1)
        clyt.addWidget(self.status)
        self.setCentralWidget(central)

        # Player
        self.player = AudioPlayer()
        self.player.playbackFinished.connect(self._on_chunk_finished)

        # wire
        self.back_btn.clicked.connect(self.go_back)
        self.filter_btn.clicked.connect(self.open_filters)
        self.gen_btn.clicked.connect(self.generate_audio)
        self.play_btn.clicked.connect(self.play_selected)
        self.sent_list.itemClicked.connect(self.play_selected)

    # --- reusable loaders ---
    def load_pdf_path(self, path: str):
        self.current_pdf_path = path
        self._show_progress("Extracting sentences…", indeterminate=True)
        QApplication.processEvents()
        self.canvas.load_pdf(path)
        self.status.setText("Extracting sentences…")
        self.current_sentences = extract_sentences(path, self.filters)
        self._populate_sentence_list()
        self.status.setText(f"Loaded {len(self.current_sentences)} sentences.")
        self._close_progress()

    def load_project(self, document_id: str):
        doc = self.library.get_document(document_id)
        if not doc:
            QMessageBox.warning(self, "Missing project", "Project not found on disk.")
            return
        _id, _title, file_path, _pc, _added = doc
        self.current_pdf_path = file_path
        self.canvas.load_pdf(file_path)
        self.status.setText("Loading project…")
        rows = self.library.get_chunks(document_id)
        self.current_sentences = []
        self.current_chunks = []
        self.sent_list.clear()
        for order_idx, page_index, text, bbox_json, audio_path, duration_sec, voice, speed in rows:
            try:
                boxes = json.loads(bbox_json) if bbox_json else []
            except Exception:
                boxes = []
            self.current_sentences.append(Sentence(page_index=page_index, text=text, word_boxes=boxes))
            self.current_chunks.append((order_idx, text, audio_path or "", duration_sec or 0.0))
        self._populate_sentence_list()
        for i in range(min(len(self.current_chunks), self.sent_list.count())):
            it = self.sent_list.item(i)
            it.setData(Qt.UserRole + 1, self.current_chunks[i][2])
        self.status.setText(f"Loaded project with {len(self.current_sentences)} sentences.")

    # --- actions ---
    def open_filters(self):
        dlg = FiltersDialog(self.filters, self)
        if dlg.exec():
            self.filters = dlg.values()
            if self.current_pdf_path:
                self.load_pdf_path(self.current_pdf_path)

    def generate_audio(self):
        if not self.current_sentences:
            QMessageBox.information(self, "No text", "Open a PDF first.")
            return
        voice = self.voice_combo.currentText()
        speed = self.speed_slider.value() / 100.0
        doc_id = self.library.ensure_document(self.current_pdf_path)
        out_dir = self.library.audio_dir(doc_id)
        self.status.setText("Generating audio with Kokoro…")
        self._show_progress("Generating audio…", indeterminate=False, maximum=max(1, len(self.current_sentences)))
        # Thread
        self.thread = QThread()
        self.worker = TTSWorker(self.current_sentences, out_dir, voice, speed)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progressed.connect(self._on_tts_progress)
        self.worker.finished.connect(self._tts_done)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _on_tts_progress(self, done: int, total: int):
        if self._progress_dialog:
            self._progress_dialog.setMaximum(max(1, total))
            self._progress_dialog.setValue(done)

    def _tts_done(self, chunks, err):
        self._close_progress()
        if err:
            QMessageBox.warning(self, "TTS error", err)
            self.status.setText("TTS failed.")
            return
        self.current_chunks = chunks
        for i in range(min(len(self.current_chunks), self.sent_list.count())):
            it = self.sent_list.item(i)
            it.setData(Qt.UserRole + 1, self.current_chunks[i][2])
        self.status.setText(f"Generated {len(self.current_chunks)} chunks. Click a sentence to play.")
        doc_id = self.library.ensure_document(self.current_pdf_path)
        voice = self.voice_combo.currentText()
        speed = self.speed_slider.value() / 100.0
        self.library.save_chunks(doc_id, self.current_sentences, self.current_chunks, voice=voice, speed=speed)

    def play_selected(self):
        it = self.sent_list.currentItem()
        if not it: return
        idx = it.data(Qt.UserRole)
        audio = it.data(Qt.UserRole + 1)
        if not audio:
            QMessageBox.information(self, "No audio", "Generate audio first.")
            return
        sent = self.current_sentences[idx]
        self.canvas.show_sentence(sent)
        self.player.play_file(audio)

    def _on_chunk_finished(self):
        pass

    def _populate_sentence_list(self):
        self.sent_list.clear()
        for i, s in enumerate(self.current_sentences):
            it = QListWidgetItem(f"{i+1:04d}  {s.text}")
            it.setData(Qt.UserRole, i)
            self.sent_list.addItem(it)

    def go_back(self):
        self.backRequested.emit()
        self.close()

    def _show_progress(self, text: str, indeterminate: bool = True, maximum: int = 0):
        self._close_progress()
        dlg = QProgressDialog(text, None, 0, maximum if not indeterminate else 0, self)
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.show()
        self._progress_dialog = dlg

    def _close_progress(self):
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None
