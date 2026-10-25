# PyInstaller recipe for a folder build (dist/CineLocal/):  pyinstaller --noconfirm cinelocal.spec
# A folder (not a single file) starts fast: nothing is unpacked to a temp folder on every launch.
# Install VLC first: its libraries are bundled so the built-in player works without VLC installed.
import os
import shutil
import sys
from pathlib import Path

win = sys.platform == "win32"


def vlc_binaries():
    """libVLC and its plugins. Looked up in $VLC_DIR (the VLC folder on Windows, the library folder on
    Linux) or in the usual place; if VLC is not found the build still works, without the built-in player."""
    if win:
        root = Path(os.environ.get("VLC_DIR", r"C:\Program Files\VideoLAN\VLC"))
        libs, plugins = [root / "libvlc.dll", root / "libvlccore.dll"], root / "plugins"
    else:
        root = Path(os.environ.get("VLC_DIR", "/usr/lib/x86_64-linux-gnu"))
        libs, plugins = [root / "libvlc.so.5", root / "libvlccore.so.9"], root / "vlc" / "plugins"
    if not (all(lib.is_file() for lib in libs) and plugins.is_dir()):
        if os.environ.get("CI"):   # GitHub Actions: a release without the built-in player must not be published
            raise SystemExit(f"VLC not found in {root}: install it (and set VLC_DIR if needed) before building")
        print("WARNING: VLC not found - building without the built-in player libraries")
        return []
    found = [(str(lib), ".") for lib in libs]
    plugin_dir = "plugins" if win else "vlc/plugins"   # Windows: libVLC looks for "plugins" next to libvlccore.dll
    for plugin in plugins.rglob("*"):
        if plugin.suffix in (".dll", ".so"):
            found.append((str(plugin), str(Path(plugin_dir) / plugin.parent.relative_to(plugins))))
    return found


def mpv_binaries():
    """libmpv gives the built-in player GPU upscaling.
    Windows (optional): mpv-2.dll / libmpv-2.dll from $MPV_DIR (packaging/fetch_libmpv.py puts the pinned build there).
    Without it a local build still works and the player uses VLC (the release workflow refuses to build without it).
    Linux: with BUNDLE_LINUX_LIBMPV=1 the build must carry libmpv.so.2 (or .so.1) found in $MPV_DIR (default: the library
    folder), and fails if it is missing; PyInstaller then bundles the libraries libmpv needs. Without the variable the
    spec adds nothing, but PyInstaller itself bundles libmpv when it is installed on the build machine (python-mpv looks
    it up with find_library). Ubuntu's libmpv binaries are GPL-3.0-or-later: see THIRD_PARTY_NOTICES.md before publishing."""
    root = os.environ.get("MPV_DIR")
    if win:
        dlls = [Path(root) / name for name in ("mpv-2.dll", "libmpv-2.dll")] if root else []
        found = [(str(dll), ".") for dll in dlls if dll.is_file()]
        if not found and os.environ.get("CI"):   # GitHub Actions: the release must carry its own libmpv
            raise SystemExit(f"libmpv-2.dll not found in MPV_DIR={root!r}: run packaging/fetch_libmpv.py first")
        return found
    if os.environ.get("BUNDLE_LINUX_LIBMPV") != "1":
        return []
    folder = Path(root or "/usr/lib/x86_64-linux-gnu")
    for name in ("libmpv.so.2", "libmpv.so.1"):
        if (folder / name).is_file():
            return [(str(folder / name), ".")]
    raise SystemExit(f"BUNDLE_LINUX_LIBMPV=1 but libmpv.so.2 / libmpv.so.1 not found in {folder}: install libmpv2 (libmpv1)")


a = Analysis(
    ["main.py"],
    binaries=vlc_binaries() + mpv_binaries(),
    datas=[("assets/cinelocal.svg", "assets")],
    hiddenimports=["PySide6.QtSvg", "vlc", "mpv"],   # QtSvg: the .svg window icon; vlc, mpv: imported lazily
)
exe = EXE(
    PYZ(a.pure),
    a.scripts, [],
    exclude_binaries=True,
    name="CineLocal",
    console=False,
    icon="assets/cinelocal.ico" if win else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="CineLocal", upx=False)
shutil.copy2("THIRD_PARTY_NOTICES.md", Path(DISTPATH) / "CineLocal" / "THIRD_PARTY_NOTICES.md")   # next to the executable
