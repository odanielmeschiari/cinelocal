"""Edit a tag's name, color, and movie membership."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from ..service import LibraryService
from ..utils import normalize_text


class TagDialog(QDialog):
    def __init__(self, service: LibraryService, tag_id: int, parent=None):
        super().__init__(parent)
        self.service, self.tag_id = service, tag_id
        self.tag = next(tag for tag in service.tags if tag["id"] == tag_id)
        self.color = self.tag["color"]
        self.setWindowTitle("Edit tag")
        self.setMinimumSize(520, 560)

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.tag["name"])
        form.addRow("Name:", self.name)
        color_row = QHBoxLayout()
        self.color_button = QPushButton("Choose color…")
        self.color_button.clicked.connect(self._choose_color)
        self.color_preview = QLabel(self.color)
        self.color_preview.setStyleSheet(f"color: {self.color}; font-weight: 700;")
        color_row.addWidget(self.color_button)
        color_row.addWidget(self.color_preview, 1)
        form.addRow("Color:", color_row)
        root.addLayout(form)

        root.addWidget(QLabel("Select the movies that belong to this tag:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter movies…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)
        self.movies = QListWidget()
        members = {movie_id for movie_id, tag_ids in service.tag_membership.items() if tag_id in tag_ids}
        for movie in sorted((m for m in service.movies if m["id"] > 0),
                            key=lambda m: (normalize_text(m["display_title"]), m["id"])):
            title = movie["display_title"]
            if movie.get("display_year"):
                title += f" ({movie['display_year']})"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, movie["id"])
            item.setData(Qt.UserRole + 1, normalize_text(title))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if movie["id"] in members else Qt.Unchecked)
            self.movies.addItem(item)
        root.addWidget(self.movies, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color), self, "Choose tag color")
        if color.isValid():
            self.color = color.name()
            self.color_preview.setText(self.color)
            self.color_preview.setStyleSheet(f"color: {self.color}; font-weight: 700;")

    def _filter(self, text: str) -> None:
        terms = normalize_text(text).split()
        for index in range(self.movies.count()):
            item = self.movies.item(index)
            item.setHidden(not all(term in item.data(Qt.UserRole + 1) for term in terms))

    def _save(self) -> None:
        try:
            self.service.rename_tag(self.tag_id, self.name.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Could not rename tag", str(exc))
            return

        if self.color != self.tag["color"]:
            self.service.set_tag_color(self.tag_id, self.color)
        selected = {
            self.movies.item(index).data(Qt.UserRole)
            for index in range(self.movies.count())
            if self.movies.item(index).checkState() == Qt.Checked
        }
        current = {movie_id for movie_id, tag_ids in self.service.tag_membership.items()
                   if self.tag_id in tag_ids}
        self.service.set_movie_tags(sorted(selected - current), self.tag_id, True)
        self.service.set_movie_tags(sorted(current - selected), self.tag_id, False)
        self.accept()
