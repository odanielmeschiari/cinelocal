"""Poster grid: model, delegate (custom, fast painting) and view."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import (QAbstractAnimation, QAbstractListModel, QEasingCurve, QModelIndex, QPoint,
                            QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QListView, QScrollArea, QStyle,
                               QStyledItemDelegate)

from .. import images
from .icons import draw_icon
from .theme import COLORS

POSTER_W, POSTER_H = 180, 270
CELL_W, CELL_H = 204, 346
MAX_CACHED_POSTERS = 900
STACK_STEP = 10   # how far (px) each cover of a collection's pile peeks out to the right of the one in front


class MovieModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._movies: list[dict] = []
        self._row_by_id: dict[int, int] = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._movies)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        movie = self._movies[index.row()]
        if role == Qt.DisplayRole:
            return movie["display_title"]
        if role == Qt.ToolTipRole:
            year = movie["display_year"]
            return f"{movie['display_title']} ({year})" if year else movie["display_title"]
        return None

    def set_movies(self, movies: list[dict]) -> None:
        self.beginResetModel()
        self._movies = movies
        self._row_by_id = {m["id"]: i for i, m in enumerate(movies)}
        self.endResetModel()

    def refresh_movie(self, movie_id: int) -> None:
        row = self._row_by_id.get(movie_id)
        if row is not None:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)

    def movie_at(self, row: int) -> dict:
        return self._movies[row]


class MovieDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: OrderedDict = OrderedDict()
        self.progress_of = None   # function(movie) -> watched fraction (0 to 1), set by the window
        self._title_font = QFont()
        self._title_font.setBold(True)
        self._title_font.setPointSize(10)
        self._small_font = QFont()
        self._small_font.setPointSize(9)
        self._badge_font = QFont()
        self._badge_font.setBold(True)
        self._badge_font.setPointSize(9)

    def sizeHint(self, option, index):
        return QSize(CELL_W, CELL_H)

    # -- poster cache ---------------------------------------------------------
    def _poster(self, movie: dict, dpr: float):
        key = (movie["id"], movie["updated_at"], dpr)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        pixmap = None
        if movie["has_poster"]:
            loaded = QPixmap(movie.get("cover_file") or str(images.thumb_file(movie.get("poster_id", movie["id"]))))
            if not loaded.isNull():
                tw, th = int(POSTER_W * dpr), int(POSTER_H * dpr)
                scaled = loaded.scaled(tw, th, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x, y = (scaled.width() - tw) // 2, (scaled.height() - th) // 2
                pixmap = scaled.copy(x, y, tw, th)
                pixmap.setDevicePixelRatio(dpr)
        self._cache[key] = pixmap
        while len(self._cache) > MAX_CACHED_POSTERS:
            self._cache.popitem(last=False)
        return pixmap

    # -- painting ------------------------------------------------------------------
    def paint(self, painter: QPainter, option, index):
        movie = index.model().movie_at(index.row())
        widget = option.widget
        dpr = widget.devicePixelRatioF() if widget else 1.0
        hover = bool(option.state & QStyle.State_MouseOver)
        selected = bool(option.state & QStyle.State_Selected)

        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                               | QPainter.TextAntialiasing)
        left = option.rect.left() + (option.rect.width() - POSTER_W) // 2
        top = option.rect.top() + 10
        poster = QRect(left, top, POSTER_W, POSTER_H)

        pixmap = self._poster(movie, dpr)
        cover = poster   # a collection's pile fits in the poster's box: the cover in front shrinks to make room
        piled = movie.get("stack_movies") or []
        if piled:
            width = POSTER_W - STACK_STEP * len(piled)
            height = round(POSTER_H * width / POSTER_W)
            cover = QRect(poster.left(), poster.top() + POSTER_H - height, width, height)
            self._paint_stack(painter, cover, piled, dpr)
        path = QPainterPath()
        path.addRect(QRectF(cover))
        painter.setClipPath(path)
        if pixmap is None:
            self._paint_placeholder(painter, cover, movie)
        elif piled:
            painter.drawPixmap(cover, pixmap)
        else:
            painter.drawPixmap(cover.topLeft(), pixmap)
        painter.setClipping(False)

        self._paint_badges(painter, cover, movie)

        if selected or hover:
            pen = QPen(QColor(COLORS["accent"] if selected else COLORS["accent_hover"]),
                       3 if selected else 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(cover).adjusted(1, 1, -1, -1))

        self._paint_texts(painter, poster, movie, hover or selected)
        painter.restore()

    def _paint_stack(self, painter, front, piled, dpr):
        """The covers of the next movies of a collection, piled behind the one in front (up and to the right)."""
        for depth in range(len(piled), 0, -1):   # the farthest first
            rect = front.translated(STACK_STEP * depth, -round(STACK_STEP * depth * POSTER_H / POSTER_W))
            path = QPainterPath()
            path.addRect(QRectF(rect))
            painter.setClipPath(path)
            pixmap = self._poster(piled[depth - 1], dpr)
            if pixmap is not None:
                painter.drawPixmap(rect, pixmap)
            else:
                self._paint_placeholder(painter, rect, piled[depth - 1])
            painter.fillRect(rect, QColor(0, 0, 0, 45 + 45 * depth))
            painter.setClipping(False)
            painter.setPen(QPen(QColor(0, 0, 0, 200), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(rect))

    def _paint_placeholder(self, painter, rect, movie):
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(COLORS["surface3"]))
        gradient.setColorAt(1, QColor(COLORS["surface"]))
        painter.fillRect(rect, gradient)
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(self._title_font)
        painter.drawText(rect.adjusted(14, 14, -14, -14),
                         Qt.AlignCenter | Qt.TextWordWrap, movie["display_title"])

    def _pill(self, painter, rect, text, bg, fg="#ffffff"):
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(rect), rect.height() / 2, rect.height() / 2)
        painter.setPen(QColor(fg))
        painter.setFont(self._badge_font)
        painter.drawText(rect, Qt.AlignCenter, text)

    @staticmethod
    def _disc(painter, rect, icon):
        """Icon on a small dark disc (readable over any cover)."""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 185))
        painter.drawEllipse(rect)
        draw_icon(painter, icon, COLORS["accent_hover"], rect.adjusted(5, 5, -5, -5))

    def _paint_badges(self, painter, poster, movie):
        if movie.get("group") is not None:   # a collection standing in for its movies: only its own marker
            self._disc(painter, QRectF(poster.right() - 34, poster.top() + 8, 26, 26), "collections")
            return
        x = poster.left() + 8
        if movie["rating"] and movie["votes"]:
            self._pill(painter, QRect(x, poster.bottom() - 28, 42, 20),
                       f"{movie['rating']:.1f}", QColor(0, 0, 0, 185), "#ffd25e")
            x += 48
        rated = bool(movie.get("user_rating"))
        if rated:   # the user's own stars, in the bottom right corner
            self._pill(painter, QRect(poster.right() - 54, poster.bottom() - 28, 46, 20),
                       f"★ {movie['user_rating']:g}", QColor(COLORS["accent"]), COLORS["bg"])
        if movie["status"] in ("ambiguous", "not_found"):
            self._pill(painter, QRect(poster.right() - 70, poster.bottom() - (52 if rated else 28), 62, 20),
                       "Review", QColor(COLORS["warn"]), "#1b1200")
        corner = poster.right() - 34   # top right: the watchlist marker stays in the corner, the heart moves aside
        if movie["watchlist"]:
            self._disc(painter, QRectF(corner, poster.top() + 8, 26, 26), "watchlist_on")
            corner -= 30
        if movie["favorite"]:
            self._disc(painter, QRectF(corner, poster.top() + 8, 26, 26), "favorite_on")
        if movie["watched"]:
            self._disc(painter, QRectF(poster.left() + 8, poster.top() + 8, 26, 26), "watched_on")
        fraction = self.progress_of(movie) if self.progress_of else 0
        if fraction > 0:   # mini-tracker: how much of the movie has been watched
            track = QRectF(poster.left() + 8, poster.bottom() - 6, POSTER_W - 16, 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 90))
            painter.drawRoundedRect(track, 2, 2)
            painter.setBrush(QColor(COLORS["accent"]))
            painter.drawRoundedRect(QRectF(track.left(), track.top(), max(4.0, track.width() * fraction), 4), 2, 2)

    def _paint_texts(self, painter, poster, movie, highlighted):
        title_rect = QRect(poster.left(), poster.bottom() + 8, POSTER_W, 20)
        painter.setFont(self._title_font)
        painter.setPen(QColor("#ffffff" if highlighted else COLORS["text"]))
        title = QFontMetrics(self._title_font).elidedText(
            movie["display_title"], Qt.ElideRight, POSTER_W)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

        parts = []
        if movie["display_year"]:
            parts.append(str(movie["display_year"]))
        if movie["genres"]:
            parts.append(movie["genres"][0])
        if not parts and movie["status"] == "pending":
            parts.append("No metadata")
        if movie.get("kind") == "series":
            parts.insert(0, "Series")
        painter.setFont(self._small_font)
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(QRect(poster.left(), poster.bottom() + 28, POSTER_W, 18),
                         Qt.AlignLeft | Qt.AlignVCenter, "  •  ".join(parts))


class MovieGrid(QListView):
    movie_opened = Signal(int)
    context_requested = Signal(list, QPoint)   # selected ids, global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("grid")
        self._model = MovieModel(self)
        self.setModel(self._model)
        self.setItemDelegate(MovieDelegate(self))
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.Batched)
        self.setBatchSize(100)
        self.setGridSize(QSize(CELL_W, CELL_H))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(48)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.NoFrame)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)
        self.clicked.connect(self._on_clicked)

    @property
    def movie_model(self) -> MovieModel:
        return self._model

    def selected_ids(self) -> list[int]:
        rows = sorted(i.row() for i in self.selectionModel().selectedIndexes())
        return [self._model.movie_at(r)["id"] for r in rows]

    def _on_clicked(self, index):
        mods = QGuiApplication.keyboardModifiers()
        if mods & (Qt.ControlModifier | Qt.ShiftModifier):
            return  # multiple selection
        self.movie_opened.emit(self._model.movie_at(index.row())["id"])

    def _on_context(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        if not self.selectionModel().isSelected(index):
            self.setCurrentIndex(index)
        self.context_requested.emit(self.selected_ids(), self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentIndex().isValid():
            self.movie_opened.emit(self._model.movie_at(self.currentIndex().row())["id"])
            return
        super().keyPressEvent(event)


def _scroll_page(widget, event) -> None:
    """Forwards the mouse wheel to the scroll area that contains `widget`."""
    area = widget.parentWidget()
    while area is not None and not isinstance(area, QScrollArea):
        area = area.parentWidget()
    if area is None:
        event.ignore()
    else:
        QApplication.sendEvent(area.viewport(), event)


class MovieFlow(MovieGrid):
    """Grid without its own scrolling: it grows to its full height and the containing area scrolls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.movie_model.modelReset.connect(self._fit)

    def _fit(self) -> None:
        per_row = max(1, self.viewport().width() // CELL_W)
        self.setFixedHeight(-(-self.movie_model.rowCount() // per_row) * CELL_H)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def wheelEvent(self, event) -> None:
        _scroll_page(self, event)


class MovieRow(MovieGrid):
    """A single horizontal row of posters (used on the home page), scrolled with arrows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ListMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.Fixed)
        self.setLayoutMode(QListView.SinglePass)
        self.setGridSize(QSize(CELL_W, CELL_H))
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(CELL_H + 8)
        self._anim = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def scroll_page(self, direction: int) -> None:
        """Moves one 'page' of whole posters to the left (-1) or right (1)."""
        bar = self.horizontalScrollBar()
        base = self._anim.endValue() if self._anim.state() == QAbstractAnimation.Running else bar.value()
        step = max(CELL_W, (self.viewport().width() // CELL_W) * CELL_W)
        target = max(bar.minimum(), min(bar.maximum(), int(base) + direction * step))
        self._anim.stop()
        self._anim.setStartValue(bar.value())
        self._anim.setEndValue(target)
        self._anim.start()

    def wheelEvent(self, event) -> None:
        if event.angleDelta().x():   # horizontal scroll (touchpad): moves the row
            super().wheelEvent(event)
        else:                        # regular wheel: scrolls the whole page
            _scroll_page(self, event)
