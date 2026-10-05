"""Точка входа. Запуск: python -m editor.main  (или через run_editor.py)."""
import os
import sys
import traceback

from PySide6.QtWidgets import QApplication

from . import config
from .main_window import MainWindow


def _excepthook(exc_type, exc, tb):
    """Пишем необработанные исключения в energybms_crash.log рядом с конфигом."""
    try:
        path = os.path.join(config.app_dir(), "energybms_crash.log")
        with open(path, "a", encoding="utf-8") as f:
            traceback.print_exception(exc_type, exc, tb, file=f)
    except OSError:
        pass
    traceback.print_exception(exc_type, exc, tb)


sys.excepthook = _excepthook


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EnergyBMS Editor")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
