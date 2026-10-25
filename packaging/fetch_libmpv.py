#!/usr/bin/env python3
"""Downloads libmpv (libmpv-2.dll, Windows x86-64) into a folder, for the built-in player's GPU upscaling.

Usage: python packaging/fetch_libmpv.py DEST_DIR [--force] [--latest]
       python packaging/fetch_libmpv.py --print-lock

Used by install.bat (DEST_DIR = <app folder>\\libmpv) and by the release workflow (the DLL is then bundled by
cinelocal.spec). Standard library only. By default it installs the build pinned in packaging/libmpv-windows.lock.json
(tag, file name and SHA-256 of the "mpv-dev-lgpl-x86_64" build of github.com/zhongfly/mpv-winbuild: the LGPL flavour,
which is the one to redistribute), so every build uses the same DLL. The download is checked against that SHA-256 before
anything is unpacked. That repository only keeps recent releases: when the pinned one is gone, run `--print-lock` (it
resolves the newest release, downloads it, and prints a new lock file), review it and commit it, or mirror the file in
your own release and point "repo" there. `--latest` skips the pin and takes the newest release, checked against the
sha256.txt published with it (less reproducible). The .7z uses the BCJ2 filter, so it is unpacked with 7-Zip
(7z, or 7zr.exe downloaded from 7-zip.org if nothing else works) or with bsdtar (the tar.exe of Windows 10/11).
Exit code 0 = the DLL is in DEST_DIR; 1 = it could not be installed (the release workflow treats that as fatal; install.bat
does not: the player then uses VLC).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

RELEASES = "https://github.com/zhongfly/mpv-winbuild/releases"
LOCK_FILE = Path(__file__).resolve().with_name("libmpv-windows.lock.json")
DLL = "libmpv-2.dll"
ASSET = re.compile(r"mpv-dev-lgpl-x86_64-\d{8}-git-[0-9a-f]+\.7z")   # not "-v3-" (that one needs AVX2)
SEVEN_ZR = "https://www.7-zip.org/a/7zr.exe"
MIN_DLL_SIZE = 10_000_000
HEADERS = {"User-Agent": "cinelocal-install"}


def say(message: str) -> None:
    print(message, flush=True)


def fetch(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60)


def fetch_text(url: str) -> str:
    with fetch(url) as response:
        return response.read().decode("utf-8", "replace")


def latest_tag() -> str:
    """Tag of the newest release (GitHub redirects /releases/latest to /releases/tag/<tag>; no API, no rate limit)."""
    with fetch(f"{RELEASES}/latest") as response:
        tag = response.geturl().rstrip("/").rsplit("/", 1)[-1]
    if not tag or tag == "latest":
        raise RuntimeError("could not find the latest libmpv release")
    return tag


def find_asset(html: str) -> str | None:
    match = ASSET.search(html)
    return match.group(0) if match else None


def parse_checksums(text: str) -> dict[str, str]:
    """sha256.txt: one 'hash  file name' per line."""
    found = {}
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line)
        if match:
            found[match.group(2)] = match.group(1).lower()
    return found


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    with fetch(url) as response, open(dest, "wb") as out:
        total, done, shown = int(response.headers.get("Content-Length") or 0), 0, -1
        for block in iter(lambda: response.read(1 << 20), b""):
            out.write(block)
            done += len(block)
            if total and done * 10 // total != shown:   # a line every 10%
                shown = done * 10 // total
                say(f"    {done * 100 // total}%  ({done // 1_000_000} of {total // 1_000_000} MB)")


def looks_like_dll(path: Path) -> bool:
    try:
        if path.stat().st_size < MIN_DLL_SIZE:
            return False
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except OSError:
        return False


def _seven_zip_programs() -> list[str]:
    found = [p for p in (shutil.which(n) for n in ("7z", "7zz", "7za", "7zr")) if p]
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        candidate = Path(os.environ.get(var, "")) / "7-Zip" / "7z.exe"
        if os.environ.get(var) and candidate.is_file():
            found.append(str(candidate))
    return found


def _tar_programs() -> list[str]:
    found = []
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    if os.name == "nt" and system32.is_file():
        found.append(str(system32))   # bsdtar: reads .7z (a GNU tar found first on PATH could not)
    found += [p for p in (shutil.which("bsdtar"),) if p]
    return found


def extract_dll(archive: Path, workdir: Path) -> Path | None:
    """Unpacks only the DLL, trying every extractor available until one produces a valid file."""
    out = workdir / "out"
    attempts = [[p, "x", "-y", f"-o{out}", str(archive), DLL] for p in _seven_zip_programs()]
    attempts += [[p, "-xf", str(archive), "-C", str(out), DLL] for p in _tar_programs()]
    if os.name == "nt":   # nothing usable found: 7-Zip's own standalone extractor
        attempts.append(None)
    for command in attempts:
        out.mkdir(exist_ok=True)
        if command is None:
            try:
                say("    downloading 7zr.exe (7-Zip's standalone extractor) to unpack it")
                seven_zr = workdir / "7zr.exe"
                download(SEVEN_ZR, seven_zr)
                if seven_zr.read_bytes()[:2] != b"MZ":   # an error page instead of the program
                    continue
                command = [str(seven_zr), "x", "-y", f"-o{out}", str(archive), DLL]
            except (OSError, urllib.error.URLError):
                continue
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=600, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            continue
        if looks_like_dll(out / DLL):
            return out / DLL
    return None


_PROBE = ("import os, sys\nos.add_dll_directory(sys.argv[1])\n"
          "os.environ['PATH'] = sys.argv[1] + os.pathsep + os.environ['PATH']\n"
          "import mpv\nmpv.MPV(vo='null', ao='null').terminate()\n")


def probe(dest: Path) -> None:
    """Windows: the DLL must really load through python-mpv, otherwise it is removed (the player then uses VLC)."""
    result = subprocess.run([sys.executable, "-c", _PROBE, str(dest)], capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        say("    libmpv loads correctly")
    elif "No module named 'mpv'" in result.stderr:
        say("    (python-mpv is not installed in this Python; skipping the load test)")
    else:
        (dest / DLL).unlink(missing_ok=True)
        raise RuntimeError("the downloaded libmpv does not load here: " + (result.stderr.strip().splitlines() or ["?"])[-1])


def load_lock(path: Path = LOCK_FILE) -> dict:
    """The pinned build: {"repo", "tag", "asset", "sha256"}."""
    lock = json.loads(path.read_text(encoding="utf-8"))
    if not all(isinstance(lock.get(k), str) and lock[k] for k in ("repo", "tag", "asset", "sha256")) \
            or not re.fullmatch(r"[0-9a-f]{64}", lock["sha256"]):
        raise RuntimeError(f"{path.name} is not a valid lock file (needs repo, tag, asset and a 64-digit sha256)")
    return lock


def resolve_latest() -> dict:
    """The newest release, with the SHA-256 its own sha256.txt publishes."""
    tag = latest_tag()
    asset = find_asset(fetch_text(f"{RELEASES}/expanded_assets/{tag}"))
    if not asset:
        raise RuntimeError(f"release {tag} has no libmpv build for Windows x86-64 (try again later)")
    expected = parse_checksums(fetch_text(f"{RELEASES}/download/{tag}/sha256.txt")).get(asset)
    if not expected:
        raise RuntimeError(f"release {tag} has no checksum for {asset}; not installing an unverified download")
    return {"repo": RELEASES, "tag": tag, "asset": asset, "sha256": expected}


def fetch_verified(build: dict, workdir: Path) -> Path:
    """Downloads the build into workdir and returns the archive, only if it matches the SHA-256."""
    say(f"==> Downloading {build['asset']}")
    archive = workdir / build["asset"]
    try:
        download(f"{build['repo']}/download/{build['tag']}/{build['asset']}", archive)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"release {build['tag']} is no longer published at {build['repo']}; update "
                               "packaging/libmpv-windows.lock.json (run this script with --print-lock)") from e
        raise
    if sha256_of(archive) != build["sha256"]:
        raise RuntimeError("the download does not match its expected SHA-256; not installing it")
    return archive


def install(dest: Path, latest: bool = False) -> None:
    build = resolve_latest() if latest else load_lock()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        archive = fetch_verified(build, work)
        say("==> Unpacking libmpv")
        dll = extract_dll(archive, work)
        if dll is None:
            raise RuntimeError("could not unpack the .7z (install 7-Zip, or use Windows 10/11 with tar.exe)")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dll, dest / (DLL + ".part"))
        os.replace(dest / (DLL + ".part"), dest / DLL)
    if os.name == "nt":
        probe(dest)
    say(f"==> libmpv installed in {dest}")


def print_lock() -> None:
    """Resolves the newest release and prints the lock file for it, with a SHA-256 computed here from the download
    (it must also match the one the release publishes)."""
    build = resolve_latest()
    with tempfile.TemporaryDirectory() as tmp:
        archive = fetch_verified(build, Path(tmp))
        build["sha256"] = sha256_of(archive)
    print(json.dumps(build, indent=2))


def main(argv: list[str]) -> int:
    force, latest = "--force" in argv, "--latest" in argv
    if "--print-lock" in argv:
        try:
            print_lock()
        except (OSError, urllib.error.URLError, RuntimeError) as e:
            print(f"could not resolve the newest libmpv release: {e}", file=sys.stderr)
            return 1
        return 0
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    dest = Path(args[0]).resolve()
    if (dest / DLL).is_file() and not force:
        say(f"libmpv is already in {dest} (use --force to download it again)")
        return 0
    try:
        install(dest, latest=latest)
    except (OSError, urllib.error.URLError, subprocess.SubprocessError, RuntimeError, ValueError) as e:
        print(f"libmpv could not be installed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
