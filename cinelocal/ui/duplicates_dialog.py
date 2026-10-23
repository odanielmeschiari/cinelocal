"""List of files that look like the same movie or episode, to decide which one to keep."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ..duplicates import find_duplicates
from ..mediainfo import badges
from ..service import LibraryService
from ..utils import format_size


class DuplicatesDialog(QDialog):
    def __init__(self, service: LibraryService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Duplicate files")
        self.resize(940, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        groups = find_duplicates(service.movies, service.episodes, lambda sid: service.by_id[-sid]["display_title"])
        summary = QLabel(f"{len(groups)} movie(s) or episode(s) found in more than one file. Compare them and delete "
                         "the ones you don't want from the folder, then rescan." if groups
                         else "No duplicate files found.")
        summary.setObjectName("muted")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Size", "Quality", "Folder"])
        self.tree.setRootIsDecorated(True)
        self.tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for group in groups:
            top = QTreeWidgetItem([f"{group['title']}   ({len(group['files'])} files)"])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            for f in group["files"]:
                child = QTreeWidgetItem([os.path.basename(f["path"]), format_size(f.get("size")),
                                         "  ·  ".join(badges(f.get("tech"))), os.path.dirname(f["path"])])
                child.setData(0, Qt.UserRole, f["id"])
                top.addChild(child)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.itemDoubleClicked.connect(lambda item, _col: self._show(item))
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.show_btn = QPushButton("Show in folder")
        self.show_btn.setEnabled(False)
        self.show_btn.clicked.connect(lambda: self._show(self.tree.currentItem()))
        self.tree.currentItemChanged.connect(
            lambda item, _prev: self.show_btn.setEnabled(self._file_id(item) is not None))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.show_btn)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)

    @staticmethod
    def _file_id(item) -> int | None:
        return item.data(0, Qt.UserRole) if item is not None else None

    def _show(self, item) -> None:
        file_id = self._file_id(item)
        if file_id is None:
            return
        try:
            self.service.show_in_folder(file_id)
        except OSError as exc:
            QMessageBox.warning(self, "Could not open the folder", str(exc))
