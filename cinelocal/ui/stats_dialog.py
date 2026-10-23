"""Statistics of the library: totals, time watched, favorite genres and decades, ratings, people."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..service import LibraryService
from ..stats import library_stats
from ..utils import format_hours, format_size, star_text
from .theme import COLORS


def _card(value: str, caption: str) -> QFrame:
    card = QFrame()
    card.setStyleSheet(f"QFrame {{ background: {COLORS['surface2']}; border-radius: 12px; }}")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(2)
    big = QLabel(value)
    big.setStyleSheet("font-size: 18pt; font-weight: 800; background: transparent;")
    small = QLabel(caption)
    small.setStyleSheet(f"color: {COLORS['muted']}; background: transparent;")
    small.setWordWrap(True)
    layout.addWidget(big)
    layout.addWidget(small)
    return card


def _bars(title: str, rows: list[tuple[str, int, str]]) -> QWidget | None:
    """Section of horizontal bars; each row is (label, value, text at the right)."""
    if not rows:
        return None
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 8, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(6)
    head = QLabel(title.upper())
    head.setObjectName("section")
    grid.addWidget(head, 0, 0, 1, 3)
    biggest = max(value for _label, value, _text in rows) or 1
    for n, (label, value, text) in enumerate(rows, 1):
        bar = QProgressBar()
        bar.setRange(0, biggest)
        bar.setValue(value)
        bar.setTextVisible(False)
        right = QLabel(text)
        right.setObjectName("muted")
        grid.addWidget(QLabel(label), n, 0)
        grid.addWidget(bar, n, 1)
        grid.addWidget(right, n, 2)
    grid.setColumnStretch(1, 1)
    grid.setColumnMinimumWidth(0, 150)
    return box


class StatsDialog(QDialog):
    def __init__(self, service: LibraryService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistics")
        self.resize(760, 680)
        s = library_stats(service.movies, service.episodes)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 8)
        layout.setSpacing(10)

        cards = QGridLayout()
        cards.setSpacing(10)
        average = f"{s['average_stars']:.1f} ★" if s["average_stars"] else "—"
        for n, (value, caption) in enumerate((
                (f"{s['movies']:,}", f"movies · {s['watched_movies']:,} watched"),
                (f"{s['series']:,}", f"series · {s['episodes']:,} episodes, {s['watched_episodes']:,} watched"),
                (format_hours(s["minutes_watched"]), "watched (movies and episodes)"),
                (format_hours(s["minutes_to_watch"]), "left in unwatched movies"),
                (format_size(s["size"]), "of video files"),
                (average, f"your average rating · {s['rated']:,} rated"))):
            cards.addWidget(_card(value, caption), n // 3, n % 3)
        layout.addLayout(cards)

        sections = (
            ("Genres", [(g, count, f"{count}  ·  {seen} watched") for g, count, seen in s["genres"]]),
            ("Decades", [(f"{d}s", count, str(count)) for d, count in s["decades"]]),
            ("Your ratings", [(star_text(v), count, str(count)) for v, count in s["stars"]]),
            ("Most frequent directors", [(n, count, str(count)) for n, count in s["directors"]]),
            ("Most frequent actors", [(n, count, str(count)) for n, count in s["actors"]]),
        )
        for title, rows in sections:
            widget = _bars(title, rows)
            if widget is not None:
                layout.addWidget(widget)
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 24, 0)
        row.addStretch(1)
        row.addWidget(close)
        outer.addLayout(row)
