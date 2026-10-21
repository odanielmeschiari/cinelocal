"""Grade de capas: modelo, delegate (pintura própria, rápida) e view."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QPoint, QRect, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from .. import images
from .theme import COLORS

POSTER_W, POSTER_H = 180, 270
CELL_W, CELL_H = 204, 346
MAX_CACHED_POSTERS = 900


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

    # -- cache de capas ---------------------------------------------------------
    def _poster(self, movie: dict, dpr: float):
        key = (movie["id"], movie["updated_at"], dpr)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        pixmap = None
        if movie["has_poster"]:
            loaded = QPixmap(str(images.thumb_file(movie["id"])))
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

    # -- pintura ------------------------------------------------------------------
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

        path = QPainterPath()
        path.addRoundedRect(QRectF(poster), 10, 10)
        painter.setClipPath(path)
        pixmap = self._poster(movie, dpr)
        if pixmap is not None:
            painter.drawPixmap(poster.topLeft(), pixmap)
        else:
            self._paint_placeholder(painter, poster, movie)
        painter.setClipping(False)

        self._paint_badges(painter, poster, movie)

        if selected or hover:
            pen = QPen(QColor(COLORS["accent"] if selected else COLORS["accent_hover"]),
                       3 if selected else 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(poster).adjusted(1, 1, -1, -1), 10, 10)

        self._paint_texts(painter, poster, movie, hover or selected)
        painter.restore()

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

    def _paint_badges(self, painter, poster, movie):
        if movie["rating"] and movie["votes"]:
            self._pill(painter, QRect(poster.left() + 8, poster.bottom() - 28, 54, 20),
                       f"★ {movie['rating']:.1f}", QColor(0, 0, 0, 185), "#ffd25e")
        if movie["status"] in ("ambiguous", "not_found"):
            self._pill(painter, QRect(poster.right() - 70, poster.bottom() - 28, 62, 20),
                       "Revisar", QColor(COLORS["warn"]), "#1b1200")
        if movie["favorite"]:
            self._pill(painter, QRect(poster.right() - 30, poster.top() + 8, 22, 22),
                       "♥", QColor(COLORS["accent"]))
        if movie["watched"]:
            self._pill(painter, QRect(poster.left() + 8, poster.top() + 8, 22, 22),
                       "✓", QColor(0, 0, 0, 185))

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
            parts.append("Sem metadados")
        if movie.get("kind") == "series":
            parts.insert(0, "Série")
        painter.setFont(self._small_font)
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(QRect(poster.left(), poster.bottom() + 28, POSTER_W, 18),
                         Qt.AlignLeft | Qt.AlignVCenter, "  •  ".join(parts))


class MovieGrid(QListView):
    movie_opened = Signal(int)
    context_requested = Signal(list, QPoint)   # ids selecionados, posição global

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
            return  # seleção múltipla
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
