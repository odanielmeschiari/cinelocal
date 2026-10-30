"""Poster grid: model, delegate (custom, fast painting) and view."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import (QAbstractAnimation, QAbstractListModel, QEasingCurve, QEvent, QMimeData, QModelIndex,
                            QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QDrag, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QListView, QScrollArea, QStyle,
                               QStyledItemDelegate)

from .. import images
from .icons import draw_icon
from .theme import COLORS

POSTER_W, POSTER_H = 180, 270   # poster size at 100% zoom
CELL_PAD_W, CELL_PAD_H = 18, 76   # what a cell adds around its poster: the space between posters; room for the title and subtitle
SIZE_TARGETS = (108, 126, 144, 162, 180, 198, 216, 252, 288)   # poster widths the sizes 1, 2, 3... aim for
DEFAULT_TARGET = 180   # the size used until the user picks one
MIN_POSTER_W, MAX_POSTER_W = 96, 320   # no size may make the posters smaller or larger than this
GROW_SCALE = 0.05   # the poster under the mouse grows by this much (5%)
MAX_CACHED_POSTERS = 900
MOVE_MIME = "application/x-cinelocal-movie"   # what is dragged: the ids (comma-separated) of the movies


def dragged_ids(mime) -> list[int]:
    """The ids of the movies carried by a drag started in a grid."""
    if not mime.hasFormat(MOVE_MIME):
        return []
    return [int(i) for i in bytes(mime.data(MOVE_MIME)).decode().split(",") if i]


MATCH_ROLE = Qt.UserRole + 1   # model role: how much (%) the title matches the user's taste, if it is being shown
PEEK_GAP = 10   # space (px) between the posters of a row that shows half a poster at its end (see MovieRow)
STACK_STEP = 10   # how far (px) each cover of a collection's pile peeks out to the right of the one in front (at 100%)

_size = 0   # the size picked by the user (1 = smallest); 0: not picked yet. Shared by every grid and row


def set_zoom(size: int) -> None:
    global _size
    _size = size


def poster_size() -> tuple[int, int]:
    """The poster width the current size aims for (a grid adjusts it a little so that its columns fill the width)."""
    width = SIZE_TARGETS[min(_size, len(SIZE_TARGETS)) - 1] if _size > 0 else DEFAULT_TARGET
    return width, round(width * POSTER_H / POSTER_W)


def cell_size() -> tuple[int, int]:
    width, height = poster_size()
    return width + CELL_PAD_W, height + CELL_PAD_H


def size_columns(area: int) -> list[int]:
    """How many columns each size has in a width of `area` px, from size 1 (the most columns, smallest posters) up.
    Every size has a different number of columns, so each one looks different, and the space between the posters
    is always the same. Sizes that would make the posters too small or too large for this width are left out."""
    options: list[int] = []
    for target in SIZE_TARGETS:
        columns = max(1, round(area / (target + CELL_PAD_W)))
        if columns not in options and MIN_POSTER_W <= area // columns - CELL_PAD_W <= MAX_POSTER_W:
            options.append(columns)
    return options or [max(1, round(area / (DEFAULT_TARGET + CELL_PAD_W)))]


def size_level(area: int) -> int:
    """The size (1 = smallest) in use in a width of `area` px."""
    options = size_columns(area)
    if _size > 0:
        return min(_size, len(options))
    wanted = max(1, round(area / (DEFAULT_TARGET + CELL_PAD_W)))
    return min(range(len(options)), key=lambda i: abs(options[i] - wanted)) + 1


def fit_cell(area: int) -> tuple[int, int]:
    """Cell size for the current size: the columns share the width of `area` px."""
    if area <= 0:
        return cell_size()
    width = area // size_columns(area)[size_level(area) - 1]
    return width, round((width - CELL_PAD_W) * POSTER_H / POSTER_W) + CELL_PAD_H


class MovieModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._movies: list[dict] = []
        self._row_by_id: dict[int, int] = {}
        self._match: dict[int, float] = {}

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
        if role == MATCH_ROLE and movie["id"] in self._match:
            return round(self._match[movie["id"]] * 100)
        return None

    def set_movies(self, movies: list[dict], match: dict[int, float] | None = None) -> None:
        """`match` (id -> 0..1) makes the posters show a "% match" badge."""
        self.beginResetModel()
        self._movies = movies
        self._match = match or {}
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
        self.hidden: set[str] = set()   # badges the user chose not to see (see BADGES in settings_dialog)
        self._dims: tuple[int, int] | None = None   # poster size in the view being painted (None: the zoom's)
        self._title_font = QFont()
        self._title_font.setBold(True)
        self._title_font.setPointSize(10)
        self._small_font = QFont()
        self._small_font.setPointSize(9)
        self._badge_font = QFont()
        self._badge_font.setBold(True)
        self._badge_font.setPointSize(9)

    def sizeHint(self, option, index):
        cell = option.widget.gridSize() if option.widget else QSize()   # the width the view stretched the cells to
        return cell if cell.isValid() else QSize(*cell_size())

    # -- poster cache ---------------------------------------------------------
    def _poster(self, movie: dict, dpr: float):
        pw, ph = self._dims or poster_size()
        key = (movie["id"], movie["updated_at"], dpr, pw)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        pixmap = None
        if movie["has_poster"]:
            loaded = QPixmap(movie.get("cover_file") or str(images.thumb_file(movie.get("poster_id", movie["id"]))))
            if not loaded.isNull():
                tw, th = int(pw * dpr), int(ph * dpr)
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
        grow = widget.grow_of(index.row()) if hasattr(widget, "grow_of") else 0.0
        pw, ph = self._dims = widget.poster_dims() if hasattr(widget, "poster_dims") else poster_size()

        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                               | QPainter.TextAntialiasing)
        if grow:   # under the mouse: the whole card (poster and texts) swells a little around its center
            center = QRectF(option.rect).center()
            painter.translate(center)
            painter.scale(1 + GROW_SCALE * grow, 1 + GROW_SCALE * grow)
            painter.translate(-center)
        left = option.rect.left() + (option.rect.width() - pw) // 2
        top = option.rect.top() + 10
        poster = QRect(left, top, pw, ph)

        pixmap = self._poster(movie, dpr)
        cover = poster   # a collection's pile fits in the poster's box: the cover in front shrinks to make room
        piled = movie.get("stack_movies") or []
        if piled:
            step = round(STACK_STEP * pw / POSTER_W)
            width = pw - step * len(piled)
            height = round(ph * width / pw)
            cover = QRect(poster.left(), poster.top() + ph - height, width, height)
            self._paint_stack(painter, cover, piled, dpr, step)
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
        match = index.data(MATCH_ROLE)
        if match is not None and "match" not in self.hidden:   # top left, under the "watched" mark
            shown = movie["watched"] and "watched" not in self.hidden
            self._pill(painter, QRect(cover.left() + 8, cover.top() + (40 if shown else 8), 46, 20),
                       f"{match}%", QColor(0, 0, 0, 185), COLORS["accent"])

        self._paint_texts(painter, poster, movie, hover or selected)
        painter.restore()

    def _paint_stack(self, painter, front, piled, dpr, step):
        """The covers of the next movies of a collection, piled behind the one in front (up and to the right)."""
        for depth in range(len(piled), 0, -1):   # the farthest first
            rect = front.translated(step * depth, -round(step * depth * POSTER_H / POSTER_W))
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
        hidden = self.hidden
        x = poster.left() + 8
        if movie["rating"] and movie["votes"] and "rating" not in hidden:
            self._pill(painter, QRect(x, poster.bottom() - 28, 42, 20),
                       f"{movie['rating']:.1f}", QColor(0, 0, 0, 185), "#ffd25e")
            x += 48
        rated = bool(movie.get("user_rating")) and "user_rating" not in hidden
        if rated:   # the user's own stars, in the bottom right corner
            self._pill(painter, QRect(poster.right() - 54, poster.bottom() - 28, 46, 20),
                       f"★ {movie['user_rating']:g}", QColor(COLORS["accent"]), COLORS["bg"])
        if movie["status"] in ("ambiguous", "not_found") and "review" not in hidden:
            self._pill(painter, QRect(poster.right() - 70, poster.bottom() - (52 if rated else 28), 62, 20),
                       "Review", QColor(COLORS["warn"]), "#1b1200")
        corner = poster.right() - 34   # top right: the watchlist marker stays in the corner, the heart moves aside
        if movie["watchlist"] and "watchlist" not in hidden:
            self._disc(painter, QRectF(corner, poster.top() + 8, 26, 26), "watchlist_on")
            corner -= 30
        if movie["favorite"] and "favorite" not in hidden:
            self._disc(painter, QRectF(corner, poster.top() + 8, 26, 26), "favorite_on")
        if movie["watched"] and "watched" not in hidden:
            self._disc(painter, QRectF(poster.left() + 8, poster.top() + 8, 26, 26), "watched_on")
        fraction = self.progress_of(movie) if self.progress_of and "progress" not in hidden else 0
        if fraction > 0:   # mini-tracker: how much of the movie has been watched
            track = QRectF(poster.left() + 8, poster.bottom() - 6, poster.width() - 16, 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 90))
            painter.drawRoundedRect(track, 2, 2)
            painter.setBrush(QColor(COLORS["accent"]))
            painter.drawRoundedRect(QRectF(track.left(), track.top(), max(4.0, track.width() * fraction), 4), 2, 2)

    def _paint_texts(self, painter, poster, movie, highlighted):
        title_rect = QRect(poster.left(), poster.bottom() + 8, poster.width(), 20)
        painter.setFont(self._title_font)
        painter.setPen(QColor("#ffffff" if highlighted else COLORS["text"]))
        title = QFontMetrics(self._title_font).elidedText(
            movie["display_title"], Qt.ElideRight, poster.width())
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
        painter.drawText(QRect(poster.left(), poster.bottom() + 28, poster.width(), 18),
                         Qt.AlignLeft | Qt.AlignVCenter, "  •  ".join(parts))


class MovieGrid(QListView):
    movie_opened = Signal(int)
    metrics_changed = Signal()   # the size of the cells changed (zoom, or the window was resized)
    context_requested = Signal(list, QPoint)   # selected ids, global position
    reorder_requested = Signal(int, int)   # a movie was dropped on another one: ids of both

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
        self.setGridSize(QSize(*cell_size()))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)   # a poster can be dropped on a list of the sidebar
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(48)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.NoFrame)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)
        self.clicked.connect(self._on_clicked)
        self._grown_row = -1     # the poster under the mouse, which is enlarged (until the mouse leaves it)
        self._grow_value = 0.0   # 0 (normal size) to 1 (fully enlarged)
        self._grow_anim = QVariantAnimation(self)
        self._grow_anim.setDuration(130)
        self._grow_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._grow_anim.valueChanged.connect(self._on_grow)
        self._model.modelReset.connect(self._reset_grown)

    @property
    def movie_model(self) -> MovieModel:
        return self._model

    # -- size of the cells: the zoom, and the leftover width shared among the columns -------------------
    def apply_metrics(self) -> None:
        """Cell size for the current size: the columns fill the width, so every row (and every home row above)
        ends exactly at the right edge of the window, with always the same space between the posters."""
        width, height = self._cell_for(self.viewport().width())
        if self.gridSize() != QSize(width, height):
            self.setGridSize(QSize(width, height))
        self.viewport().update()
        self.metrics_changed.emit()

    def _cell_for(self, available: int) -> tuple[int, int]:
        return fit_cell(available)

    def poster_dims(self) -> tuple[int, int]:
        width = self.gridSize().width() - CELL_PAD_W
        return width, round(width * POSTER_H / POSTER_W)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_metrics()

    # -- the poster under the mouse grows a little, and goes back to normal when the mouse leaves it ---------------
    def grow_of(self, row: int) -> float:
        return self._grow_value if row == self._grown_row else 0.0

    def _dirty(self, row: int) -> None:
        if 0 <= row < self._model.rowCount():
            self.viewport().update(self.visualRect(self._model.index(row)).adjusted(-20, -20, 20, 20))

    def _set_grown(self, row: int) -> None:
        """`row` is the poster to enlarge (-1: none, the enlarged one returns to normal)."""
        if row >= 0:
            if row != self._grown_row:
                self._dirty(self._grown_row)
                self._grown_row, self._grow_value = row, 0.0
            elif self._grow_anim.endValue() == 1.0:
                return
            target = 1.0
        elif self._grown_row >= 0 and self._grow_value > 0:
            target = 0.0
        else:
            return
        self._grow_anim.stop()
        self._grow_anim.setStartValue(self._grow_value)
        self._grow_anim.setEndValue(target)
        self._grow_anim.start()

    def _on_grow(self, value) -> None:
        self._grow_value = float(value)
        self._dirty(self._grown_row)
        if self._grow_value <= 0 and self._grow_anim.endValue() == 0.0:
            self._grown_row = -1

    def _reset_grown(self) -> None:
        self._grow_anim.stop()
        self._grown_row, self._grow_value = -1, 0.0

    def mousePressEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and index.isValid():
            self._set_grown(index.row())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._set_grown(self.indexAt(event.position().toPoint()).row())   # -1 over an empty spot
        super().mouseMoveEvent(event)

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Leave:
            self._set_grown(-1)
        return super().viewportEvent(event)

    def hideEvent(self, event) -> None:   # e.g. the movie page covers the list: it is back to normal when you return
        self._dirty(self._grown_row)
        self._reset_grown()
        super().hideEvent(event)

    # -- dragging: to a list of the sidebar, or (in a list in manual order) to another place of the list ------
    def set_reorderable(self, on: bool) -> None:
        self.setAcceptDrops(on)

    def startDrag(self, actions) -> None:
        index = self.currentIndex()
        if not index.isValid() or self._model.movie_at(index.row())["id"] <= 0:   # series and piles are not dragged
            return
        mime = QMimeData()
        mime.setData(MOVE_MIME, str(self._model.movie_at(index.row())["id"]).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.viewport().grab(self.visualRect(index)).scaledToWidth(96, Qt.SmoothTransformation))
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MOVE_MIME):
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event) -> None:
        target = self.indexAt(event.position().toPoint())
        ids = dragged_ids(event.mimeData())
        if not ids or not target.isValid():
            event.ignore()
            return
        event.acceptProposedAction()
        self.reorder_requested.emit(ids[0], self._model.movie_at(target.row())["id"])

    def selected_ids(self) -> list[int]:
        rows = sorted(i.row() for i in self.selectionModel().selectedIndexes())
        return [self._model.movie_at(r)["id"] for r in rows]

    def _on_clicked(self, index):
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
        cell = self.gridSize()
        per_row = max(1, self.viewport().width() // cell.width())
        self.setFixedHeight(-(-self.movie_model.rowCount() // per_row) * cell.height())

    def apply_metrics(self) -> None:
        super().apply_metrics()
        self._fit()

    def wheelEvent(self, event) -> None:
        _scroll_page(self, event)


class MovieRow(MovieGrid):
    """A single horizontal row of posters (used on the home page), scrolled with arrows.
    With `peek` (the "similar" row of a description) the posters sit close together and the row always ends with
    half a poster, which tells there is more; to get that at any width, the posters are a little larger or smaller
    than the zoom's size."""

    def __init__(self, parent=None, peek: bool = False):
        super().__init__(parent)
        self._peek = peek
        self.setViewMode(QListView.ListMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.Fixed)
        self.setLayoutMode(QListView.SinglePass)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(cell_size()[1] + 8)
        if peek:
            self.setGridSize(QSize(*self._cell_for(0)))
        self._anim = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def scroll_page(self, direction: int) -> None:
        """Moves one 'page' of whole posters to the left (-1) or right (1)."""
        bar = self.horizontalScrollBar()
        base = self._anim.endValue() if self._anim.state() == QAbstractAnimation.Running else bar.value()
        cell = self.gridSize().width()
        step = max(cell, (self.viewport().width() // cell) * cell)
        target = max(bar.minimum(), min(bar.maximum(), int(base) + direction * step))
        self._anim.stop()
        self._anim.setStartValue(bar.value())
        self._anim.setEndValue(target)
        self._anim.start()

    def _cell_for(self, available: int) -> tuple[int, int]:
        if not self._peek or available <= 0:
            return super()._cell_for(available)
        natural = poster_size()[0] + PEEK_GAP
        whole = max(1, round(available / natural - 0.5))   # whole posters in view, besides the half one
        width = round(available / (whole + 0.5))
        return width, round((width - PEEK_GAP) * POSTER_H / POSTER_W) + CELL_PAD_H

    def poster_dims(self) -> tuple[int, int]:
        width = self.gridSize().width() - (PEEK_GAP if self._peek else CELL_PAD_W)
        return width, round(width * POSTER_H / POSTER_W)

    def apply_metrics(self) -> None:
        super().apply_metrics()
        self.setFixedHeight(self.gridSize().height() + 8)

    def wheelEvent(self, event) -> None:
        if event.angleDelta().x():   # horizontal scroll (touchpad): moves the row
            super().wheelEvent(event)
        else:                        # regular wheel: scrolls the whole page
            _scroll_page(self, event)
