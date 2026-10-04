#!/usr/bin/env python3
"""Портативный запуск EnergyBMS Editor.

Windows:  python run_editor.py
Linux:    python3 run_editor.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from energybms_editor.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
