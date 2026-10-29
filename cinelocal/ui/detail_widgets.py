"""Pieces shared by the movie and series pages: text style, the user's review box, poster alignment."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

from ..mediainfo import channels_label, name_quality, resolution_label
from ..utils import format_size
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


def _tech_rows(tech: dict, path: str | None = None) -> list[tuple[str, str | None]]:
    """Quality, resolution, codecs, frame rate, bitrate and languages of the video file(s) ('More info' page).
    Without the real resolution, the quality is taken from the file name when it says one ('1080p')."""
    width, height = tech.get("width") or 0, tech.get("height") or 0
    audio = " ".join(p for p in (tech.get("audio"), channels_label(tech.get("channels") or 0)) if p)
    named = name_quality(path)
    return [
        ("Quality", resolution_label(width, height) or (f"{named} (from the file name)" if named else None)),
        ("Resolution", f"{width} × {height}" if width and height else None),
        ("Video codec", tech.get("video")),
        ("Audio", audio),
        ("Frame rate", f"{tech['fps']:g} fps" if tech.get("fps") else None),
        ("Bitrate", f"{tech['bitrate'] / 1000:.1f} Mbps" if tech.get("bitrate") else None),
        ("Audio languages", ", ".join(tech.get("audio_langs") or [])),
        ("Embedded subtitles", ", ".join(tech.get("sub_langs") or [])),
    ]


def show_more_info(parent: QWidget, title: str, extra: dict, file_size: int | None = None,
                   franchise: str | None = None, size_label: str = "File size",
                   other_rows: tuple[tuple[str, str], ...] = (), tech: dict | None = None,
                   path: str | None = None) -> None:
    """Show locally stored TMDB production data and file details."""
    details = [
        (size_label, format_size(file_size) if file_size else None),
        *_tech_rows(tech or {}, path),
        ("Budget", f"${int(extra['budget']):,}" if extra.get("budget") else None),
        ("Box office", f"${int(extra['revenue']):,}" if extra.get("revenue") else None),
        ("Production countries", ", ".join(extra.get("production_countries") or [])),
        ("Production companies", ", ".join(extra.get("production_companies") or [])),
        ("Original language", extra.get("original_language_name")),
        ("Other spoken languages", ", ".join(extra.get("spoken_languages") or [])),
        ("Franchise", franchise),
        ("Popularity", f"{extra['popularity']:,.2f}" if isinstance(extra.get("popularity"), (int, float)) else None),
        ("Status", extra.get("status")),
        ("In production", ("Yes" if extra["in_production"] else "No")
         if extra.get("in_production") is not None else None),
        ("IMDb ID", extra.get("imdb_id")),
        ("Homepage", extra.get("homepage")),
        ("Seasons", extra.get("number_of_seasons")),
        ("Episodes", extra.get("number_of_episodes")),
        *other_rows,
    ]
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"More info — {title}")
    dialog.setMinimumWidth(480)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    shown = False
    for label, value in details:
        if value not in (None, ""):
            value_label = QLabel(str(value))
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(f"{label}:", value_label)
            shown = True
    if not shown:
        form.addRow(QLabel("No additional information is available for this title yet."))
    layout.addLayout(form)
    close = QPushButton("Close")
    close.clicked.connect(dialog.accept)
    layout.addWidget(close, 0, Qt.AlignRight)
    dialog.exec()


class TechBadges(QWidget):
    """Row of small labels with the file's resolution and codecs ('1080p', 'H.264', 'AC3 5.1')."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(6)
        self._row.addStretch(1)
        self.hide()

    def set_badges(self, texts: list[str]) -> None:
        while self._row.count() > 1:   # everything but the final stretch
            self._row.takeAt(0).widget().deleteLater()
        for text in texts:
            label = QLabel(text)
            label.setStyleSheet(f"color: {COLORS['accent_hover']}; border: 1px solid {COLORS['accent_dark']};"
                                " border-radius: 5px; padding: 1px 7px; font-size: 10pt; font-weight: 700;")
            self._row.insertWidget(self._row.count() - 1, label)
        self.setVisible(bool(texts))


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
