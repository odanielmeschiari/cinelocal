# PyInstaller recipe for a folder build (dist/CineLocal/):  pyinstaller --noconfirm cinelocal.spec
# A folder (not a single file) starts fast: nothing is unpacked to a temp folder on every launch.
# Install VLC first: its libraries are bundled so the built-in player works without VLC installed.
import os
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
    """Optional, Windows only: mpv-2.dll from $MPV_DIR gives the built-in player GPU upscaling. Without it the build
    still works and the player uses VLC. On Linux the system libmpv is used (the .deb recommends it)."""
    root = os.environ.get("MPV_DIR")
    dlls = [Path(root) / name for name in ("mpv-2.dll", "libmpv-2.dll")] if win and root else []
    return [(str(dll), ".") for dll in dlls if dll.is_file()]


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
