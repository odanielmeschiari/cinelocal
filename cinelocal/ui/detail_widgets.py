"""Pieces shared by the movie and series pages: text style, the user's review box, poster alignment."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from .theme import COLORS

POSTER_SIZE = (240, 360)
DETAILS_OFFSET = 150      # empty space above the details, so they leave the backdrop image visible
STAR_COLOR = "#ffd25e"
ACTION_BOX = 44           # side (px) of the square action buttons (play, favorite, watched, watchlist...)
SECTION_GAP = 14          # extra space (px) above each section heading (OVERVIEW, CAST...)
CONTENT_MAX = 1040        # widest the details get; in wider windows the side margins grow (content stays centered)
# Bigger text than the global theme (widget-level rules beat the application's, so other pages are unaffected)
DETAIL_STYLE = """
QLabel#movieTitle { font-size: 30pt; }
QLabel#rating { font-size: 15pt; }
QLabel#section { font-size: 11pt; }
QLabel#detailText, QLabel#muted { font-size: 13pt; }
QTextEdit { font-size: 13pt; }
"""


def side_margin(window_width: int) -> int:
    """Extra left/right margin that keeps the details at most CONTENT_MAX wide, centered (page margins are 34)."""
    return max(0, (window_width - 2 * 34 - CONTENT_MAX) // 2)


def backdrop_gradient(height: int, bg: QColor) -> QLinearGradient:
    """Dark layer over the backdrop image: light at the top, so the image shows, and solid at the bottom, so the text
    below it stays readable."""
    gradient = QLinearGradient(0, 0, 0, height)
    for position, alpha in ((0.0, 95), (0.55, 160), (1.0, 255)):
        color = QColor(bg)
        color.setAlpha(alpha)
        gradient.setColorAt(position, color)
    return gradient


def cap_offset(label: QLabel) -> int:
    """Pixels from the top of a label to the top of its capital letters (used to align the poster with the title)."""
    label.ensurePolished()
    metrics = label.fontMetrics()
    return max(0, metrics.ascent() - metrics.capHeight())


class _StarButton(QPushButton):
    """A star that can be full, half (left half filled) or empty. Which half was clicked is kept in `left_half`."""

    def __init__(self, parent=None):
        super().__init__("★", parent)
        self.fill = 0.0          # 0, 0.5 or 1
        self.left_half = False

    def mousePressEvent(self, event) -> None:
        self.left_half = event.position().x() < self.width() / 2
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)   # background and the star in the "empty" color
        if self.fill == 0.5:        # the left half again, in the star color
            painter = QPainter(self)
            painter.setClipRect(0, 0, self.width() // 2, self.height())
            painter.setFont(self.font())
            painter.setPen(QColor(STAR_COLOR))
            painter.drawText(self.rect(), Qt.AlignCenter, "★")
            painter.end()


class _Stars(QWidget):
    """Five clickable stars; the left half of a star gives a half rating (3.5...), the right half a whole one.
    Clicking the current rating again clears it."""
    changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._buttons = []
        for n in range(1, 6):
            button = _StarButton()
            button.setObjectName("iconBtn")
            button.setFixedSize(46, 46)
            button.setFocusPolicy(Qt.NoFocus)
            button.setToolTip(f"{n} of 5 (left half = half a star; click again to clear)")
            button.clicked.connect(lambda _checked=False, n=n, b=button: self._pick(n - 0.5 if b.left_half else n))
            row.addWidget(button)
            self._buttons.append(button)
        row.addStretch(1)
        self.set_value(0)

    def _pick(self, value: float) -> None:
        self.changed.emit(0 if value == self.value else value)

    def set_value(self, value: float) -> None:
        self.value = value
        for n, button in enumerate(self._buttons, 1):
            button.fill = 1 if n <= value else 0.5 if n - 0.5 == value else 0
            button.setStyleSheet(f"color: {STAR_COLOR if button.fill == 1 else COLORS['muted']};")
            button.update()


class ReviewBox(QWidget):
    """The user's own rating (stars) and comment. The comment is saved by the button and when the field loses focus."""
    rating_changed = Signal(float)   # 0 = no rating; half stars allowed (3.5)
    comment_saved = Signal(str)

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        head = QLabel("YOUR REVIEW")
        head.setObjectName("section")
        head.setContentsMargins(0, SECTION_GAP, 0, 0)
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
