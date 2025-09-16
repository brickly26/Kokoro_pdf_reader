from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QScrollArea
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage
from PySide6.QtCore import QRect, Qt
from app.ingest.pdf_reader import Sentence
import fitz

HILITE_COLOR = QColor(255, 255, 0, 120)

class PdfCanvas(QWidget):
    """Simple page viewer rendered by PyMuPDF with highlight rectangles."""
    def __init__(self):
        super().__init__()
        self.doc = None
        self.page_index = 0
        self.image_label = QLabel(alignment=Qt.AlignTop | Qt.AlignHCenter)
        self.scroll = QScrollArea(); self.scroll.setWidget(self.image_label); self.scroll.setWidgetResizable(True)
        l = QVBoxLayout(self); l.addWidget(self.scroll)
        self._last_boxes = []  # in PDF coords
        self._scale = 1.5

    def load_pdf(self, path):
        self.doc = fitz.open(path)
        self.page_index = 0
        self._render_page()

    def _render_page(self):
        if not self.doc: return
        page = self.doc[self.page_index]
        mat = fitz.Matrix(self._scale, self._scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pm = QPixmap.fromImage(img)
        # draw highlights if any
        if self._last_boxes:
            pm = pm.copy()
            painter = QPainter(pm)
            painter.setBrush(HILITE_COLOR); painter.setPen(Qt.NoPen)
            for (x0,y0,x1,y1) in self._last_boxes:
                painter.drawRect(int(x0*self._scale), int(y0*self._scale), int((x1-x0)*self._scale), int((y1-y0)*self._scale))
            painter.end()
        self.image_label.setPixmap(pm)
        self.image_label.resize(pm.size())

    def show_sentence(self, sent: Sentence):
        """Scroll to sentence's page and draw highlight boxes."""
        if not self.doc: return
        if sent.page_index != self.page_index:
            self.page_index = sent.page_index
        # use first/union of word boxes
        boxes = sent.word_boxes or []
        # fall back to an approximate bbox if needed
        self._last_boxes = boxes
        self._render_page()
        # scroll roughly to the first box
        if boxes:
            x0,y0,_,_ = boxes[0]
            self.scroll.verticalScrollBar().setValue(int(y0*self._scale) - 100)
