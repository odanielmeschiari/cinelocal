"""Installs the downloaded single-file executable for the current user and adds it to the Start Menu
(Windows) or the application menu (Linux). It only runs from a PyInstaller build and needs no admin rights.
The paths match install.sh / install.bat, so uninstall.sh / uninstall.bat remove this install too."""
from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtWidgets import QCheckBox, QMessageBox

from . import APP_ID, APP_NAME
from .config import Settings

WIN = sys.platform == "win32"

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=CineLocal
Comment=Browse the movies in your local folder
Exec="{exe}"
Icon=cinelocal
Terminal=false
Categories=AudioVideo;Video;Player;
StartupWMClass=CineLocal
"""


def installed_exe() -> Path:
    if WIN:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return local / "Programs" / APP_ID / f"{APP_NAME}.exe"
    return Path.home() / ".local" / "opt" / APP_ID / APP_NAME


def install(src: Path) -> Path:
    """Copies `src` to the install folder and creates the menu entry. Returns the installed executable."""
    dest = installed_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".new")
    shutil.copy2(src, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, dest)

    if WIN:
        roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        lnk = roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"
        lnk.parent.mkdir(parents=True, exist_ok=True)
        lnk.unlink(missing_ok=True)
        if not QFile.link(str(dest), str(lnk)):  # a .lnk; the icon comes from the .exe
            raise OSError("could not create the Start Menu shortcut")
        return dest

    icon_root = Path.home() / ".local" / "share" / "icons" / "hicolor"
    icons = icon_root / "scalable" / "apps"
    apps = Path.home() / ".local" / "share" / "applications"
    icons.mkdir(parents=True, exist_ok=True)
    apps.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve().parent.parent / "assets" / "cinelocal.svg", icons / f"{APP_ID}.svg")
    (apps / f"{APP_ID}.desktop").write_text(DESKTOP_ENTRY.format(exe=dest), encoding="utf-8")
    for cmd in (["update-desktop-database", str(apps)], ["gtk-update-icon-cache", "-q", str(icon_root)]):
        try:
            subprocess.run(cmd, check=False, capture_output=True)
        except OSError:
            pass
    return dest


def maybe_install(settings: Settings) -> None:
    """Offers to install when running a downloaded executable (or a newer one than the installed copy)."""
    if not getattr(sys, "frozen", False) or settings.get("skip_install_prompt"):
        return
    src, dest = Path(sys.executable).resolve(), installed_exe()
    updating = dest.exists()
    if updating and (src == dest.resolve() or filecmp.cmp(src, dest, shallow=False)):
        return
    menu = "Start Menu" if WIN else "application menu"
    box = QMessageBox(QMessageBox.Question, APP_NAME,
                      f"Update the installed {APP_NAME} with this version?" if updating
                      else f"Install {APP_NAME} on this computer?",
                      QMessageBox.Yes | QMessageBox.No)
    box.setInformativeText(f"It will be added to the {menu}, so you can open it from there "
                           "(no administrator rights needed).")
    never = QCheckBox("Don't ask again")
    box.setCheckBox(never)
    if box.exec() != QMessageBox.Yes:
        if never.isChecked():
            settings.update(skip_install_prompt=True)
        return
    try:
        install(src)
    except OSError as e:
        QMessageBox.warning(None, APP_NAME, f"Could not install {APP_NAME}:\n{e}\n\n"
                            "If it is already open, close it and try again.")
        return
    QMessageBox.information(None, APP_NAME, f"{APP_NAME} is installed. Next time, open it from the {menu}; "
                            "you can delete the downloaded file.")
