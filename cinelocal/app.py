"""Qt application startup."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME
from .config import DB_FILE, Settings, ensure_dirs
from .db import Database
from .service import LibraryService
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def _icon() -> QIcon:
    for candidate in (Path(__file__).resolve().parent.parent / "assets" / "cinelocal.svg",
                      Path.home() / ".local/share/icons/hicolor/scalable/apps/cinelocal.svg"):
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def run() -> int:
    ensure_dirs()
    if sys.platform == "win32":  # own taskbar icon (instead of Python's)
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(_icon())
    apply_theme(app)

    settings = Settings()
    db = Database(DB_FILE)
    service = LibraryService(db, settings)
    window = MainWindow(service)
    window.show()
    window.start()
    code = app.exec()
    db.close()
    return code
