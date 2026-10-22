"""Settings dialog: folder, TMDB key, language and player."""
from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ..config import LANGUAGES, TRACK_LANGUAGES
from ..providers import PROVIDERS
from ..service import LibraryService
from .restore_dialog import RestoreDialog

_HELP = {
    "tmdb": ('Free: create an account at <a href="https://www.themoviedb.org/signup">themoviedb.org</a>, '
             'open <a href="https://www.themoviedb.org/settings/api">Settings → API</a> and copy the '
             '“API Key” (or the “Read Access Token”).'),
    "omdb": ('Free (1,000 requests/day): request a key at <a href="https://www.omdbapi.com/apikey.aspx">'
             'omdbapi.com/apikey</a> and activate it with the link sent to your email. OMDb only has English '
             'data and provides no backdrop image or trailer.'),
}


class SettingsDialog(QDialog):
    edit_home_requested = Signal()

    def __init__(self, service: LibraryService, parent=None, intro: str = "",
                 focus_key: bool = False):
        super().__init__(parent)
        self.service = service
        self._closed = False
        self.saved = False
        self.restored = False
        s = service.settings
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(14)
        if intro:
            note = QLabel(intro)
            note.setWordWrap(True)
            root.addWidget(note)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(form.labelAlignment())

        self.folder_edit = QLineEdit(s.get("library_path"))
        self.folder_edit.setPlaceholderText("Folder containing all your movies")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        form.addRow("Movies folder", self._with_button(self.folder_edit, browse))

        self.provider = QComboBox()
        for code, name in PROVIDERS.items():
            self.provider.addItem(name, code)
        self.provider.setCurrentIndex(max(0, self.provider.findData(s.get("provider"))))
        form.addRow("Metadata source", self.provider)
        self._keys = {"tmdb": s.get("tmdb_api_key"), "omdb": s.get("omdb_api_key")}
        self._shown = self.provider.currentData()

        self.key_edit = QLineEdit(self._keys[self._shown])
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your API key here")
        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self._test_key)
        form.addRow("API key", self._with_button(self.key_edit, self.test_btn))

        self.key_status = QLabel("")
        self.key_status.setObjectName("muted")
        form.addRow("", self.key_status)
        self.help_label = help_label = QLabel(_HELP[self._shown])
        help_label.setOpenExternalLinks(True)
        help_label.setWordWrap(True)
        help_label.setObjectName("muted")
        form.addRow("", help_label)
        self.provider.currentIndexChanged.connect(self._on_provider)

        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(f"{name}  ({code})", code)
        current = s.get("language")
        index = self.language.findData(current)
        if index < 0:
            self.language.addItem(current, current)
            index = self.language.count() - 1
        self.language.setCurrentIndex(index)
        form.addRow("Metadata language", self.language)

        self.default_player = QComboBox()
        self.default_player.addItem("Built-in (VLC)", "builtin")
        self.default_player.addItem("External", "external")
        chosen = s.get("default_player") or ("external" if s.get("player_command").strip() else "builtin")
        self.default_player.setCurrentIndex(max(0, self.default_player.findData(chosen)))
        form.addRow("Default player", self.default_player)

        self.audio_language = self._track_combo(s.get("audio_language"), "File default")
        form.addRow("Audio language", self.audio_language)
        self.subtitle_language = self._track_combo(s.get("subtitle_language"), "File default")
        self.subtitle_language.insertItem(1, "Off (no subtitles)", "off")
        self.subtitle_language.insertItem(2, "Forced only (foreign-language parts)", "forced")
        self.subtitle_language.setCurrentIndex(max(0, self.subtitle_language.findData(s.get("subtitle_language"))))
        form.addRow("Subtitle language", self.subtitle_language)

        self.player_edit = QLineEdit(s.get("player_command"))
        self.player_edit.setPlaceholderText("Empty = system default player")
        pbrowse = QPushButton("Browse…")
        pbrowse.clicked.connect(self._browse_player)
        form.addRow("External player", self._with_button(self.player_edit, pbrowse))

        root.addLayout(form)

        buttons = QHBoxLayout()
        edit_home = QPushButton("Edit home…")
        edit_home.setToolTip("Choose which rows are shown above the movies, and their order")
        edit_home.clicked.connect(self.edit_home_requested)
        buttons.addWidget(edit_home)
        restore = QPushButton("Restore app…")
        restore.clicked.connect(self._restore)
        buttons.addWidget(restore)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setProperty("primary", True)
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        if focus_key:
            self.key_edit.setFocus()

    @staticmethod
    def _track_combo(current: str, default_label: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem(default_label, "")
        for code, (name, _aliases) in TRACK_LANGUAGES.items():
            combo.addItem(name, code)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        return combo

    @staticmethod
    def _with_button(edit: QLineEdit, button: QPushButton) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return box

    def _save(self) -> None:
        self.saved = True
        self.accept()

    def _restore(self) -> None:
        dialog = RestoreDialog(self)
        if dialog.exec() and self.service.restore(dialog.selected()):
            self.restored = True
            self.reject()   # unsaved changes in this window are discarded: the settings may have just been reset

    def done(self, result: int) -> None:
        self._closed = True
        super().done(result)

    def _browse_folder(self) -> None:
        start = self.folder_edit.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Select movies folder", start)
        if path:
            self.folder_edit.setText(path)

    def _browse_player(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose player", "/usr/bin")
        if path:
            self.player_edit.setText(path)

    def _on_provider(self) -> None:
        self._keys[self._shown] = self.key_edit.text()
        self._shown = self.provider.currentData()
        self.key_edit.setText(self._keys[self._shown])
        self.help_label.setText(_HELP[self._shown])
        self.key_status.setText("")

    def _test_key(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self.key_status.setText("Paste a key first.")
            return
        self.key_status.setText("Testing…")
        self.test_btn.setEnabled(False)
        self.service.test_key(key, self._key_ok, self._key_failed, self.provider.currentData())

    def _key_ok(self, _result) -> None:
        if not self._closed:
            self.test_btn.setEnabled(True)
            self.key_status.setText("Valid key.")

    def _key_failed(self, exc: Exception) -> None:
        if not self._closed:
            self.test_btn.setEnabled(True)
            self.key_status.setText(f"Error: {exc}")

    def values(self) -> dict:
        self._keys[self._shown] = self.key_edit.text()
        return {
            "library_path": self.folder_edit.text().strip(),
            "tmdb_api_key": self._keys["tmdb"].strip(),
            "omdb_api_key": self._keys["omdb"].strip(),
            "provider": self.provider.currentData(),
            "language": self.language.currentData(),
            "player_command": self.player_edit.text().strip(),
            "default_player": self.default_player.currentData(),
            "audio_language": self.audio_language.currentData(),
            "subtitle_language": self.subtitle_language.currentData(),
        }
