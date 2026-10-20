"""Janela com os metadados do filme (capa, sinopse, nota, elenco...) e ações."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import images
from ..service import LibraryService
from ..utils import format_runtime, format_votes
from .dialogs import populate_collections_menu
from .match_dialog import MatchDialog
from .theme import COLORS
from .widgets import rounded_pixmap

POSTER_SIZE = (240, 360)
BACKDROP_HEIGHT = 380


class MovieDialog(QDialog):
    def __init__(self, service: LibraryService, movie_id: int, parent=None):
        super().__init__(parent)
        self.service = service
        self.movie_id = movie_id
        self._backdrop: QPixmap | None = None
        self._backdrop_scaled: QPixmap | None = None
        self._heads: dict[QLabel, QLabel] = {}
        self.setWindowTitle(service.by_id[movie_id]["display_title"])
        self.setModal(True)
        self.resize(1000, 660)
        self.setMinimumSize(860, 560)
        self._build()
        self._populate()
        service.movie_changed.connect(self._on_movie_changed)

    # -- construção ------------------------------------------------------------------
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(34, 34, 34, 30)
        root.setSpacing(30)

        self.poster = QLabel()
        self.poster.setFixedSize(*POSTER_SIZE)
        self.poster.setAlignment(Qt.AlignCenter)
        left = QVBoxLayout()
        left.addWidget(self.poster)
        left.addStretch(1)
        root.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)
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
        self.overview = self._text_block(body_layout, "SINOPSE")
        self.director = self._text_block(body_layout, "DIREÇÃO")
        self.cast = self._text_block(body_layout, "ELENCO")
        self.file_info = self._text_block(body_layout, "ARQUIVO", muted=True)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        right.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.watch_btn = QPushButton("▶  Assistir")
        self.watch_btn.setProperty("primary", True)
        self.watch_btn.clicked.connect(self._watch)
        self.fav_btn = QPushButton("♥  Favoritar")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "favorite", on))
        self.seen_btn = QPushButton("✓  Assistido")
        self.seen_btn.setCheckable(True)
        self.seen_btn.toggled.connect(lambda on: self.service.set_flag([self.movie_id], "watched", on))
        self.coll_btn = QPushButton("＋  Coleções")
        coll_menu = QMenu(self.coll_btn)
        coll_menu.aboutToShow.connect(lambda: self._fill_collections(coll_menu))
        self.coll_btn.setMenu(coll_menu)
        self.trailer_btn = QPushButton("Trailer")
        self.trailer_btn.clicked.connect(self._open_trailer)
        more = QPushButton("⋯")
        more_menu = QMenu(more)
        more_menu.addAction("Atualizar metadados", self._refresh)
        more_menu.addAction("Corrigir correspondência…", self._fix_match)
        more_menu.addAction("Mostrar na pasta", self._show_folder)
        more.setMenu(more_menu)
        for w in (self.watch_btn, self.fav_btn, self.seen_btn, self.coll_btn, self.trailer_btn):
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
        if muted:
            text.setObjectName("muted")
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

    # -- dados -------------------------------------------------------------------------
    def _populate(self) -> None:
        m = self.service.by_id.get(self.movie_id)
        if m is None:
            self.reject()
            return
        self.setWindowTitle(m["display_title"])
        self.title.setText(m["display_title"])
        if m["original_title"] and m["original_title"] != m["display_title"]:
            self.title.setToolTip(f"Título original: {m['original_title']}")

        parts = [str(m["display_year"] or ""), format_runtime(m["runtime"]), ", ".join(m["genres"])]
        self.meta.setText("   •   ".join(p for p in parts if p))

        if m["rating"] and m["votes"]:
            self.rating.setText(f"★ {m['rating']:.1f}/10   "
                                f"<span style='color:{COLORS['muted']};font-weight:400;font-size:10pt'>"
                                f"{format_votes(m['votes'])} votos no TMDB</span>")
        else:
            self.rating.setText("")
        self.rating.setVisible(bool(self.rating.text()))
        self.tagline.setText(f"“{m['tagline']}”" if m["tagline"] else "")
        self.tagline.setVisible(bool(m["tagline"]))

        banners = {
            "pending": "Os metadados ainda não foram baixados para este filme.",
            "ambiguous": "Vários filmes combinam com este arquivo. Use ⋯ → Corrigir correspondência.",
            "not_found": "Este filme não foi encontrado no TMDB. Use ⋯ → Corrigir correspondência.",
        }
        self.banner.setText(banners.get(m["status"], ""))
        self.banner.setVisible(bool(self.banner.text()))

        overview = m["overview"] or ("Sem sinopse disponível." if m["status"] == "matched" else "")
        self._set_block(self.overview, overview)
        self._set_block(self.director, m["director"] or "")
        self._set_block(self.cast, ", ".join(c["name"] for c in m["cast"][:10]))
        self._set_block(self.file_info, m["path"])

        self._load_poster(m)
        self._load_backdrop(m)

        for button, value, on_text, off_text in (
                (self.fav_btn, m["favorite"], "♥  Favorito", "♥  Favoritar"),
                (self.seen_btn, m["watched"], "✓  Assistido", "✓  Marcar como assistido")):
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
            self.poster.setText("Sem capa")
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
            top.setAlpha(150)
            gradient.setColorAt(0, top)
            gradient.setColorAt(1, bottom)
            painter.fillRect(0, 0, self.width(), BACKDROP_HEIGHT, gradient)
        painter.end()

    def resizeEvent(self, event) -> None:
        self._backdrop_scaled = None
        super().resizeEvent(event)

    # -- ações ---------------------------------------------------------------------------------
    def _watch(self) -> None:
        try:
            self.service.play(self.movie_id)
        except OSError as exc:
            QMessageBox.warning(self, "Não foi possível abrir", str(exc))

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
            QMessageBox.warning(self, "Não foi possível abrir a pasta", str(exc))
