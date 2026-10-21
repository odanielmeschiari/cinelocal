# PyInstaller recipe for a single-file build:  pyinstaller --noconfirm cinelocal.spec
# The output name must match ASSETS in cinelocal/updater.py.
import sys

win = sys.platform == "win32"

a = Analysis(
    ["main.py"],
    datas=[("assets/cinelocal.svg", "assets")],
    hiddenimports=["PySide6.QtSvg"],   # for the .svg window icon
)
exe = EXE(
    PYZ(a.pure),
    a.scripts, a.binaries, a.datas, [],
    name="CineLocal-windows-x86_64" if win else "CineLocal-linux-x86_64",
    console=False,
    icon="assets/cinelocal.ico" if win else None,
    upx=False,
)
