"""Pieces shared by the movie and series pages: text style, the user's review box, poster alignment."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
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


def _tag_path() -> QPainterPath:
    path = QPainterPath()
    points = [(2, 2), (12, 2), (20.6, 10.6), (20.6, 13.4), (13.4, 20.6), (10.6, 20.6), (2, 12)]
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    path.closeSubpath()
    path.addEllipse(QPointF(7.2, 7.2), 2, 2)   # the hole of the tag
    path.setFillRule(Qt.OddEvenFill)
    path.translate(0.7, 0.7)
    return path


def _book_path() -> QPainterPath:
    path = QPainterPath()
    for mirrored in (False, True):   # open book: the left page and its mirror image
        def x(v: float) -> float:
            return 24 - v if mirrored else v
        path.moveTo(x(2), 3)
        path.lineTo(x(8), 3)
        path.cubicTo(x(10.2), 3, x(12), 4.8, x(12), 7)
        path.lineTo(x(12), 21)
        path.cubicTo(x(12), 19.3, x(10.7), 18, x(9), 18)
        path.lineTo(x(2), 18)
        path.closeSubpath()
    return path


def _clapper_path() -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(3, 10, 18, 11), 2, 2)                      # board
    path.addPolygon(QPolygonF([QPointF(*p) for p in ((3, 10), (3, 7), (21, 3.5), (21, 10), (3, 10))]))   # stick
    for x in (7.5, 12.5, 17.5):                                            # diagonal stripes of the stick
        x2 = x + 3
        path.moveTo(x, 10)
        path.lineTo(x2, 7 - (x2 - 3) * 3.5 / 18)                           # up to the slanted top edge
    return path


_GLYPHS = {"tag": _tag_path, "book": _book_path, "clapper": _clapper_path}


class GlyphButton(QPushButton):
    """Icon button with the look of the heart / check ones (objectName "bigIcon"), but whose symbol is drawn as a
    vector shape, so it does not depend on the fonts installed. Checked buttons get a filled symbol."""
    SIZE = 26   # side (px) of the drawing

    def __init__(self, shape: str, parent=None):
        super().__init__(parent)
        self.setObjectName("bigIcon")
        self.setFixedSize(ACTION_BOX, ACTION_BOX)
        self._path = _GLYPHS[shape]()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.isDown():
            name = "accent"
        elif self.isChecked() or self.underMouse():
            name = "accent_hover"
        else:
            name = "text"
        color = QColor(COLORS[name])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate((self.width() - self.SIZE) / 2, (self.height() - self.SIZE) / 2)
        painter.scale(self.SIZE / 24, self.SIZE / 24)
        painter.setPen(QPen(color, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(color if self.isChecked() else Qt.NoBrush)
        painter.drawPath(self._path)
        painter.end()


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
