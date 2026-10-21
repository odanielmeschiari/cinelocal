"""Tela de uma série: metadados gerais, temporadas e episódios (cada um com seus metadados)."""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QKeySequence, QLinearGradient, QPainter,
                           QPixmap, QShortcut)
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import images
from ..service import LibraryService
from ..utils import format_runtime, format_votes
from .match_dialog import MatchDialog
from .theme import COLORS
from .widgets import rounded_pixmap

POSTER_SIZE = (180, 270)
BACKDROP_HEIGHT = 340


def _date(text) -> str:
    parts = (text or "").split("-")
    return "/".join(reversed(parts)) if len(parts) == 3 else (text or "")


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class SeriesDialog(QWidget):
    back_requested = Signal()
    play_requested = Signal(int)   # id do episódio (ou da série, para tocar o próximo)

    def __init__(self, service: LibraryService, movie_id: int, parent=None):
        super().__init__(parent)
        self.service = service
        self.movie_id = movie_id          # id da série na interface (negativo)
        self.series_id = -movie_id
        self._backdrop: QPixmap | None = None
        self._backdrop_scaled: QPixmap | None = None
        self._season = None
        self.setWindowTitle(service.by_id[movie_id]["display_title"])
        self._build()
        QShortcut(QKeySequence("Esc"), self, activated=self.back_requested.emit)
        QShortcut(QKeySequence.Back, self, activated=self.back_requested.emit)
        self._populate()
        service.movie_changed.connect(self._on_movie_changed)

    # -- construção ------------------------------------------------------------------
    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(34, 20, 34, 20)
        page.setSpacing(10)
        self.back_btn = QPushButton("←  Voltar")
        self.back_btn.setToolTip("Voltar à lista (Esc)")
        self.back_btn.clicked.connect(self.back_requested.emit)
        page.addWidget(self.back_btn, 0, Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        column = QVBoxLayout(body)
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
        top.addLayout(right, 1)
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
        self.overview = QLabel()
        self.overview.setWordWrap(True)
        self.overview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.creator = QLabel()
        self.creator.setObjectName("muted")
        self.creator.setWordWrap(True)
        self.cast = QLabel()
        self.cast.setObjectName("muted")
        self.cast.setWordWrap(True)
        for w in (self.title, self.meta, self.rating, self.tagline, self.banner,
                  self.overview, self.creator, self.cast):
            right.addWidget(w)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.watch_btn = QPushButton("▶  Assistir")
        self.watch_btn.setProperty("primary", True)
        self.watch_btn.clicked.connect(lambda: self.play_requested.emit(self.movie_id))
        self.fav_btn = QPushButton("♥  Favoritar")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "favorite", on))
        self.seen_btn = QPushButton("✓  Assistida")
        self.seen_btn.setCheckable(True)
        self.seen_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watched", on))
        self.list_btn = QPushButton("＋  Watchlist")
        self.list_btn.setCheckable(True)
        self.list_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watchlist", on))
        self.trailer_btn = QPushButton("Trailer")
        self.trailer_btn.clicked.connect(self._open_trailer)
        more = QPushButton("⋯")
        more_menu = QMenu(more)
        more_menu.addAction("Atualizar metadados", lambda: self.service.apply_match(self.movie_id))
        more_menu.addAction("Corrigir correspondência…", self._fix_match)
        more.setMenu(more_menu)
        for w in (self.watch_btn, self.fav_btn, self.seen_btn, self.list_btn, self.trailer_btn):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(more)
        right.addLayout(actions)
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
        column.addStretch(1)

    # -- dados -------------------------------------------------------------------------
    def _populate(self) -> None:
        s = self.service.by_id.get(self.movie_id)
        if s is None:
            self.back_requested.emit()
            return
        self.setWindowTitle(s["display_title"])
        self.title.setText(s["display_title"])
        parts = [str(s["display_year"] or ""),
                 _plural(s["season_count"], "temporada", "temporadas"),
                 _plural(s["episode_count"], "episódio", "episódios"),
                 format_runtime(s["runtime"]), ", ".join(s["genres"])]
        self.meta.setText("   •   ".join(p for p in parts if p))
        if s["rating"] and s["votes"]:
            self.rating.setText(f"★ {s['rating']:.1f}/10   "
                                f"<span style='color:{COLORS['muted']};font-weight:400;font-size:10pt'>"
                                f"{format_votes(s['votes'])} votos</span>")
        else:
            self.rating.setText("")
        self.rating.setVisible(bool(self.rating.text()))
        self.tagline.setText(f"“{s['tagline']}”" if s["tagline"] else "")
        self.tagline.setVisible(bool(s["tagline"]))
        banners = {
            "pending": "Os metadados ainda não foram baixados para esta série.",
            "ambiguous": "Várias séries combinam com estes arquivos. Use ⋯ → Corrigir correspondência.",
            "not_found": "Esta série não foi encontrada. Use ⋯ → Corrigir correspondência.",
        }
        self.banner.setText(banners.get(s["status"], ""))
        self.banner.setVisible(bool(self.banner.text()))
        overview = s["overview"] or ("Sem sinopse disponível." if s["status"] == "matched" else "")
        for label, text in ((self.overview, overview),
                            (self.creator, f"Criação: {s['director']}" if s["director"] else ""),
                            (self.cast, "Elenco: " + ", ".join(c["name"] for c in s["cast"][:10])
                             if s["cast"] else "")):
            label.setText(text)
            label.setVisible(bool(text))

        self._load_poster(s)
        pixmap = QPixmap(str(images.backdrop_file(s["id"]))) if s["has_backdrop"] else QPixmap()
        self._backdrop = None if pixmap.isNull() else pixmap
        self._backdrop_scaled = None
        self.update()

        for button, value, on_text, off_text in (
                (self.fav_btn, s["favorite"], "♥  Favorita", "♥  Favoritar"),
                (self.seen_btn, s["watched"], "✓  Assistida", "✓  Marcar como assistida"),
                (self.list_btn, s["watchlist"], "✓  Na Watchlist", "＋  Watchlist")):
            button.blockSignals(True)
            button.setChecked(value)
            button.setText(on_text if value else off_text)
            button.blockSignals(False)
        self.trailer_btn.setVisible(bool(s["trailer_key"]))
        nxt = self.service.by_id.get(self.service.next_episode(self.series_id))
        self.watch_btn.setEnabled(nxt is not None)
        self.watch_btn.setText(f"▶  Assistir T{nxt['season']}E{nxt['episode']}" if nxt else "▶  Assistir")
        self._fill_seasons()

    def _fill_seasons(self) -> None:
        episodes = self.service.episodes.get(self.series_id, [])
        seasons = sorted({e["season"] for e in episodes if e["season"] is not None})
        wanted = self._season
        if wanted not in seasons:   # primeira temporada com episódio ainda não assistido
            wanted = next((n for n in seasons
                           if any(e["season"] == n and not e["watched"] for e in episodes)),
                          seasons[0] if seasons else None)
        self.season_combo.blockSignals(True)
        self.season_combo.clear()
        for n in seasons:
            count = sum(1 for e in episodes if e["season"] == n)
            self.season_combo.addItem(f"{'Especiais' if n == 0 else f'Temporada {n}'}"
                                      f"  ·  {_plural(count, 'episódio', 'episódios')}", n)
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
        QTimer.singleShot(0, lambda: bar.setValue(position))   # mantém a rolagem ao atualizar

    def _episode_row(self, e: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("episode")
        row.setStyleSheet(f"QFrame#episode {{ background: {COLORS['surface']};"
                          f" border: 1px solid {COLORS['border']}; border-radius: 10px; }}")
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
                   f"★ {e['ep_rating']:.1f}" if e["ep_rating"] else ""]
        meta = QLabel("   •   ".join(p for p in details if p))
        meta.setObjectName("muted")
        meta.setVisible(any(details))
        text = QLabel(e["ep_overview"] or e["file_name"])
        text.setObjectName("muted" if not e["ep_overview"] else "")
        text.setWordWrap(True)
        for w in (name, meta, text):
            info.addWidget(w)
        layout.addLayout(info, 1)

        play = QPushButton("▶")
        play.setToolTip("Assistir este episódio")
        play.clicked.connect(lambda _checked=False, i=e["id"]: self.play_requested.emit(i))
        seen = QPushButton("✓")
        seen.setCheckable(True)
        seen.setChecked(e["watched"])
        seen.setToolTip("Marcar como assistido")
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
                f"background:{COLORS['surface2']}; border-radius:12px; color:{COLORS['muted']};")
            self.poster.setText("Sem capa")
            return
        self.poster.setStyleSheet("")
        w, h = int(POSTER_SIZE[0] * dpr), int(POSTER_SIZE[1] * dpr)
        scaled = pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        cropped = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)
        cropped.setDevicePixelRatio(dpr)
        self.poster.setPixmap(rounded_pixmap(cropped, 12))

    def _on_movie_changed(self, movie_id: int) -> None:
        if movie_id == self.movie_id:
            self._populate()

    # -- fundo com backdrop ----------------------------------------------------------------
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
            top.setAlpha(170)
            gradient.setColorAt(0, top)
            gradient.setColorAt(1, bottom)
            painter.fillRect(0, 0, self.width(), BACKDROP_HEIGHT, gradient)
        painter.end()

    def resizeEvent(self, event) -> None:
        self._backdrop_scaled = None
        super().resizeEvent(event)

    # -- ações ---------------------------------------------------------------------------------
    def _open_trailer(self) -> None:
        key = self.service.by_id[self.movie_id]["trailer_key"]
        if key:
            QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={key}"))

    def _fix_match(self) -> None:
        dialog = MatchDialog(self.service, self.service.by_id[self.movie_id], self)
        dialog.exec()
        if dialog.selected_tmdb_id:
            self.service.apply_match(self.movie_id, dialog.selected_tmdb_id)
