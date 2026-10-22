"""Menu to choose what to erase when restoring the app."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout)

# key (see LibraryService.restore), label, description
OPTIONS = (
    ("metadata", "Metadata and covers", "Posters, backdrops and info; downloaded again if an API key is set."),
    ("history", "Watch history", "Watched marks and “Continue watching” positions."),
    ("favorites", "Favorites and watchlist", ""),
    ("collections", "Collections", "The movies themselves stay in the library."),
    ("reviews", "My reviews", "Your stars and comments."),
    ("settings", "Settings", "Movies folder, API keys, language, players and remembered tracks."),
)


class RestoreDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore app")
        self.setModal(True)
        self.setMinimumWidth(480)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(10)
        note = QLabel("Choose what to erase. Your movie files are never touched.")
        note.setWordWrap(True)
        root.addWidget(note)

        self.everything = QCheckBox("All data (back to a first run)")
        self.everything.toggled.connect(self._on_everything)
        root.addWidget(self.everything)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)
        self._boxes: dict[str, QCheckBox] = {}
        for key, label, hint in OPTIONS:
            box = QCheckBox(label)
            box.toggled.connect(self._update_buttons)
            self._boxes[key] = box
            root.addWidget(box)
            if hint:
                text = QLabel(hint)
                text.setObjectName("muted")
                text.setWordWrap(True)
                text.setContentsMargins(26, 0, 0, 0)
                root.addWidget(text)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        self.restore_btn = QPushButton("Restore")
        self.restore_btn.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        self.restore_btn.clicked.connect(self._confirm)
        buttons.addWidget(cancel)
        buttons.addWidget(self.restore_btn)
        root.addSpacing(6)
        root.addLayout(buttons)
        self._update_buttons()

    def selected(self) -> set[str]:
        if self.everything.isChecked():
            return {"everything"}
        return {key for key, box in self._boxes.items() if box.isChecked()}

    def _on_everything(self, on: bool) -> None:
        for box in self._boxes.values():
            box.setEnabled(not on)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.restore_btn.setEnabled(bool(self.selected()))

    def _confirm(self) -> None:
        chosen = self.selected()
        what = "everything" if "everything" in chosen else ", ".join(
            label.lower() for key, label, _hint in OPTIONS if key in chosen)
        answer = QMessageBox.warning(self, "Restore app", f"Erase {what}?\nThis cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Yes:
            self.accept()
