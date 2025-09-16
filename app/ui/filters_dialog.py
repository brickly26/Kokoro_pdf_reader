from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QCheckBox, QLabel
from app.ingest.pdf_reader import FILTER_KEYS

class FiltersDialog(QDialog):
    def __init__(self, current_values: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Content Filters")
        self._boxes = {}
        lyt = QVBoxLayout(self)
        lyt.addWidget(QLabel("Skip the following elements during reading:"))
        for key in FILTER_KEYS:
            cb = QCheckBox(key.replace("_", " ").title())
            cb.setChecked(bool(current_values.get(key, False)))
            self._boxes[key] = cb
            lyt.addWidget(cb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

    def values(self):
        return {k: cb.isChecked() for k, cb in self._boxes.items()}
