"""Series page: general metadata, seasons and episodes (each with its own metadata)."""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QPoint, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QMenu,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import images
from ..service import LibraryService
from ..utils import format_runtime, format_votes
from .detail_widgets import (ACTION_BOX, DETAIL_STYLE, DETAILS_OFFSET, POSTER_SIZE, SECTION_GAP,
                             ReviewBox, backdrop_gradient, cap_offset, show_more_info, side_margin)
from .edit_dialog import EditDialog
from .icons import IconButton
from .match_dialog import MatchDialog
from .theme import COLORS

BACKDROP_HEIGHT = 340
EP_BOX, EP_ICON = 36, 20   # episode row buttons: side of the button and of the icon (px)


def _date(text) -> str:
    return text or ""   # ISO date (YYYY-MM-DD), as returned by the API


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class SeriesDialog(QWidget):
    back_requested = Signal()
    play_requested = Signal(int)   # episode id (or series id, to play the next one)

    def __init__(self, service: LibraryService, movie_id: int, parent=None):
        super().__init__(parent)
        self.service = service
        self.movie_id = movie_id          # series id in the UI (negative)
        self.series_id = -movie_id
        self._backdrop: QPixmap | None = None
        self._backdrop_scaled: QPixmap | None = None
        self._season = None
        self._offset = DETAILS_OFFSET
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
        page.setContentsMargins(34, 20, 34, 20)
        page.setSpacing(10)
        self.back_btn = IconButton("back", object_name="plainIcon")
        self.back_btn.setToolTip("Back to the list (Esc)")
        self.back_btn.clicked.connect(self._leave)
        page.addWidget(self.back_btn, 0, Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        column = self._column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(14)
        self.scroll.setWidget(body)
        page.addWidget(self.scroll, 1)

        top = QHBoxLayout()
        top.setSpacing(30)
        column.addLayout(top)
        self.poster = QLabel()
        self.poster.setFixedSize(*POSTER_SIZE)
        self.poster.setAlignment(Qt.AlignCenter)
        left = QVBoxLayout()
        left.addWidget(self.poster)
        left.addStretch(1)
        top.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)
        # Empty space above the details. It starts at DETAILS_OFFSET and is trimmed by _fit_offset() so that
        # the first episodes are visible without scrolling.
        self._right_gap = QWidget()
        self._right_gap.setFixedHeight(DETAILS_OFFSET)
        right.addWidget(self._right_gap)
        top.addLayout(right, 1)
        self.title = QLabel()
        self.title.setObjectName("movieTitle")
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignTop)   # letters start at the label top
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
        self._cap = cap_offset(self.title)   # the poster's top lines up with the title's letters
        self._left_gap = QWidget()
        self._left_gap.setFixedHeight(DETAILS_OFFSET + self._cap)
        left.insertWidget(0, self._left_gap)
        self.overview = self._text_block(right, "OVERVIEW")
        self.creator = self._text_block(right, "CREATED BY")
        self.cast = self._text_block(right, "CAST")

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.watch_btn = IconButton("play", object_name="", color="#141414", text="Play")   # dark over the white square
        self.watch_btn.setStyleSheet("QPushButton { border: none; padding: 0; }")
        self.watch_btn.setProperty("primary", True)
        self.watch_btn.clicked.connect(lambda: self.play_requested.emit(self.movie_id))
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
        self.trailer_btn = IconButton("trailer")
        self.trailer_btn.setToolTip("Trailer")
        self.trailer_btn.clicked.connect(self._open_trailer)
        more = IconButton("menu", object_name="plainIcon")
        more.setToolTip("More")
        more_menu = QMenu(more)
        more_menu.addAction("More info", self._more_info)
        more_menu.addAction("Refresh metadata", lambda: self.service.apply_match(self.movie_id))
        more_menu.addAction("Fix match…", self._fix_match)
        more_menu.addAction("Edit metadata…", self._edit)
        more.setMenu(more_menu)
        for w in (self.fav_btn, self.seen_btn, more):
            w.setFixedSize(ACTION_BOX, ACTION_BOX)
        for w in (self.watch_btn, self.fav_btn, self.seen_btn, self.list_btn, self.trailer_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(more)   # "More" at the right edge
        column.addLayout(actions)   # under the poster and details, from the poster's left edge
        self.review = ReviewBox("Write your own comments about this series…")
        self.review.rating_changed.connect(self._set_rating)
        self.review.comment_saved.connect(self._save_comment)
        right.addStretch(1)

        self.season_combo = QComboBox()
        self.season_combo.setMinimumWidth(260)
        self.season_combo.currentIndexChanged.connect(self._fill_episodes)
        season_row = QHBoxLayout()
        season_row.addWidget(self.season_combo)
        season_row.addStretch(1)
        column.addLayout(season_row)

        self.ep_box = QVBoxLayout()
        self.ep_box.setSpacing(8)
        column.addLayout(self.ep_box)
        column.addWidget(self.review)   # below the episodes, so they are the first thing under the details
        column.addStretch(1)

    def _text_block(self, layout: QVBoxLayout, heading: str) -> QLabel:
        head = QLabel(heading)
        head.setObjectName("section")
        head.setContentsMargins(0, SECTION_GAP, 0, 0)
        text = QLabel()
        text.setObjectName("detailText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
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
        s = self.service.by_id.get(self.movie_id)
        if s is None:
            self.back_requested.emit()
            return
        self.setWindowTitle(s["display_title"])
        self.title.setText(s["display_title"])
        parts = [str(s["display_year"] or ""), s.get("certification") or "",
                 _plural(s["season_count"], "season", "seasons"),
                 _plural(s["episode_count"], "episode", "episodes"),
                 format_runtime(s["runtime"]), ", ".join(s["genres"])]
        self.meta.setText("   •   ".join(p for p in parts if p))
        if s["rating"] and s["votes"]:
            self.rating.setText(f"Rating {s['rating']:.1f}/10   "
                                f"<span style='color:{COLORS['muted']};font-weight:400;font-size:12pt'>"
                                f"{format_votes(s['votes'])} votes</span>")
        else:
            self.rating.setText("")
        self.rating.setVisible(bool(self.rating.text()))
        self.tagline.setText(f"“{s['tagline']}”" if s["tagline"] else "")
        self.tagline.setVisible(bool(s["tagline"]))
        banners = {
            "pending": "Metadata has not been downloaded for this series yet.",
            "ambiguous": "Several series match these files. Use More → Fix match.",
            "not_found": "This series was not found. Use More → Fix match.",
        }
        self.banner.setText(banners.get(s["status"], ""))
        self.banner.setVisible(bool(self.banner.text()))
        overview = s["overview"] or ("No overview available." if s["status"] == "matched" else "")
        self._set_block(self.overview, overview)
        self._set_block(self.creator, s["director"] or "")
        self._set_block(self.cast, ", ".join(c["name"] for c in s["cast"][:10]))
        self.review.set_values(s.get("user_rating") or 0, s.get("user_comment") or "")

        self._load_poster(s)
        pixmap = QPixmap(str(images.backdrop_file(s["id"]))) if s["has_backdrop"] else QPixmap()
        self._backdrop = None if pixmap.isNull() else pixmap
        self._backdrop_scaled = None
        self.update()

        for button, value in ((self.fav_btn, s["favorite"]), (self.seen_btn, s["watched"])):
            button.blockSignals(True)
            button.setChecked(value)
            button.blockSignals(False)
        self.list_btn.blockSignals(True)
        self.list_btn.setChecked(s["watchlist"])
        self.list_btn.blockSignals(False)
        self.trailer_btn.setVisible(bool(s["trailer_key"]))
        nxt = self.service.by_id.get(self.service.next_episode(self.series_id))
        self.watch_btn.setEnabled(nxt is not None)
        self.watch_btn.setToolTip(f"Watch S{nxt['season']}E{nxt['episode']}" if nxt else "Watch")
        self._fill_seasons()

    def _fill_seasons(self) -> None:
        episodes = self.service.episodes.get(self.series_id, [])
        seasons = sorted({e["season"] for e in episodes if e["season"] is not None})
        wanted = self._season
        if wanted not in seasons:   # first season with an unwatched episode
            wanted = next((n for n in seasons
                           if any(e["season"] == n and not e["watched"] for e in episodes)),
                          seasons[0] if seasons else None)
        self.season_combo.blockSignals(True)
        self.season_combo.clear()
        for n in seasons:
            count = sum(1 for e in episodes if e["season"] == n)
            self.season_combo.addItem(f"{'Specials' if n == 0 else f'Season {n}'}"
                                      f"  ·  {_plural(count, 'episode', 'episodes')}", n)
        self.season_combo.setCurrentIndex(max(0, self.season_combo.findData(wanted)))
        self.season_combo.blockSignals(False)
        self._fill_episodes()

    def _fill_episodes(self) -> None:
        bar = self.scroll.verticalScrollBar()
        position = bar.value()
        while self.ep_box.count():
            item = self.ep_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._season = self.season_combo.currentData()
        for e in self.service.episodes.get(self.series_id, []):
            if e["season"] == self._season:
                self.ep_box.addWidget(self._episode_row(e))
        QTimer.singleShot(0, lambda: bar.setValue(position))   # keep the scroll position on refresh
        QTimer.singleShot(0, self._fit_offset)

    def _episode_row(self, e: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("episode")
        row.setStyleSheet(f"QFrame#episode {{ background: {COLORS['surface']};"
                          f" border: 1px solid {COLORS['border']}; }}"
                          f" QFrame#episode QLabel {{ font-size: 10pt; }}")   # compact, unlike the details above
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        number = QLabel(f"E{e['episode']:02d}" if e["episode"] is not None else "—")
        number.setObjectName("section")
        number.setFixedWidth(42)
        layout.addWidget(number, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        name = QLabel(e["display_title"])
        name.setStyleSheet("font-weight: 700;")
        name.setWordWrap(True)
        details = [_date(e["ep_air_date"]), format_runtime(e["ep_runtime"]),
                   f"Rating {e['ep_rating']:.1f}" if e["ep_rating"] else ""]
        meta = QLabel("   •   ".join(p for p in details if p))
        meta.setObjectName("muted")
        meta.setVisible(any(details))
        text = QLabel(e["ep_overview"] or e["file_name"])
        text.setObjectName("muted" if not e["ep_overview"] else "")
        text.setWordWrap(True)
        for w in (name, meta, text):
            info.addWidget(w)
        layout.addLayout(info, 1)

        play = IconButton("play", object_name="iconBtn", box=EP_BOX, size=EP_ICON)
        play.setToolTip("Watch this episode")
        play.clicked.connect(lambda _checked=False, i=e["id"]: self.play_requested.emit(i))
        seen = IconButton("watched", "watched_on", object_name="iconBtn", box=EP_BOX, size=EP_ICON)
        seen.setCheckable(True)
        seen.setChecked(e["watched"])
        seen.setToolTip("Mark as watched")
        seen.toggled.connect(lambda on, i=e["id"]: self.service.set_flag([i], "watched", on))
        layout.addWidget(play, 0, Qt.AlignTop)
        layout.addWidget(seen, 0, Qt.AlignTop)
        return row

    def _load_poster(self, s: dict) -> None:
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(str(images.poster_file(s["id"]))) if s["has_poster"] else QPixmap()
        if pixmap.isNull():
            self.poster.setPixmap(QPixmap())
            self.poster.setStyleSheet(
                f"background:{COLORS['surface2']}; color:{COLORS['muted']};")
            self.poster.setText("No poster")
            return
        self.poster.setStyleSheet("")
        w, h = int(POSTER_SIZE[0] * dpr), int(POSTER_SIZE[1] * dpr)
        scaled = pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        cropped = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)
        cropped.setDevicePixelRatio(dpr)
        self.poster.setPixmap(cropped)

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
        self._column.setContentsMargins(side, 0, side + 8, 0)
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_offset)

    def _set_offset(self, offset: int) -> None:
        self._offset = offset
        self._right_gap.setFixedHeight(offset)
        self._left_gap.setFixedHeight(offset + self._cap)
        body = self.scroll.widget()
        body.layout().activate()
        # The poster's top lines up with the top of the title's letters, whatever spacing the layouts add.
        delta = self.title.mapTo(body, QPoint(0, 0)).y() + self._cap - self.poster.mapTo(body, QPoint(0, 0)).y()
        if delta:
            self._left_gap.setFixedHeight(max(0, offset + self._cap + delta))
            body.layout().activate()

    def _fit_offset(self) -> None:
        """Raises the poster and details just enough for the first episodes to be visible without scrolling: the middle
        of the second episode sits at the bottom edge of the window (the first is whole and the next one peeks out,
        hinting that there is more below). Never lower than DETAILS_OFFSET."""
        if self.scroll.verticalScrollBar().value() > 0:
            return   # do not move the content under the user's scroll
        offset = self._offset
        if self.ep_box.count():
            row = self.ep_box.itemAt(min(1, self.ep_box.count() - 1)).widget()
            self._set_offset(0)
            middle = row.mapTo(self.scroll.widget(), row.rect().center()).y()   # grows 1:1 with the offset
            offset = max(0, min(DETAILS_OFFSET, self.scroll.viewport().height() - middle))
        self._set_offset(offset)

    def _leave(self) -> None:
        self.review.autosave()
        self.back_requested.emit()

    def _escape(self) -> None:
        if not self.review.release_focus():   # Esc while typing a comment only leaves the field
            self._leave()

    def _set_rating(self, value: int) -> None:
        s = self.service.by_id[self.movie_id]
        self.service.set_review(self.movie_id, value, s.get("user_comment") or "")

    def _save_comment(self, text: str) -> None:
        s = self.service.by_id[self.movie_id]
        self.service.set_review(self.movie_id, s.get("user_rating") or 0, text)

    # -- actions ---------------------------------------------------------------------------------
    def _open_trailer(self) -> None:
        key = self.service.by_id[self.movie_id]["trailer_key"]
        if key:
            QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={key}"))

    def _more_info(self) -> None:
        series = self.service.by_id[self.movie_id]
        episodes = self.service.episodes.get(self.series_id, [])
        total_size = sum(episode.get("size") or 0 for episode in episodes)
        techs = Counter(tuple(sorted(e["tech"].items())) for e in episodes if e.get("tech"))
        tech = dict(techs.most_common(1)[0][0]) if techs else None   # the most common quality among the episodes
        show_more_info(self, series["display_title"], series.get("extra") or {}, total_size,
                       series.get("franchise"), "Episode files size",
                       (("Episodes in library", str(len(episodes))),), tech)

    def _fix_match(self) -> None:
        dialog = MatchDialog(self.service, self.service.by_id[self.movie_id], self)
        dialog.exec()
        if dialog.selected_tmdb_id:
            self.service.apply_match(self.movie_id, dialog.selected_tmdb_id)

    def _edit(self) -> None:
        EditDialog(self.service, self.movie_id, self).exec()
