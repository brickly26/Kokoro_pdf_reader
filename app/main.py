from PySide6.QtWidgets import QApplication
from app.ui.home_window import HomeWindow
import sys

def main():
    app = QApplication(sys.argv)
    win = HomeWindow()
    win.resize(1280, 900)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
