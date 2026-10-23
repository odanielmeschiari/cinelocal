"""Installs the downloaded single-file executable for the current user and adds it to the Start Menu
(Windows) or the application menu (Linux). It only runs from a PyInstaller build and needs no admin rights.
The paths match install.sh / install.bat, so uninstall.sh / uninstall.bat remove this install too.
Running the installed executable with --uninstall (menu entry "Uninstall CineLocal", or Settings > Apps on
Windows) removes it again, optionally with the library and settings."""
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
from .config import CACHE_DIR, CONFIG_DIR, DATA_DIR, Settings

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

UNINSTALL_ENTRY = """[Desktop Entry]
Type=Application
Name=Uninstall CineLocal
Exec="{exe}" --uninstall
Icon=cinelocal
Terminal=false
Categories=AudioVideo;Video;
"""

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\cinelocal"   # Windows: Settings > Apps


def installed_exe() -> Path:
    if WIN:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return local / "Programs" / APP_ID / f"{APP_NAME}.exe"
    return Path.home() / ".local" / "opt" / APP_ID / APP_NAME


def _start_menu_link() -> Path:
    roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"


def install(src: Path) -> Path:
    """Copies `src` to the install folder and creates the menu entry. Returns the installed executable."""
    dest = installed_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".new")
    shutil.copy2(src, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, dest)

    if WIN:
        import winreg
        lnk = _start_menu_link()
        lnk.parent.mkdir(parents=True, exist_ok=True)
        lnk.unlink(missing_ok=True)
        if not QFile.link(str(dest), str(lnk)):  # a .lnk; the icon comes from the .exe
            raise OSError("could not create the Start Menu shortcut")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            for name, value in (("DisplayName", APP_NAME), ("Publisher", APP_NAME), ("DisplayIcon", str(dest)),
                                ("UninstallString", f'"{dest}" --uninstall')):
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        return dest

    icon_root = Path.home() / ".local" / "share" / "icons" / "hicolor"
    icons = icon_root / "scalable" / "apps"
    apps = Path.home() / ".local" / "share" / "applications"
    icons.mkdir(parents=True, exist_ok=True)
    apps.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve().parent.parent / "assets" / "cinelocal.svg", icons / f"{APP_ID}.svg")
    (apps / f"{APP_ID}.desktop").write_text(DESKTOP_ENTRY.format(exe=dest), encoding="utf-8")
    (apps / f"{APP_ID}-uninstall.desktop").write_text(UNINSTALL_ENTRY.format(exe=dest), encoding="utf-8")
    for cmd in (["update-desktop-database", str(apps)], ["gtk-update-icon-cache", "-q", str(icon_root)]):
        try:
            subprocess.run(cmd, check=False, capture_output=True)
        except OSError:
            pass
    return dest


def uninstall(purge: bool) -> None:
    """Removes the installed app and its menu entries; with `purge`, also the library, posters and settings.
    Never touches the movies themselves."""
    folder = installed_exe().parent
    if WIN:
        import winreg
        _start_menu_link().unlink(missing_ok=True)
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        except OSError:
            pass
    else:
        home = Path.home()
        for f in (home / ".local" / "bin" / APP_ID,
                  home / ".local" / "share" / "applications" / f"{APP_ID}.desktop",
                  home / ".local" / "share" / "applications" / f"{APP_ID}-uninstall.desktop",
                  home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"):
            f.unlink(missing_ok=True)
    if purge:
        for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR):
            shutil.rmtree(d, ignore_errors=True)
    if WIN:  # the running .exe is locked: a detached shell removes the folder after this process exits
        subprocess.Popen(f'ping -n 4 127.0.0.1 >nul & rmdir /s /q "{folder}"', shell=True, close_fds=True,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    else:
        shutil.rmtree(folder, ignore_errors=True)


def uninstall_dialog() -> int:
    """Asks what to remove (the data only if the box is ticked), then uninstalls. Returns the exit code."""
    box = QMessageBox(QMessageBox.Question, APP_NAME, f"Uninstall {APP_NAME}?",
                      QMessageBox.Yes | QMessageBox.No)
    box.setInformativeText("Your movies are never deleted.")
    purge = QCheckBox("Also delete the library, posters and settings (cannot be undone)")
    box.setCheckBox(purge)
    box.setDefaultButton(QMessageBox.No)
    if box.exec() != QMessageBox.Yes:
        return 0
    try:
        uninstall(purge.isChecked())
    except OSError as e:
        QMessageBox.warning(None, APP_NAME, f"Could not uninstall {APP_NAME}:\n{e}")
        return 1
    QMessageBox.information(None, APP_NAME, f"{APP_NAME} was uninstalled."
                            + ("" if purge.isChecked() else " Your library and settings were kept."))
    return 0


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
