"""Точка входа. Запуск: python -m editor.main  (или через run_editor.py)."""
import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EnergyBMS Editor")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
