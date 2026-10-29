"""Shared dialogs and menus (collections)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QMenu, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from ..service import LibraryService
from ..utils import normalize_text


class MovieSelectionDialog(QDialog):
    def __init__(self, movies: list[dict], selected_ids: set[int], title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(480, 560)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Select the movies to include:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter movies…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)

        self.movies = QListWidget()
        self.movies.setSpacing(3)
        for movie in sorted(movies, key=lambda m: (normalize_text(m["display_title"]), m["id"])):
            title_text = movie["display_title"]
            if movie.get("display_year"):
                title_text += f" ({movie['display_year']})"
            if movie.get("kind") == "series":
                title_text += " [Series]"
            item = QListWidgetItem(title_text)
            item.setData(Qt.UserRole, movie["id"])
            item.setData(Qt.UserRole + 1, normalize_text(title_text))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if movie["id"] in selected_ids else Qt.Unchecked)
            self.movies.addItem(item)
        root.addWidget(self.movies, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def selected_ids(self) -> set[int]:
        return {
            self.movies.item(index).data(Qt.UserRole)
            for index in range(self.movies.count())
            if self.movies.item(index).checkState() == Qt.Checked
        }

    def _filter(self, text: str) -> None:
        terms = normalize_text(text).split()
        for index in range(self.movies.count()):
            item = self.movies.item(index)
            item.setHidden(not all(term in item.data(Qt.UserRole + 1) for term in terms))


class CollectionDialog(QDialog):
    """How a collection shows up in “All movies”: a stack of covers, a poster of its own, or its movies one by one."""

    CHOICES = (("stack", "Stack of covers", "One poster that opens the collection, with the next covers piled behind it."),
               ("cover", "Own cover", "One poster that opens the collection, using an image you choose."),
               ("separate", "All movies separately", "Every movie of the collection appears on its own."))

    def __init__(self, name: str, mode: str, has_cover: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure collection")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.new_cover: str | None = None   # image picked in this dialog (copied by the caller when accepted)
        self._has_cover = has_cover
        self._mode = mode
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(8)
        title = QLabel(name)
        title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        root.addWidget(title)
        self.radios: dict[str, QRadioButton] = {}
        for key, label, hint in self.CHOICES:
            radio = QRadioButton(label)
            radio.setChecked(key == mode)
            radio.toggled.connect(lambda checked, key=key: checked and self._chosen(key))
            note = QLabel(hint)
            note.setObjectName("muted")
            note.setWordWrap(True)
            note.setContentsMargins(26, 0, 0, 6)
            self.radios[key] = radio
            root.addWidget(radio)
            if key == "cover":
                row = QHBoxLayout()
                row.addWidget(note, 1)
                self.pick = QPushButton("Choose poster…")
                self.pick.clicked.connect(self._pick_poster)
                row.addWidget(self.pick)
                root.addLayout(row)
            else:
                root.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        ok = QPushButton("OK")
        ok.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        root.addLayout(buttons)
        self.pick.setEnabled(mode == "cover")

    def mode(self) -> str:
        return self._mode

    def _chosen(self, key: str) -> None:
        if key == "cover" and not (self._has_cover or self.new_cover) and not self._pick_poster():
            self.radios[self._mode].setChecked(True)   # no image picked: stays as it was
            return
        self._mode = key
        self.pick.setEnabled(key == "cover")

    def _pick_poster(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Choose poster", os.path.expanduser("~"),
                                              "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not path or QImage(path).isNull():
            return False
        self.new_cover = path
        return True


def ask_new_collection(parent: QWidget, service: LibraryService) -> int | None:
    text = ""
    while True:
        name, ok = QInputDialog.getText(parent, "New collection", "Collection name:", text=text)
        if not ok:
            return None
        try:
            return service.create_collection(name)
        except ValueError as exc:
            QMessageBox.warning(parent, "Collection", str(exc))
            text = name


def ask_rename_collection(parent: QWidget, service: LibraryService, collection_id: int) -> None:
    text = service.collection_name(collection_id)
    while True:
        name, ok = QInputDialog.getText(parent, "Rename collection", "New name:", text=text)
        if not ok:
            return
        try:
            service.rename_collection(collection_id, name)
            return
        except ValueError as exc:
            QMessageBox.warning(parent, "Collection", str(exc))
            text = name


def confirm_delete_collection(parent: QWidget, service: LibraryService, collection_id: int) -> bool:
    name = service.collection_name(collection_id)
    answer = QMessageBox.question(
        parent, "Delete collection",
        f"Delete the collection “{name}”?\nThe movies will not be deleted, only removed from the collection.")
    if answer == QMessageBox.Yes:
        service.delete_collection(collection_id)
        return True
    return False


def populate_collections_menu(menu: QMenu, service: LibraryService,
                              movie_ids: list[int], parent: QWidget) -> None:
    """Fills `menu` with the collections; checking/unchecking adds/removes the movies."""
    ids = list(movie_ids)
    id_set = set(ids)
    for collection in service.collections:
        members = service.membership.get(collection["id"], set())
        all_in = id_set <= members
        action = menu.addAction(collection["name"])
        action.setCheckable(True)
        action.setChecked(all_in)
        action.triggered.connect(
            lambda _checked=False, cid=collection["id"], present=not all_in:
            service.set_in_collection(cid, ids, present))
    if service.collections:
        menu.addSeparator()
    new_action = menu.addAction("New collection…")

    def create_and_add():
        collection_id = ask_new_collection(parent, service)
        if collection_id is not None:
            service.set_in_collection(collection_id, ids, True)

    new_action.triggered.connect(create_and_add)
