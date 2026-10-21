"""Movie page with its metadata (poster, overview, rating, cast...) and actions."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QUrl, Qt, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QKeySequence, QLinearGradient, QPainter,
                           QPixmap, QShortcut)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QTextEdit, QVBoxLayout, QWidget)

from .. import images
from ..service import LibraryService
from ..utils import format_runtime, format_votes
from .dialogs import populate_collections_menu
from .match_dialog import MatchDialog
from .theme import COLORS
from .widgets import rounded_pixmap

POSTER_SIZE = (240, 360)
BACKDROP_HEIGHT = 380
DETAILS_OFFSET = 150      # empty space above the details, so they leave the backdrop image visible
STAR_COLOR = "#ffd25e"
# Bigger text than the global theme (widget-level rules beat the application's, so other pages are unaffected)
_STYLE = """
QLabel#movieTitle { font-size: 30pt; }
QLabel#rating { font-size: 15pt; }
QLabel#section { font-size: 11pt; }
QLabel#detailText, QLabel#muted { font-size: 13pt; }
QTextEdit { font-size: 13pt; }
"""


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


class MovieDialog(QWidget):
    back_requested = Signal()
    play_requested = Signal(int)

    def __init__(self, service: LibraryService, movie_id: int, parent=None):
        super().__init__(parent)
        self.service = service
        self.movie_id = movie_id
        self._backdrop: QPixmap | None = None
        self._backdrop_scaled: QPixmap | None = None
        self._heads: dict[QLabel, QLabel] = {}
        self.setStyleSheet(_STYLE)
        self.setWindowTitle(service.by_id[movie_id]["display_title"])
        self._build()
        QShortcut(QKeySequence("Esc"), self, activated=self._escape)
        QShortcut(QKeySequence.Back, self, activated=self._leave)
        self._populate()
        service.movie_changed.connect(self._on_movie_changed)

    # -- construction ------------------------------------------------------------------
    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(34, 20, 34, 30)
        page.setSpacing(14)
        self.back_btn = QPushButton("←  Back")
        self.back_btn.setToolTip("Back to the list (Esc)")
        self.back_btn.clicked.connect(self._leave)
        page.addWidget(self.back_btn, 0, Qt.AlignLeft)
        root = QHBoxLayout()
        root.setSpacing(30)
        page.addLayout(root, 1)

        self.poster = QLabel()
        self.poster.setFixedSize(*POSTER_SIZE)
        self.poster.setAlignment(Qt.AlignCenter)
        left = QVBoxLayout()
        left.addWidget(self.poster)
        left.addStretch(1)
        root.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addSpacing(DETAILS_OFFSET)
        root.addLayout(right, 1)

        self.title = QLabel()
        self.title.setObjectName("movieTitle")
        self.title.setWordWrap(True)
        self.meta = QLabel()
        self.meta.setObjectName("muted")
        self.rating = QLabel()
        self.rating.setObjectName("rating")
        self.rating.setTextFormat(Qt.RichText)
        self.tagline = QLabel()
        self.tagline.setObjectName("muted")
        self.tagline.setWordWrap(True)
        self.banner = QLabel()
        self.banner.setObjectName("warn")
        self.banner.setWordWrap(True)
        for w in (self.title, self.meta, self.rating, self.tagline, self.banner):
            right.addWidget(w)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 8, 8, 0)
        body_layout.setSpacing(6)
        self.overview = self._text_block(body_layout, "OVERVIEW")
        self.director = self._text_block(body_layout, "DIRECTOR")
        self.cast = self._text_block(body_layout, "CAST")
        review_head = QLabel("YOUR REVIEW")
        review_head.setObjectName("section")
        self.stars = _Stars()
        self.stars.changed.connect(self._set_rating)
        self.comment = QTextEdit()
        self.comment.setAcceptRichText(False)
        self.comment.setPlaceholderText("Write your own comments about this movie…")
        self.comment.setFixedHeight(100)
        self.comment.installEventFilter(self)   # the comment is also saved when the field loses focus
        self.save_comment_btn = QPushButton("Save comment")
        self.save_comment_btn.setEnabled(False)
        self.save_comment_btn.clicked.connect(self._save_comment)
        self.comment.document().modificationChanged.connect(self.save_comment_btn.setEnabled)
        for w in (review_head, self.stars, self.comment):
            body_layout.addWidget(w)
        body_layout.addWidget(self.save_comment_btn, 0, Qt.AlignLeft)
        self.file_info = self._text_block(body_layout, "FILE", muted=True)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        right.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.watch_btn = QPushButton("Watch")
        self.watch_btn.setProperty("primary", True)
        self.watch_btn.clicked.connect(self._watch)
        self.fav_btn = QPushButton("Favorite")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "favorite", on))
        self.seen_btn = QPushButton("Watched")
        self.seen_btn.setCheckable(True)
        self.seen_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watched", on))
        self.list_btn = QPushButton("Watchlist")
        self.list_btn.setCheckable(True)
        self.list_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watchlist", on))
        self.coll_btn = QPushButton("Collections")
        coll_menu = QMenu(self.coll_btn)
        coll_menu.aboutToShow.connect(lambda: self._fill_collections(coll_menu))
        self.coll_btn.setMenu(coll_menu)
        self.trailer_btn = QPushButton("Trailer")
        self.trailer_btn.clicked.connect(self._open_trailer)
        more = QPushButton("More")
        more_menu = QMenu(more)
        more_menu.addAction("Refresh metadata", self._refresh)
        more_menu.addAction("Fix match…", self._fix_match)
        more_menu.addAction("Show in folder", self._show_folder)
        more.setMenu(more_menu)
        for w in (self.watch_btn, self.fav_btn, self.seen_btn, self.list_btn, self.coll_btn, self.trailer_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(more)
        right.addLayout(actions)

    def _text_block(self, layout: QVBoxLayout, heading: str, muted: bool = False) -> QLabel:
        head = QLabel(heading)
        head.setObjectName("section")
        text = QLabel()
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text.setObjectName("muted" if muted else "detailText")
        layout.addWidget(head)
        layout.addWidget(text)
        head.hide()
        text.hide()
        self._heads[text] = head
        return text

    def _set_block(self, label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))
        self._heads[label].setVisible(bool(text))

    # -- data -------------------------------------------------------------------------
    def _populate(self) -> None:
        m = self.service.by_id.get(self.movie_id)
        if m is None:
            self.back_requested.emit()
            return
        self.setWindowTitle(m["display_title"])
        self.title.setText(m["display_title"])
        if m["original_title"] and m["original_title"] != m["display_title"]:
            self.title.setToolTip(f"Original title: {m['original_title']}")

        parts = [str(m["display_year"] or ""), format_runtime(m["runtime"]), ", ".join(m["genres"])]
        self.meta.setText("   •   ".join(p for p in parts if p))

        if m["rating"] and m["votes"]:
            self.rating.setText(f"Rating {m['rating']:.1f}/10   "
                                f"<span style='color:{COLORS['muted']};font-weight:400;font-size:12pt'>"
                                f"{format_votes(m['votes'])} votes on TMDB</span>")
        else:
            self.rating.setText("")
        self.rating.setVisible(bool(self.rating.text()))
        self.tagline.setText(f"“{m['tagline']}”" if m["tagline"] else "")
        self.tagline.setVisible(bool(m["tagline"]))

        banners = {
            "pending": "Metadata has not been downloaded for this movie yet.",
            "ambiguous": "Several movies match this file. Use More → Fix match.",
            "not_found": "This movie was not found on TMDB. Use More → Fix match.",
        }
        self.banner.setText(banners.get(m["status"], ""))
        self.banner.setVisible(bool(self.banner.text()))

        overview = m["overview"] or ("No overview available." if m["status"] == "matched" else "")
        self._set_block(self.overview, overview)
        self._set_block(self.director, m["director"] or "")
        self._set_block(self.cast, ", ".join(c["name"] for c in m["cast"][:10]))
        self._set_block(self.file_info, m["path"])

        self.stars.set_value(m.get("user_rating") or 0)
        comment = m.get("user_comment") or ""
        if not self.comment.document().isModified() and self.comment.toPlainText() != comment:
            self.comment.setPlainText(comment)   # an unsaved draft is never overwritten
            self.comment.document().setModified(False)

        self._load_poster(m)
        self._load_backdrop(m)

        for button, value, on_text, off_text in (
                (self.fav_btn, m["favorite"], "Favorited", "Favorite"),
                (self.seen_btn, m["watched"], "Watched", "Mark as watched"),
                (self.list_btn, m["watchlist"], "On Watchlist", "Watchlist")):
            button.blockSignals(True)
            button.setChecked(value)
            button.setText(on_text if value else off_text)
            button.blockSignals(False)
        self.trailer_btn.setVisible(bool(m["trailer_key"]))

    def _load_poster(self, m: dict) -> None:
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(str(images.poster_file(m["id"]))) if m["has_poster"] else QPixmap()
        if pixmap.isNull():
            self.poster.setPixmap(QPixmap())
            self.poster.setStyleSheet(
                f"background:{COLORS['surface2']}; border-radius:12px; color:{COLORS['muted']};")
            self.poster.setText("No poster")
            return
        self.poster.setStyleSheet("")
        scaled = pixmap.scaled(int(POSTER_SIZE[0] * dpr), int(POSTER_SIZE[1] * dpr),
                               Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x, y = (scaled.width() - int(POSTER_SIZE[0] * dpr)) // 2, (scaled.height() - int(POSTER_SIZE[1] * dpr)) // 2
        cropped = scaled.copy(x, y, int(POSTER_SIZE[0] * dpr), int(POSTER_SIZE[1] * dpr))
        cropped.setDevicePixelRatio(dpr)
        self.poster.setPixmap(rounded_pixmap(cropped, 12))

    def _load_backdrop(self, m: dict) -> None:
        pixmap = QPixmap(str(images.backdrop_file(m["id"]))) if m["has_backdrop"] else QPixmap()
        self._backdrop = None if pixmap.isNull() else pixmap
        self._backdrop_scaled = None
        self.update()

    def _on_movie_changed(self, movie_id: int) -> None:
        if movie_id == self.movie_id:
            self._populate()

    # -- backdrop background ----------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        bg = QColor(COLORS["bg"])
        painter.fillRect(self.rect(), bg)
        if self._backdrop is not None:
            if self._backdrop_scaled is None or self._backdrop_scaled.width() != self.width():
                self._backdrop_scaled = self._backdrop.scaledToWidth(self.width(), Qt.SmoothTransformation)
            painter.drawPixmap(0, 0, self._backdrop_scaled, 0, 0, self.width(), BACKDROP_HEIGHT)
            gradient = QLinearGradient(0, 0, 0, BACKDROP_HEIGHT)
            top, bottom = QColor(bg), QColor(bg)
            top.setAlpha(150)
            gradient.setColorAt(0, top)
            gradient.setColorAt(1, bottom)
            painter.fillRect(0, 0, self.width(), BACKDROP_HEIGHT, gradient)
        painter.end()

    def resizeEvent(self, event) -> None:
        self._backdrop_scaled = None
        super().resizeEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.comment and event.type() == QEvent.FocusOut:
            self._autosave()
        return super().eventFilter(obj, event)

    def _autosave(self) -> None:
        if self.comment.document().isModified():
            self._save_comment()

    def _leave(self) -> None:
        self._autosave()
        self.back_requested.emit()

    def _escape(self) -> None:
        if self.comment.hasFocus():   # Esc while typing a comment only leaves the field
            self.comment.clearFocus()
        else:
            self._leave()

    # -- actions ---------------------------------------------------------------------------------
    def _set_rating(self, value: int) -> None:
        m = self.service.by_id[self.movie_id]
        self.service.set_review(self.movie_id, value, m.get("user_comment") or "")

    def _save_comment(self) -> None:
        m = self.service.by_id[self.movie_id]
        self.comment.document().setModified(False)
        self.service.set_review(self.movie_id, m.get("user_rating") or 0,
                                self.comment.toPlainText().strip())

    def _watch(self) -> None:
        self.play_requested.emit(self.movie_id)

    def _fill_collections(self, menu: QMenu) -> None:
        menu.clear()
        populate_collections_menu(menu, self.service, [self.movie_id], self)

    def _open_trailer(self) -> None:
        key = self.service.by_id[self.movie_id]["trailer_key"]
        if key:
            QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={key}"))

    def _refresh(self) -> None:
        self.service.apply_match(self.movie_id)

    def _fix_match(self) -> None:
        dialog = MatchDialog(self.service, self.service.by_id[self.movie_id], self)
        dialog.exec()
        if dialog.selected_tmdb_id:
            self.service.apply_match(self.movie_id, dialog.selected_tmdb_id)

    def _show_folder(self) -> None:
        try:
            self.service.show_in_folder(self.movie_id)
        except OSError as exc:
            QMessageBox.warning(self, "Could not open the folder", str(exc))
