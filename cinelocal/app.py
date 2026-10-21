"""Qt application startup."""
from __future__ import annotations

import os
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


def _prefer_embeddable_platform() -> None:
    """libVLC can only draw inside a Qt window through X11 on Linux. On Wayland sessions, Qt is asked to use
    XWayland (xcb), falling back to native Wayland if the xcb plugin cannot load. The user's own
    QT_QPA_PLATFORM always wins."""
    if not sys.platform.startswith("linux") or os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("DISPLAY") and (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland"):
        os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"


def run() -> int:
    ensure_dirs()
    _prefer_embeddable_platform()
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
