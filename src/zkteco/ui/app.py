"""Qt application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ..config import DeviceConfig
from .main_window import MainWindow
from .theme import apply_theme


def run_ui() -> int:
    db_path = Path(os.getenv("ZKTEco_DB", "tracker.db"))
    app = QApplication(sys.argv)
    app.setApplicationName("Control de asistencia ZKTeco")
    app.setOrganizationName("ZKTeco")
    apply_theme(app)
    window = MainWindow(db_path=db_path, config=DeviceConfig())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_ui())