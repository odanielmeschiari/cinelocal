#!/usr/bin/env python3
"""Downloads libmpv (libmpv-2.dll, Windows x86-64) into a folder, for the built-in player's GPU upscaling.

Usage: python packaging/fetch_libmpv.py DEST_DIR [--force]

Used by install.bat (DEST_DIR = <app folder>\\libmpv) and by the release workflow (the DLL is then bundled by
cinelocal.spec). Standard library only. It takes the newest "mpv-dev-lgpl-x86_64" build published by
github.com/zhongfly/mpv-winbuild (the LGPL flavour, which is the one to redistribute) and checks its SHA-256 against the
sha256.txt of the same release before unpacking anything. The .7z uses the BCJ2 filter, so it is unpacked with 7-Zip
(7z, or 7zr.exe downloaded from 7-zip.org if nothing else works) or with bsdtar (the tar.exe of Windows 10/11).
Exit code 0 = the DLL is in DEST_DIR; 1 = it could not be installed (callers treat that as non-fatal: the player then
uses VLC).
"""
from __future__ import annotations

import hashlib
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


def install(dest: Path) -> None:
    tag = latest_tag()
    asset = find_asset(fetch_text(f"{RELEASES}/expanded_assets/{tag}"))
    if not asset:
        raise RuntimeError(f"release {tag} has no libmpv build for Windows x86-64 (try again later)")
    expected = parse_checksums(fetch_text(f"{RELEASES}/download/{tag}/sha256.txt")).get(asset)
    if not expected:
        raise RuntimeError(f"release {tag} has no checksum for {asset}; not installing an unverified download")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        say(f"==> Downloading {asset}")
        download(f"{RELEASES}/download/{tag}/{asset}", work / asset)
        if sha256_of(work / asset) != expected:
            raise RuntimeError("the download does not match its published SHA-256; not installing it")
        say("==> Unpacking libmpv")
        dll = extract_dll(work / asset, work)
        if dll is None:
            raise RuntimeError("could not unpack the .7z (install 7-Zip, or use Windows 10/11 with tar.exe)")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dll, dest / (DLL + ".part"))
        os.replace(dest / (DLL + ".part"), dest / DLL)
    if os.name == "nt":
        probe(dest)
    say(f"==> libmpv installed in {dest}")


def main(argv: list[str]) -> int:
    force = "--force" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    dest = Path(args[0]).resolve()
    if (dest / DLL).is_file() and not force:
        say(f"libmpv is already in {dest} (use --force to download it again)")
        return 0
    try:
        install(dest)
    except (OSError, urllib.error.URLError, subprocess.SubprocessError, RuntimeError) as e:
        print(f"libmpv could not be installed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
