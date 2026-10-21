"""Self-update from GitHub Releases (no Qt, standard library only).

Packaged builds (PyInstaller) replace their own executable with the one attached to the
latest release. Runs from source / install.sh only get told that a new version exists.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import UPDATE_REPO, __version__

# Release asset name for each platform (must match the name in cinelocal.spec).
ASSETS = {"win32": "CineLocal-windows-x86_64.exe", "linux": "CineLocal-linux-x86_64"}


@dataclass
class Release:
    version: str
    page: str            # release web page
    url: str = ""        # direct download of this platform's file ("" = none published)
    sha256: str = ""     # expected checksum, when GitHub provides it


def enabled() -> bool:
    return bool(UPDATE_REPO)


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _numbers(version: str) -> tuple[int, ...]:
    nums = [int(n) for n in re.findall(r"\d+", version)]
    while nums and nums[-1] == 0:   # 1.11 == 1.11.0
        nums.pop()
    return tuple(nums)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return _numbers(candidate) > _numbers(current)


def _open(url: str, accept: str, timeout: int = 15):
    request = urllib.request.Request(url, headers={"User-Agent": f"CineLocal/{__version__}", "Accept": accept})
    return urllib.request.urlopen(request, timeout=timeout)


def parse_release(data: dict, platform: str = sys.platform) -> Release:
    asset = next((a for a in data.get("assets") or [] if a.get("name") == ASSETS.get(platform)), {})
    digest = asset.get("digest") or ""
    return Release(
        version=str(data.get("tag_name") or "").lstrip("vV"),
        page=data.get("html_url") or "",
        url=asset.get("browser_download_url") or "",
        sha256=digest[len("sha256:"):] if digest.startswith("sha256:") else "",
    )


def check() -> Release | None:
    """The latest release if it is newer than this version; None if not, or if offline."""
    try:
        with _open(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
                   "application/vnd.github+json") as response:
            release = parse_release(json.loads(response.read()))
    except (OSError, ValueError):
        return None
    return release if release.version and is_newer(release.version) else None


def _exe() -> Path:
    return Path(sys.executable).resolve()


def can_self_update(release: Release) -> bool:
    return frozen() and release.url.startswith("https://") and os.access(_exe().parent, os.W_OK)


def install(release: Release) -> None:
    """Downloads the new executable and puts it in place of the running one (restart afterwards)."""
    exe = _exe()
    new = exe.with_name(exe.name + ".new")
    digest = hashlib.sha256()
    try:
        with _open(release.url, "application/octet-stream", timeout=60) as src, open(new, "wb") as out:
            while chunk := src.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
        if release.sha256 and digest.hexdigest() != release.sha256:
            raise OSError("The downloaded update is corrupted (checksum mismatch).")
        os.chmod(new, 0o755)
        if os.name == "nt":   # a running .exe can be renamed, but not overwritten
            old = exe.with_name(exe.name + ".old")
            os.replace(exe, old)
            try:
                os.replace(new, exe)
            except OSError:
                os.replace(old, exe)
                raise
        else:
            os.replace(new, exe)
    finally:
        with contextlib.suppress(OSError):
            new.unlink()


def cleanup() -> None:
    """Removes the previous executable left behind by an update (Windows)."""
    if frozen():
        with contextlib.suppress(OSError):
            _exe().with_name(_exe().name + ".old").unlink()


def restart() -> None:
    # PYINSTALLER_RESET_ENVIRONMENT makes the new process unpack itself instead of reusing ours.
    subprocess.Popen([str(_exe()), *sys.argv[1:]], env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                     close_fds=True, start_new_session=os.name != "nt")
