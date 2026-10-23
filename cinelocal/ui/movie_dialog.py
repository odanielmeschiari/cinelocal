"""Movie page with its metadata (poster, overview, rating, cast...) and actions."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QColorDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import images
from ..mediainfo import badges
from ..service import LibraryService
from ..similar import similar_movies
from ..utils import format_runtime, format_size, format_votes
from .dialogs import populate_collections_menu
from .detail_widgets import (ACTION_BOX, DETAIL_STYLE, DETAILS_OFFSET, POSTER_SIZE, SECTION_GAP,
                             ReviewBox, TechBadges, backdrop_gradient, cap_offset, show_more_info,
                             side_margin)
from .edit_dialog import EditDialog
from .home import HomeSection
from .icons import IconButton
from .match_dialog import MatchDialog
from .theme import COLORS
from .widgets import rounded_pixmap

BACKDROP_HEIGHT = 380


class MovieDialog(QWidget):
    back_requested = Signal()
    play_requested = Signal(int)
    open_requested = Signal(int)   # another movie, chosen among the similar ones
    filter_tag_requested = Signal(int)

    def __init__(self, service: LibraryService, movie_id: int, parent=None):
        super().__init__(parent)
        self.service = service
        self.movie_id = movie_id
        self._backdrop: QPixmap | None = None
        self._backdrop_scaled: QPixmap | None = None
        self._heads: dict[QLabel, QLabel] = {}
        self.setStyleSheet(DETAIL_STYLE)
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
        self.back_btn = IconButton("back", object_name="plainIcon")
        self.back_btn.setToolTip("Back to the list (Esc)")
        self.back_btn.clicked.connect(self._leave)
        page.addWidget(self.back_btn, 0, Qt.AlignLeft)
        root = self._content = QHBoxLayout()
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
        self.tech = TechBadges()
        for w in (self.title, self.meta, self.tech, self.rating, self.tagline, self.banner):
            right.addWidget(w)
        left.insertSpacing(0, DETAILS_OFFSET + cap_offset(self.title))   # the poster's top lines up with the title's letters

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 8, 8, 0)
        body_layout.setSpacing(8)
        self.overview = self._text_block(body_layout, "OVERVIEW")
        self.tag_head = QLabel("TAGS")
        self.tag_head.setObjectName("section")
        self.tag_head.setContentsMargins(0, SECTION_GAP, 0, 0)
        body_layout.addWidget(self.tag_head)
        self.tags_box = QWidget()
        self.tags_row = QHBoxLayout(self.tags_box)
        self.tags_row.setContentsMargins(0, 0, 0, 0)
        self.tags_row.setSpacing(6)
        self.tag_add_btn = QPushButton("+ Tag")
        self.tag_add_btn.clicked.connect(self._show_tags_menu)
        self.tags_row.addWidget(self.tag_add_btn)
        self.tags_row.addStretch(1)
        body_layout.addWidget(self.tags_box)
        self.director = self._text_block(body_layout, "DIRECTOR")
        self.cast = self._text_block(body_layout, "CAST")
        self.similar = HomeSection("Similar in your library")
        self.similar.setContentsMargins(0, SECTION_GAP, 0, 0)
        self.similar.row.itemDelegate().progress_of = self.service.progress_of
        self.similar.row.movie_opened.connect(self.open_requested)
        body_layout.addWidget(self.similar)
        self.review = ReviewBox("Write your own comments about this movie…")
        self.review.rating_changed.connect(self._set_rating)
        self.review.comment_saved.connect(self._save_comment)
        body_layout.addWidget(self.review)
        self.file_info = self._text_block(body_layout, "FILE", muted=True)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        right.addWidget(scroll, 1)

        actions = self._actions = QHBoxLayout()   # under the poster and details, from the poster's left edge
        actions.setSpacing(12)
        self.watch_btn = IconButton("play", object_name="", color="#ffffff", text="Play")   # white over the blue square
        self.watch_btn.setToolTip("Watch")
        self.watch_btn.setStyleSheet("QPushButton { border: none; border-radius: 10px; padding: 0; }")
        self.watch_btn.setProperty("primary", True)
        self.watch_btn.clicked.connect(self._watch)
        self.fav_btn = IconButton("favorite", "favorite_on", checked_color="text")   # the filled heart is enough
        self.fav_btn.setToolTip("Favorite")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "favorite", on))
        self.seen_btn = IconButton("watched", "watched_on")
        self.seen_btn.setToolTip("Mark as watched")
        self.seen_btn.setCheckable(True)
        self.seen_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watched", on))
        self.list_btn = IconButton("watchlist", "watchlist_on")
        self.list_btn.setToolTip("Watchlist")
        self.list_btn.setCheckable(True)
        self.list_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watchlist", on))
        self.coll_btn = IconButton("collections")
        self.coll_btn.setToolTip("Collections")
        coll_menu = QMenu(self.coll_btn)
        coll_menu.aboutToShow.connect(lambda: self._fill_collections(coll_menu))
        self.coll_btn.setMenu(coll_menu)
        self.trailer_btn = IconButton("trailer")
        self.trailer_btn.setToolTip("Trailer")
        self.trailer_btn.clicked.connect(self._open_trailer)
        more = IconButton("menu", object_name="plainIcon")
        more.setToolTip("More")
        more_menu = QMenu(more)
        more_menu.addAction("More info", self._more_info)
        more_menu.addAction("Refresh metadata", self._refresh)
        more_menu.addAction("Fix match…", self._fix_match)
        more_menu.addAction("Edit metadata…", self._edit)
        more_menu.addAction("Show in folder", self._show_folder)
        more.setMenu(more_menu)
        for w in (self.fav_btn, self.seen_btn, more):
            w.setFixedSize(ACTION_BOX, ACTION_BOX)
        for w in (self.watch_btn, self.fav_btn, self.seen_btn, self.list_btn, self.coll_btn, self.trailer_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(more)   # "More" at the right edge
        actions.setContentsMargins(0, 0, 8, 0)   # same right edge as the text above (the scroll body has 8px)
        page.addLayout(actions)

    def _text_block(self, layout: QVBoxLayout, heading: str, muted: bool = False) -> QLabel:
        head = QLabel(heading)
        head.setObjectName("section")
        head.setContentsMargins(0, SECTION_GAP, 0, 0)
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
        self.tech.set_badges(badges(m.get("tech")) + ([format_size(m["size"])] if m.get("size") else []))

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
        self._populate_tags(m)
        self._set_block(self.director, m["director"] or "")
        self._set_block(self.cast, ", ".join(c["name"] for c in m["cast"][:10]))
        similar = similar_movies(m, self.service.movies)
        self.similar.row.movie_model.set_movies(similar)
        self.similar.count.setText(str(len(similar)))
        self.similar.setVisible(bool(similar))
        self._set_block(self.file_info, m["path"])

        self.review.set_values(m.get("user_rating") or 0, m.get("user_comment") or "")

        self._load_poster(m)
        self._load_backdrop(m)

        for button, value in ((self.fav_btn, m["favorite"]), (self.seen_btn, m["watched"])):
            button.blockSignals(True)
            button.setChecked(value)
            button.blockSignals(False)
        self.list_btn.blockSignals(True)
        self.list_btn.setChecked(m["watchlist"])
        self.list_btn.blockSignals(False)
        self.trailer_btn.setVisible(bool(m["trailer_key"]))

    def _populate_tags(self, movie: dict) -> None:
        while self.tags_row.count() > 2:
            item = self.tags_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        tags = movie.get("tags", [])
        self.tag_head.setVisible(bool(tags) or bool(self.service.tags))
        self.tags_box.setVisible(bool(tags) or bool(self.service.tags))
        for tag in tags:
            button = QPushButton(tag["name"])
            button.clicked.connect(lambda _checked=False, tag_id=tag["id"]:
                                    self.filter_tag_requested.emit(tag_id))
            color = QColor(tag["color"])
            foreground = "#17202a" if color.lightness() > 175 else "#ffffff"
            button.setStyleSheet(
                f"QPushButton {{ background: {tag['color']}; color: {foreground}; border: none;"
                " border-radius: 11px; padding: 4px 10px; font-weight: 600; }"
                f"QPushButton:hover {{ background: {color.lighter(115).name()}; }}")
            button.setToolTip("Right-click to change the color or remove this tag.")
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, current=tag, widget=button: self._tag_context_menu(current, widget, pos))
            self.tags_row.insertWidget(self.tags_row.count() - 2, button)

    def _show_tags_menu(self) -> None:
        menu = QMenu(self)
        movie_id = self.movie_id
        current = {tag["id"] for tag in self.service.by_id[movie_id].get("tags", [])}
        for tag in self.service.tags:
            action = menu.addAction(tag["name"])
            action.setCheckable(True)
            action.setChecked(tag["id"] in current)
            action.triggered.connect(
                lambda checked, tag_id=tag["id"]: self.service.set_movie_tag(movie_id, tag_id, checked))
        if self.service.tags:
            menu.addSeparator()
        menu.addAction("Create new tag…", self._create_tag)
        menu.exec(self.tag_add_btn.mapToGlobal(self.tag_add_btn.rect().bottomLeft()))

    def _create_tag(self) -> None:
        name, accepted = QInputDialog.getText(self, "Create tag", "Tag name:")
        if not accepted or not name.strip():
            return
        try:
            tag_id = self.service.create_tag(name)
            self.service.set_movie_tag(self.movie_id, tag_id, True)
        except ValueError as exc:
            QMessageBox.warning(self, "Could not create tag", str(exc))

    def _tag_context_menu(self, tag: dict, button: QPushButton, position) -> None:
        menu = QMenu(self)
        menu.addAction("Change color…", lambda: self._change_tag_color(tag))
        menu.addAction("Remove from this movie", lambda: self.service.set_movie_tag(self.movie_id, tag["id"], False))
        menu.exec(button.mapToGlobal(position))

    def _change_tag_color(self, tag: dict) -> None:
        color = QColorDialog.getColor(QColor(tag["color"]), self, "Choose tag color")
        if color.isValid():
            self.service.set_tag_color(tag["id"], color.name())

    def _more_info(self) -> None:
        movie = self.service.by_id[self.movie_id]
        show_more_info(self, movie["display_title"], movie.get("extra") or {},
                       movie.get("size"), movie.get("franchise"))

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
            painter.fillRect(0, 0, self.width(), BACKDROP_HEIGHT, backdrop_gradient(BACKDROP_HEIGHT, bg))
        painter.end()

    def resizeEvent(self, event) -> None:
        self._backdrop_scaled = None
        side = side_margin(self.width())
        self._content.setContentsMargins(side, 0, side, 0)
        self._actions.setContentsMargins(side, 0, side, 0)
        super().resizeEvent(event)

    def _leave(self) -> None:
        self.review.autosave()
        self.back_requested.emit()

    def _escape(self) -> None:
        if not self.review.release_focus():   # Esc while typing a comment only leaves the field
            self._leave()

    # -- actions ---------------------------------------------------------------------------------
    def _set_rating(self, value: int) -> None:
        m = self.service.by_id[self.movie_id]
        self.service.set_review(self.movie_id, value, m.get("user_comment") or "")

    def _save_comment(self, text: str) -> None:
        m = self.service.by_id[self.movie_id]
        self.service.set_review(self.movie_id, m.get("user_rating") or 0, text)

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

    def _edit(self) -> None:
        EditDialog(self.service, self.movie_id, self).exec()
