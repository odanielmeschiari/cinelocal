"""Dialog to choose which rows the home screen shows, and in what order."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from ..service import LibraryService
from .advanced_search import check_icon

FIXED_SECTIONS = (("continue", "Continue watching"), ("history", "History"),
                  ("favorites", "Favorites"), ("watchlist", "Watchlist"))
_KEY, _ON = Qt.UserRole, Qt.UserRole + 1


def section_options(service: LibraryService) -> list[tuple[str, str]]:
    """Every row that can be on the home screen: (key, title)."""
    return list(FIXED_SECTIONS) + [(f"collection:{c['id']}", c["name"]) for c in service.collections]


class HomeDialog(QDialog):
    """`enabled` is the list of keys currently shown, in order; `keys()` gives the new list."""

    def __init__(self, service: LibraryService, enabled: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit home")
        self.setModal(True)
        self.setMinimumSize(460, 440)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(10)
        note = QLabel("Choose the rows shown above “All movies” and put them in the order you like.\n"
                      "Click a row to show or hide it; use “Move up” and “Move down” for the selected one.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)

        titles = dict(section_options(service))
        order = [k for k in enabled if k in titles] + [k for k in titles if k not in enabled]
        self.list = QListWidget()
        self.list.setIconSize(QSize(16, 16))
        for key in order:
            item = QListWidgetItem(titles[key] + ("  (collection)" if key.startswith("collection:") else ""))
            item.setData(_KEY, key)
            self._mark(item, key in enabled)
            self.list.addItem(item)
        self.list.itemClicked.connect(lambda item: self._mark(item, not item.data(_ON)))
        self.list.setCurrentRow(0)

        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        moves = QVBoxLayout()
        for text, step in (("Move up", -1), ("Move down", 1)):
            button = QPushButton(text)
            button.clicked.connect(lambda _c=False, s=step: self._move(s))
            moves.addWidget(button)
        moves.addStretch(1)
        body.addLayout(moves)
        root.addLayout(body, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setProperty("primary", True)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    @staticmethod
    def _mark(item: QListWidgetItem, on: bool) -> None:
        item.setData(_ON, on)
        item.setIcon(check_icon(on))

    def _move(self, step: int) -> None:
        row, target = self.list.currentRow(), self.list.currentRow() + step
        if row < 0 or not 0 <= target < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def keys(self) -> list[str]:
        items = (self.list.item(i) for i in range(self.list.count()))
        return [item.data(_KEY) for item in items if item.data(_ON)]
