"""Qt application startup."""
from __future__ import annotations

import faulthandler
import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME
from .config import DATA_DIR, DB_FILE, Settings, ensure_dirs
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
    """`CineLocal --check-player [file] [--bundled-libmpv]`: smoke test of a packaged build (used by the release
    workflow). Writes the result to `file` (the windowed Windows build has no console): the first line says whether
    libVLC loads, the second which libmpv was loaded. Exits 0 only if libVLC loads and, with --bundled-libmpv, if the
    libmpv that loaded is the copy inside the app folder (not one of the system)."""
    from . import mpvbackend
    from .ui.player_page import load_error
    reason = load_error()
    args = sys.argv[sys.argv.index("--check-player") + 1:]
    failed = bool(reason)
    lines = [reason or "built-in player OK"]
    mpv_reason, mpv_path = mpvbackend.unavailable_reason(), mpvbackend.library_path()
    lines.append(f"libmpv: {mpv_path}" if not mpv_reason else f"libmpv: not loaded ({mpv_reason})")
    if "--bundled-libmpv" in args:
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
        if mpv_reason or base not in Path(mpv_path).resolve().parents:
            lines.append(f"libmpv must be the copy bundled in {base}")
            failed = True
    files = [a for a in args if not a.startswith("--")]
    if files:
        Path(files[0]).write_text("\n".join(lines), encoding="utf-8")
    return 1 if failed else 0


_crash_log = None   # kept open while the app runs


def _enable_crash_log() -> None:
    """Writes crashes (Python errors and native ones, e.g. inside libVLC) to <data folder>/crash.log: the windowed
    Windows build has no console where they could be seen."""
    global _crash_log
    try:
        _crash_log = open(DATA_DIR / "crash.log", "a", buffering=1, encoding="utf-8")
        _crash_log.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} start\n")
        faulthandler.enable(_crash_log, all_threads=True)
    except OSError:
        return
    sys.excepthook = lambda kind, value, tb: traceback.print_exception(kind, value, tb, file=_crash_log)


def run() -> int:
    if "--check-player" in sys.argv[1:]:
        return _check_player()
    ensure_dirs()
    _enable_crash_log()
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
