"""Edit the metadata of a movie or series by hand (text fields and cover)."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTextEdit, QVBoxLayout)

from ..service import LibraryService


def _names(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


class EditDialog(QDialog):
    def __init__(self, service: LibraryService, movie_id: int, parent=None):
        super().__init__(parent)
        self.service, self.movie_id = service, movie_id
        m = service.by_id[movie_id]
        self._cast = {c["name"]: c for c in m["cast"]}
        self._poster = ""
        self.setWindowTitle("Edit metadata")
        self.setModal(True)
        self.resize(640, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(10)
        layout.addLayout(form)

        # key -> (label, value shown at the start); only what the user changes is saved
        self._fields = {
            "title": ("Title", m["display_title"]),
            "year": ("Year", str(m["display_year"] or "")),
            "runtime": ("Runtime (min)", str(m["runtime"] or "")),
            "genres": ("Genres", m["genres"]),
            "director": ("Created by" if movie_id < 0 else "Director", m["director"] or ""),
            "tagline": ("Tagline", m["tagline"] or ""),
            "overview": ("Overview", m["overview"] or ""),
            "cast": ("Cast", [c["name"] for c in m["cast"]]),
        }
        self._edits: dict[str, QLineEdit | QTextEdit] = {}
        for key, (label, value) in self._fields.items():
            text = ", ".join(value) if isinstance(value, list) else value
            if key == "overview":
                edit = QTextEdit()
                edit.setAcceptRichText(False)
                edit.setPlainText(text)
            else:
                edit = QLineEdit(text)
            if key in ("genres", "cast"):
                edit.setPlaceholderText("Separated by commas")
            self._edits[key] = edit
            form.addRow(label, edit)

        cover = QHBoxLayout()
        self.cover_label = QLabel("Keep the current cover")
        self.cover_label.setObjectName("muted")
        pick = QPushButton("Choose cover…")
        pick.clicked.connect(self._pick_cover)
        cover.addWidget(pick)
        cover.addWidget(self.cover_label, 1)
        form.addRow("Cover", cover)

        buttons = QHBoxLayout()
        reset = QPushButton("Reset to original…")
        reset.setEnabled(bool(m.get("custom")))
        reset.setToolTip("Discard your edits and download the metadata again")
        reset.clicked.connect(self._reset)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _read(self, key: str):
        edit = self._edits[key]
        text = (edit.toPlainText() if isinstance(edit, QTextEdit) else edit.text()).strip()
        return _names(text) if key in ("genres", "cast") else text

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a cover", "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._poster = path
            self.cover_label.setText(os.path.basename(path))

    def _save(self) -> None:
        changes = {}
        for key, (label, start) in self._fields.items():
            value = self._read(key)
            if value == (start if isinstance(start, list) else start.strip()):
                continue
            if key in ("year", "runtime"):
                if value and not value.isdigit():
                    QMessageBox.warning(self, "Edit metadata", f"“{label}” must be a number.")
                    return
                value = int(value) if value else None
            elif key == "cast":   # names that were already there keep their character
                value = [self._cast.get(n, {"name": n, "character": ""}) for n in value]
            elif key != "genres":
                value = value or None
            changes[key] = value
        if not changes and not self._poster:
            return self.reject()
        try:
            self.service.edit_metadata(self.movie_id, changes, self._poster)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Edit metadata", str(exc))
            return
        self.accept()

    def _reset(self) -> None:
        ask = QMessageBox.question(self, "Reset to original",
                                   "Discard your edits and download the metadata again?")
        if ask == QMessageBox.Yes:
            self.service.reset_edits(self.movie_id)
            self.accept()
