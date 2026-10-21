"""Pieces shared by the movie and series pages: text style, the user's review box, poster alignment."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from .theme import COLORS

POSTER_SIZE = (240, 360)
DETAILS_OFFSET = 150      # empty space above the details, so they leave the backdrop image visible
STAR_COLOR = "#ffd25e"
# Bigger text than the global theme (widget-level rules beat the application's, so other pages are unaffected)
DETAIL_STYLE = """
QLabel#movieTitle { font-size: 30pt; }
QLabel#rating { font-size: 15pt; }
QLabel#section { font-size: 11pt; }
QLabel#detailText, QLabel#muted { font-size: 13pt; }
QTextEdit { font-size: 13pt; }
"""


def cap_offset(label: QLabel) -> int:
    """Pixels from the top of a label to the top of its capital letters (used to align the poster with the title)."""
    label.ensurePolished()
    metrics = label.fontMetrics()
    return max(0, metrics.ascent() - metrics.capHeight())


class _Stars(QWidget):
    """Five clickable stars (1-5); clicking the current rating again clears it."""
    changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._buttons = []
        for n in range(1, 6):
            button = QPushButton("★")
            button.setObjectName("iconBtn")
            button.setFixedSize(46, 46)
            button.setFocusPolicy(Qt.NoFocus)
            button.setToolTip(f"{n} of 5 (click again to clear)")
            button.clicked.connect(lambda _checked=False, n=n: self.changed.emit(0 if n == self.value else n))
            row.addWidget(button)
            self._buttons.append(button)
        row.addStretch(1)
        self.set_value(0)

    def set_value(self, value: int) -> None:
        self.value = value
        for n, button in enumerate(self._buttons, 1):
            button.setStyleSheet(f"color: {STAR_COLOR if n <= value else COLORS['muted']};")


class ReviewBox(QWidget):
    """The user's own rating (stars) and comment. The comment is saved by the button and when the field loses focus."""
    rating_changed = Signal(int)     # 0 = no rating
    comment_saved = Signal(str)

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        head = QLabel("YOUR REVIEW")
        head.setObjectName("section")
        self.stars = _Stars()
        self.stars.changed.connect(self.rating_changed.emit)
        self.comment = QTextEdit()
        self.comment.setAcceptRichText(False)
        self.comment.setPlaceholderText(placeholder)
        self.comment.setFixedHeight(100)
        self.comment.installEventFilter(self)
        self.save_btn = QPushButton("Save comment")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save)
        self.comment.document().modificationChanged.connect(self.save_btn.setEnabled)
        for w in (head, self.stars, self.comment):
            layout.addWidget(w)
        layout.addWidget(self.save_btn, 0, Qt.AlignLeft)

    def set_values(self, rating: int, comment: str) -> None:
        self.stars.set_value(rating)
        if not self.comment.document().isModified() and self.comment.toPlainText() != comment:
            self.comment.setPlainText(comment)   # an unsaved draft is never overwritten
            self.comment.document().setModified(False)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.comment and event.type() == QEvent.FocusOut:
            self.autosave()
        return super().eventFilter(obj, event)

    def autosave(self) -> None:
        if self.comment.document().isModified():
            self._save()

    def release_focus(self) -> bool:
        """Leaves the comment field (saving it). True if the field had the focus."""
        if self.comment.hasFocus():
            self.comment.clearFocus()
            return True
        return False

    def _save(self) -> None:
        self.comment.document().setModified(False)
        self.comment_saved.emit(self.comment.toPlainText().strip())
