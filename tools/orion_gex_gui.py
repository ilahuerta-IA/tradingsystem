#!/usr/bin/env python3
"""ORION GEX GUI -- entry point.

Launches the PyQt6 visualization window for manual GEX observation.
See context/ORION_GUI_PLAN.md for design details.

Usage:
    python tools/orion_gex_gui.py
"""

import os
import sys

# Ensure tools/ is importable when run directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from orion_gui.main_window import OrionGuiMainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = OrionGuiMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
