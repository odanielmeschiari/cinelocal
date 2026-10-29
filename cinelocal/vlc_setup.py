"""Installs libVLC (built-in player, and reading of each file's resolution/codecs) when the computer does not have it.

The packaged builds (Windows installer, .deb, portable archives) already carry libVLC. This module is for the rest
(running from source, or a bundled copy that cannot load): Windows downloads VLC's portable build into CineLocal's
data folder (no administrator rights needed); Linux asks the system for permission (pkexec) and installs the
distribution's VLC package; python-vlc is installed with pip when it is missing. No Qt here."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import shutil
import site
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .config import DATA_DIR

VLC_VERSION = "3.0.21"   # libVLC 3, the series python-vlc 3.x drives
_MIRRORS = ("https://get.videolan.org/vlc", "https://download.videolan.org/pub/videolan/vlc")
LOCAL_DIR = DATA_DIR / "vlc"   # Windows: VLC downloaded by install()
_LINUX_COMMANDS = (   # (package manager, command run as administrator)
    ("apt-get", ["env", "DEBIAN_FRONTEND=noninteractive", "sh", "-c", "apt-get update -qq; apt-get install -y vlc"]),
    ("pacman", ["pacman", "-S", "--noconfirm", "--needed", "vlc"]),
)
_MANUAL = "Install VLC from https://www.videolan.org/vlc/ (or with your package manager) and restart CineLocal."


def use_local_vlc() -> None:
    """Points python-vlc to the VLC downloaded by install() (Windows). Does nothing if there is none."""
    lib = LOCAL_DIR / "libvlc.dll"
    if sys.platform == "win32" and lib.is_file():
        os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(lib))
        os.environ.setdefault("VLC_PLUGIN_PATH", str(LOCAL_DIR / "plugins"))
        os.add_dll_directory(str(LOCAL_DIR))


def install(progress: Callable[[str], None] = lambda text: None) -> None:
    """Makes libVLC available. Raises RuntimeError with a message for the user if it cannot."""
    if not getattr(sys, "frozen", False) and importlib.util.find_spec("vlc") is None:
        progress("Installing python-vlc…")
        _pip_install("python-vlc>=3.0.18")
    if sys.platform == "win32":
        _install_windows(progress)
    elif sys.platform.startswith("linux"):
        _install_linux(progress)
    else:
        raise RuntimeError(_MANUAL)


def _pip_install(requirement: str) -> None:
    command = [sys.executable, "-m", "pip", "install", "--quiet", requirement]
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    # outside a virtual environment: the user's folder, and if the system forbids it (PEP 668), the override
    attempts = [command] if in_venv else [command + ["--user"], command + ["--user", "--break-system-packages"]]
    for attempt in attempts:
        try:
            if subprocess.run(attempt, capture_output=True, timeout=600).returncode == 0:
                user_site = site.getusersitepackages()
                if user_site not in sys.path and os.path.isdir(user_site):
                    sys.path.append(user_site)   # created after this process started
                importlib.invalidate_caches()
                return
        except (OSError, subprocess.SubprocessError):
            continue
    raise RuntimeError(f"Could not install {requirement.split('>')[0]} automatically (no internet connection?).")


def _install_linux(progress: Callable[[str], None]) -> None:
    manager = next((command for name, command in _LINUX_COMMANDS if shutil.which(name)), None)
    if manager is None or not shutil.which("pkexec"):
        raise RuntimeError(_MANUAL)
    progress("Installing VLC (a window will ask for your password)…")
    try:
        result = subprocess.run(["pkexec", *manager], capture_output=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Could not install VLC: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError("VLC was not installed (the password request was cancelled or the installation failed).")


def _install_windows(progress: Callable[[str], None]) -> None:
    name = f"vlc-{VLC_VERSION}-win64.zip"
    with tempfile.TemporaryDirectory() as tmp:
        archive, error = Path(tmp) / name, None
        for mirror in _MIRRORS:
            url = f"{mirror}/{VLC_VERSION}/win64/{name}"
            try:
                progress("Downloading VLC (about 40 MB)…")
                _download(url, archive)
                _verify_sha256(archive, url + ".sha256")
                break
            except (OSError, ValueError) as exc:
                error = exc
        else:
            raise RuntimeError(f"Could not download VLC ({error}). Check your internet connection.")
        progress("Installing VLC…")
        try:
            _extract(archive, LOCAL_DIR)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise RuntimeError(f"Could not unpack VLC: {exc}") from exc


def _download(url: str, target: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, open(target, "wb") as out:
        shutil.copyfileobj(response, out)


def _verify_sha256(archive: Path, checksum_url: str) -> None:
    """Compares with the checksum published next to the file. If it is not published (404), only the zip's own
    integrity check applies; a published checksum that does not match raises ValueError."""
    try:
        with urllib.request.urlopen(checksum_url, timeout=30) as response:
            expected = response.read().decode("ascii", "ignore").split()[0].lower()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise
    digest = hashlib.sha256()
    with open(archive, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("the downloaded file is corrupted (checksum mismatch)")


def _extract(archive: Path, target: Path) -> None:
    """Unpacks VLC's zip (everything inside its single top folder) into `target`, replacing the previous copy."""
    staging = target.with_name(target.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as zf:
            if zf.testzip() is not None:
                raise ValueError("the downloaded file is corrupted")
            for member in zf.infolist():
                parts = Path(member.filename).parts[1:]   # drops "vlc-3.0.21/"
                if not parts or member.is_dir():
                    continue
                if ".." in parts or Path(*parts).is_absolute():
                    raise ValueError("unsafe path in the archive")
                destination = staging.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(destination, "wb") as out:
                    shutil.copyfileobj(source, out)
        if not ((staging / "libvlc.dll").is_file() and (staging / "plugins").is_dir()):
            raise ValueError("libvlc.dll is not in the archive")
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
