from PySide6.QtWidgets import QApplication
from app.ui.main_window import ReaderMainWindow
import sys

def main():
    app = QApplication(sys.argv)
    win = ReaderMainWindow()
    win.resize(1280, 900)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
