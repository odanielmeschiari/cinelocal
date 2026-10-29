#!/usr/bin/env python3
"""CineLocal entry point."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(*command: str) -> bool:
    try:
        return subprocess.run(command).returncode == 0
    except OSError:
        return False


def _ensure_dependencies() -> None:
    """Running from source on a computer without PySide6: installs the requirements in a private virtual
    environment (in CineLocal's data folder) and restarts there, so nothing has to be installed by hand.
    VLC is handled later, by the app itself (cinelocal/vlc_setup.py)."""
    if getattr(sys, "frozen", False):
        return
    try:
        import PySide6  # noqa: F401
        return
    except ImportError:
        if os.environ.get("CINELOCAL_BOOTSTRAPPED"):
            raise
    from cinelocal.config import DATA_DIR
    requirements = str(Path(__file__).resolve().with_name("requirements.txt"))
    venv = DATA_DIR / "venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    print("CineLocal: installing the required components (first run only, needs internet)...", flush=True)
    if (python.exists() or _run(sys.executable, "-m", "venv", str(venv))) \
            and _run(str(python), "-m", "pip", "install", "-r", requirements):
        target = str(python)
    else:
        shutil.rmtree(venv, ignore_errors=True)   # a half-created environment (e.g. without ensurepip)
        if not _run(sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "-r", requirements):
            sys.exit("CineLocal could not install its requirements automatically. Check the internet connection "
                     "and run again, or use the installer (install.sh / install.bat).")
        target = sys.executable
    sys.exit(subprocess.call([target, str(Path(__file__).resolve()), *sys.argv[1:]],
                             env={**os.environ, "CINELOCAL_BOOTSTRAPPED": "1"}))


if __name__ == "__main__":
    _ensure_dependencies()
    from cinelocal.app import run
    sys.exit(run())
