from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from app.storage.library import Library
from app.ui.main_window import ReaderMainWindow

class HomeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kokoro Read‑Along – Home")
        self.library = Library()
        self._reader = None

        self.list = QListWidget()
        self.open_btn = QPushButton("Open Selected")
        self.delete_btn = QPushButton("Delete Selected")
        self.new_btn = QPushButton("Create New…")
        self.status = QLabel("")

        central = QWidget(); l = QVBoxLayout(central)
        l.addWidget(QLabel("Projects"))
        l.addWidget(self.list, 1)
        row = QHBoxLayout(); row.addWidget(self.open_btn); row.addWidget(self.delete_btn); row.addStretch(1); row.addWidget(self.new_btn)
        l.addLayout(row)
        l.addWidget(self.status)
        self.setCentralWidget(central)

        self.open_btn.clicked.connect(self.open_selected)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.new_btn.clicked.connect(self.create_new)
        self.list.itemDoubleClicked.connect(lambda _it: self.open_selected())

        self.refresh()

    def refresh(self):
        self.list.clear()
        docs = self.library.list_documents()
        for (doc_id, title, file_path, page_count, added_at) in docs:
            it = QListWidgetItem(f"{title}  —  {doc_id}")
            it.setData(Qt.UserRole, doc_id)
            self.list.addItem(it)
        self.status.setText(f"{self.list.count()} project(s)")

    def open_selected(self):
        it = self.list.currentItem()
        if not it:
            QMessageBox.information(self, "No selection", "Select a project first.")
            return
        doc_id = it.data(Qt.UserRole)
        self._open_reader_with_project(doc_id)

    def create_new(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", filter="PDF Files (*.pdf)")
        if not path:
            return
        reader = ReaderMainWindow()
        reader.load_pdf_path(path)
        reader.generate_audio()
        self._attach_reader(reader)

    def delete_selected(self):
        it = self.list.currentItem()
        if not it:
            QMessageBox.information(self, "No selection", "Select a project first.")
            return
        doc_id = it.data(Qt.UserRole)
        resp = QMessageBox.question(self, "Delete Project", "This will permanently delete the project's files and audio. Proceed?")
        if resp != QMessageBox.Yes:
            return
        self.library.delete_document(doc_id)
        self.refresh()

    def _open_reader_with_project(self, document_id: str):
        reader = ReaderMainWindow()
        reader.load_project(document_id)
        self._attach_reader(reader)

    def _attach_reader(self, reader: ReaderMainWindow):
        self._reader = reader
        self._reader.resize(self.size())
        self._reader.backRequested.connect(self._on_reader_back)
        self._reader.destroyed.connect(lambda: self.show())
        self._reader.show()
        self.hide()

    def _on_reader_back(self):
        if self._reader:
            self._reader.close()
        self.show()
