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


def _check_player() -> int:
    """`CineLocal --check-player [file]`: smoke test of a packaged build (used by the release workflow).
    Writes the result to `file` (the windowed Windows build has no console) and exits 0 only if libVLC loads."""
    from .ui.player_page import load_error
    reason = load_error()
    args = sys.argv[sys.argv.index("--check-player") + 1:]
    if args:
        Path(args[0]).write_text(reason or "built-in player OK", encoding="utf-8")
    return 1 if reason else 0


def run() -> int:
    if "--check-player" in sys.argv[1:]:
        return _check_player()
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
