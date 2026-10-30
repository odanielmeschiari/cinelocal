"""Shared dialogs and menus (collections)."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QMenu, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from ..service import LibraryService
from ..utils import normalize_text
from .advanced_search import check_icon

_ON = Qt.UserRole + 2
ROW_HEIGHT = 18   # px of a row of a CheckList (the 3 px of spacing are added above and below)


class CheckList(QListWidget):
    """Rows with a box on the left: it is an icon, so it is always the same size, and a click anywhere on the row
    (or Space) checks or unchecks it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(3)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setIconSize(QSize(16, 16))
        self.itemClicked.connect(lambda item: self.mark(item, not item.data(_ON)))

    def add(self, text: str, key: int, on: bool) -> None:
        item = QListWidgetItem(text)
        item.setSizeHint(QSize(0, ROW_HEIGHT))   # fixed, so the rows never change size (not even after a click)
        item.setData(Qt.UserRole, key)
        item.setData(Qt.UserRole + 1, normalize_text(text))   # what the filter searches
        self.mark(item, on)
        self.addItem(item)

    @staticmethod
    def mark(item: QListWidgetItem, on: bool) -> None:
        item.setData(_ON, on)
        item.setIcon(check_icon(on))

    def checked(self) -> set[int]:
        items = (self.item(i) for i in range(self.count()))
        return {item.data(Qt.UserRole) for item in items if item.data(_ON)}

    def filter(self, text: str) -> None:
        terms = normalize_text(text).split()
        for i in range(self.count()):
            item = self.item(i)
            item.setHidden(not all(term in item.data(Qt.UserRole + 1) for term in terms))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space and self.currentItem() is not None:
            self.mark(self.currentItem(), not self.currentItem().data(_ON))
            return
        super().keyPressEvent(event)


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
        root.addWidget(self.search)

        self.movies = CheckList()
        self.search.textChanged.connect(self.movies.filter)
        for movie in sorted(movies, key=lambda m: (normalize_text(m["display_title"]), m["id"])):
            title_text = movie["display_title"]
            if movie.get("display_year"):
                title_text += f" ({movie['display_year']})"
            if movie.get("kind") == "series":
                title_text += " [Series]"
            self.movies.add(title_text, movie["id"], movie["id"] in selected_ids)
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
        return self.movies.checked()


class CollectionDialog(QDialog):
    """How a collection shows up in “All movies”: a stack of covers, a poster of its own, or its movies one by one."""

    CHOICES = (("stack", "Stack of covers", "One poster that opens the {noun}, with the next covers piled behind it."),
               ("cover", "Own cover", "One poster that opens the {noun}, using an image you choose."),
               ("separate", "All movies separately", "Every movie of the {noun} appears on its own."))

    def __init__(self, name: str, mode: str, has_cover: bool, parent=None, noun: str = "collection"):
        super().__init__(parent)
        self.setWindowTitle(f"Configure {noun}")
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
            note = QLabel(hint.format(noun=noun))
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


def ask_new_collection(parent: QWidget, service: LibraryService, kind: str = "collection") -> int | None:
    text = ""
    while True:
        name, ok = QInputDialog.getText(parent, f"New {kind}", f"{kind.capitalize()} name:", text=text)
        if not ok:
            return None
        try:
            return service.create_collection(name, kind)
        except ValueError as exc:
            QMessageBox.warning(parent, kind.capitalize(), str(exc))
            text = name


def ask_rename_collection(parent: QWidget, service: LibraryService, collection_id: int) -> None:
    text = service.collection_name(collection_id)
    noun = service.collection_kind(collection_id)
    while True:
        name, ok = QInputDialog.getText(parent, f"Rename {noun}", "New name:", text=text)
        if not ok:
            return
        try:
            service.rename_collection(collection_id, name)
            return
        except ValueError as exc:
            QMessageBox.warning(parent, noun.capitalize(), str(exc))
            text = name


def confirm_delete_collection(parent: QWidget, service: LibraryService, collection_id: int) -> bool:
    name = service.collection_name(collection_id)
    noun = service.collection_kind(collection_id)
    answer = QMessageBox.question(
        parent, f"Delete {noun}",
        f"Delete the {noun} “{name}”?\nThe movies will not be deleted, only removed from the {noun}.")
    if answer == QMessageBox.Yes:
        service.delete_collection(collection_id)
        return True
    return False


def populate_collections_menu(menu: QMenu, service: LibraryService,
                              movie_ids: list[int], parent: QWidget, kind: str = "collection") -> None:
    """Fills `menu` with the collections (or the lists: `kind`); checking/unchecking adds/removes the movies."""
    ids = list(movie_ids)
    id_set = set(ids)
    shown = [c for c in service.collections if c.get("kind", "collection") == kind]
    for collection in shown:
        members = service.membership.get(collection["id"], set())
        all_in = id_set <= members
        action = menu.addAction(collection["name"])
        action.setCheckable(True)
        action.setChecked(all_in)
        action.triggered.connect(
            lambda _checked=False, cid=collection["id"], present=not all_in:
            service.set_in_collection(cid, ids, present))
    if shown:
        menu.addSeparator()
    new_action = menu.addAction(f"New {kind}…")

    def create_and_add():
        collection_id = ask_new_collection(parent, service, kind)
        if collection_id is not None:
            service.set_in_collection(collection_id, ids, True)

    new_action.triggered.connect(create_and_add)
