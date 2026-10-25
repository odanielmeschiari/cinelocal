"""Settings dialog: folder, TMDB key, language and player."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCursor, QImage
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from .. import images
from ..config import LANGUAGES, TRACK_LANGUAGES
from ..service import LibraryService
from .advanced_search import check_icon
from .restore_dialog import RestoreDialog

_HELP = ('Free: create an account at <a href="https://www.themoviedb.org/signup">themoviedb.org</a>, '
         'open <a href="https://www.themoviedb.org/settings/api">Settings → API</a> and copy the '
         '“API Key” (or the “Read Access Token”).')
_HELP_SUBTITLES = ('With a key, the subtitle of each new movie is downloaded automatically, in the language above '
                   '(or the metadata language), and saved next to the video. Free: create an account at '
                   '<a href="https://www.opensubtitles.com/en/consumers">opensubtitles.com</a> and register an API '
                   'consumer. There is a daily download limit; what is left is downloaded on the next scan.')


class GroupCollectionsDialog(QDialog):
    """Pick the collections that “All movies” shows as a single poster, and how each one looks there:
    a stack of covers (default) or a poster chosen by the user."""

    def __init__(self, collections: list[dict], grouped: list[int], styles: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Group collections")
        self.setModal(True)
        self.setMinimumSize(460, 480)
        self.styles = dict(styles)   # str(collection id) -> "cover"
        self.new_covers: dict[int, str] = {}   # collection id -> image file picked in this dialog
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(10)
        note = QLabel("In “All movies”, the checked collections show up as one poster named after the collection, "
                      "which opens it. Click the box to check or uncheck; select a collection to choose how it "
                      "looks.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)
        self.list = QListWidget()
        for c in collections:
            item = QListWidgetItem()
            item.setText(c["name"])
            item.setData(Qt.UserRole, c["id"])
            item.setSizeHint(QSize(0, 36))
            self._mark(item, c["id"] in grouped)
            self.list.addItem(item)
        self.list.itemClicked.connect(self._clicked)
        self.list.currentItemChanged.connect(self._load_look)
        root.addWidget(self.list, 1)

        look = QHBoxLayout()
        self.look = QComboBox()
        self.look.addItem("Stack of covers", "stack")
        self.look.addItem("Own poster", "cover")
        self.look.activated.connect(self._look_chosen)
        self.pick = QPushButton("Choose poster…")
        self.pick.clicked.connect(self._pick_poster)
        look.addWidget(QLabel("Look"))
        look.addWidget(self.look, 1)
        look.addWidget(self.pick)
        root.addLayout(look)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setProperty("primary", True)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)
        self.list.setCurrentRow(0)
        self._load_look()

    @staticmethod
    def _mark(item: QListWidgetItem, on: bool) -> None:
        item.setData(Qt.UserRole + 1, on)
        item.setIcon(check_icon(on))

    def _clicked(self, item: QListWidgetItem) -> None:
        if self.list.viewport().mapFromGlobal(QCursor.pos()).x() < 40:   # only the box toggles
            self._mark(item, not item.data(Qt.UserRole + 1))

    def _current_id(self) -> int | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _load_look(self, *_args) -> None:
        collection_id = self._current_id()
        self.look.setEnabled(collection_id is not None)
        self.look.setCurrentIndex(1 if self.styles.get(str(collection_id)) == "cover" else 0)
        self.pick.setEnabled(self.look.currentData() == "cover")

    def _look_chosen(self) -> None:
        collection_id = self._current_id()
        if self.look.currentData() == "cover":
            if collection_id in self.new_covers or images.collection_cover(collection_id) or self._pick_poster():
                self.styles[str(collection_id)] = "cover"
        else:
            self.styles.pop(str(collection_id), None)
        self._load_look()

    def _pick_poster(self) -> bool:
        collection_id = self._current_id()
        path, _ = QFileDialog.getOpenFileName(self, "Choose poster", os.path.expanduser("~"),
                                              "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not path or QImage(path).isNull():
            return False
        self.new_covers[collection_id] = path
        self.styles[str(collection_id)] = "cover"
        self._load_look()
        return True

    def ids(self) -> list[int]:
        items = (self.list.item(i) for i in range(self.list.count()))
        return [item.data(Qt.UserRole) for item in items if item.data(Qt.UserRole + 1)]


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
        self.grouped = list(s.get("grouped_collections") or [])
        self.cover_styles = dict(s.get("collection_covers") or {})
        self.new_covers: dict[int, str] = {}   # posters picked for collections, copied when the settings are saved
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

        self.key_edit = QLineEdit(s.get("tmdb_api_key"))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your API key here")
        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self._test_key)
        form.addRow("API key", self._with_button(self.key_edit, self.test_btn))

        self.key_status = QLabel("")
        self.key_status.setObjectName("muted")
        form.addRow("", self.key_status)
        self.help_label = help_label = QLabel(_HELP)
        help_label.setOpenExternalLinks(True)
        help_label.setWordWrap(True)
        help_label.setObjectName("muted")
        form.addRow("", help_label)

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

        self.group_auto = QCheckBox("Group automatic collections (franchises) in “All movies”")
        self.group_auto.setChecked(bool(s.get("group_auto_collections")))
        form.addRow("Collections", self.group_auto)

        self.opensubtitles_key = QLineEdit(s.get("opensubtitles_api_key"))
        self.opensubtitles_key.setEchoMode(QLineEdit.Password)
        self.opensubtitles_key.setPlaceholderText("Optional: OpenSubtitles API key")
        form.addRow("OpenSubtitles key", self.opensubtitles_key)
        opensubtitles_help = QLabel(_HELP_SUBTITLES)
        opensubtitles_help.setOpenExternalLinks(True)
        opensubtitles_help.setWordWrap(True)
        opensubtitles_help.setObjectName("muted")
        form.addRow("", opensubtitles_help)

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
        group = QPushButton("Group collections…")
        group.setToolTip("Choose collections that “All movies” shows as a single poster")
        group.clicked.connect(self._group_collections)
        buttons.addWidget(group)
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
        for collection_id, source in self.new_covers.items():
            if self.cover_styles.get(str(collection_id)) == "cover":
                images.store_collection_cover(collection_id, source)
        self.saved = True
        self.accept()

    def _group_collections(self) -> None:
        dialog = GroupCollectionsDialog(self.service.collections, self.grouped, self.cover_styles, self)
        if dialog.exec():
            self.grouped = dialog.ids()
            self.cover_styles = dialog.styles
            self.new_covers.update(dialog.new_covers)

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

    def _test_key(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self.key_status.setText("Paste a key first.")
            return
        self.key_status.setText("Testing…")
        self.test_btn.setEnabled(False)
        self.service.test_key(key, self._key_ok, self._key_failed)

    def _key_ok(self, _result) -> None:
        if not self._closed:
            self.test_btn.setEnabled(True)
            self.key_status.setText("Valid key.")

    def _key_failed(self, exc: Exception) -> None:
        if not self._closed:
            self.test_btn.setEnabled(True)
            self.key_status.setText(f"Error: {exc}")

    def values(self) -> dict:
        return {
            "library_path": self.folder_edit.text().strip(),
            "tmdb_api_key": self.key_edit.text().strip(),
            "language": self.language.currentData(),
            "player_command": self.player_edit.text().strip(),
            "default_player": self.default_player.currentData(),
            "audio_language": self.audio_language.currentData(),
            "subtitle_language": self.subtitle_language.currentData(),
            "opensubtitles_api_key": self.opensubtitles_key.text().strip(),
            "grouped_collections": self.grouped,
            "group_auto_collections": self.group_auto.isChecked(),
            "collection_covers": self.cover_styles,
        }
