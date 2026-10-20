"""Janela principal: barra lateral + busca/ordenação + grade de capas."""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint,
                            QPropertyAnimation, Qt, QTimer)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import filters
from ..service import LibraryService
from .dialogs import (ask_new_collection, ask_rename_collection, confirm_delete_collection,
                      populate_collections_menu)
from .grid import MovieGrid
from .match_dialog import MatchDialog
from .movie_dialog import MovieDialog
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, service: LibraryService):
        super().__init__()
        self.service = service
        self.flt: filters.Filter = ("all", None)
        self.query = ""
        self.sort_id = service.settings.get("sort_id")
        self._detail: MovieDialog | None = None
        self._sliding = False
        self.setWindowTitle("CineLocal")
        self.resize(1380, 860)
        self.setMinimumSize(920, 600)

        self._sidebar_timer = QTimer(self, singleShot=True, interval=350)
        self._sidebar_timer.timeout.connect(self._rebuild_sidebar)

        self._build_ui()
        self._connect()

    # ------------------------------------------------------------------ construção --
    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.stack.addWidget(self._build_welcome())
        self.stack.addWidget(self._build_library())
        self._build_status_bar()

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(14)
        title = QLabel("CineLocal")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Sua videoteca pessoal, rápida e offline.\n"
                          "Escolha a pasta onde estão seus filmes para começar.")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignCenter)
        choose = QPushButton("Selecionar pasta de filmes")
        choose.setProperty("primary", True)
        choose.setMinimumHeight(46)
        choose.setMinimumWidth(280)
        choose.clicked.connect(self._choose_folder)
        key = QPushButton("Configurar chave do TMDB")
        key.clicked.connect(lambda: self.open_settings(focus_key=True))
        note = QLabel("Os arquivos nunca são alterados. A internet só é usada para baixar\n"
                      "capas e informações dos filmes novos.")
        note.setObjectName("muted")
        note.setAlignment(Qt.AlignCenter)
        for w, align in ((title, Qt.AlignHCenter), (subtitle, Qt.AlignHCenter),
                         (choose, Qt.AlignHCenter), (key, Qt.AlignHCenter), (note, Qt.AlignHCenter)):
            layout.addWidget(w, 0, align)
        return page

    def _build_library(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.setFixedWidth(260)
        outer.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("content")
        column = QVBoxLayout(content)
        column.setContentsMargins(26, 18, 10, 6)
        column.setSpacing(10)
        outer.addWidget(content, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título, ator, diretor ou gênero…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.sort_combo = QComboBox()
        for sort_id, label, *_ in filters.SORT_OPTIONS:
            self.sort_combo.addItem(label, sort_id)
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(self.sort_id)))
        rescan = QPushButton("⟳  Reescanear")
        rescan.clicked.connect(self.service.start_scan)
        meta = QPushButton("Metadados")
        meta_menu = QMenu(meta)
        meta_menu.addAction("Buscar metadados dos filmes pendentes",
                            lambda: self.service.start_update("pending"))
        meta_menu.addAction("Forçar atualização de todos os filmes", self._confirm_update_all)
        meta_menu.addSeparator()
        meta_menu.addAction("Revisar filmes sem correspondência…", self.review_all)
        meta.setMenu(meta_menu)
        settings = QPushButton("⚙")
        settings.setToolTip("Configurações (Ctrl+,)")
        settings.setFixedWidth(46)
        settings.clicked.connect(lambda: self.open_settings())
        bar.addWidget(self.search, 1)
        bar.addWidget(QLabel("Ordenar:"))
        bar.addWidget(self.sort_combo)
        bar.addWidget(rescan)
        bar.addWidget(meta)
        bar.addWidget(settings)
        column.addLayout(bar)

        self.infobar = QFrame()
        self.infobar.setObjectName("infobar")
        info_row = QHBoxLayout(self.infobar)
        info_row.setContentsMargins(16, 10, 10, 10)
        info_row.addWidget(QLabel("Para baixar capas e informações, configure sua chave gratuita do TMDB."), 1)
        info_btn = QPushButton("Configurar")
        info_btn.clicked.connect(lambda: self.open_settings(focus_key=True))
        info_row.addWidget(info_btn)
        column.addWidget(self.infobar)

        head = QHBoxLayout()
        self.heading = QLabel("Todos os filmes")
        self.heading.setObjectName("heading")
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        head.addWidget(self.heading)
        head.addSpacing(12)
        head.addWidget(self.count_label, 0, Qt.AlignBottom)
        head.addStretch(1)
        column.addLayout(head)

        self.views = QStackedWidget()
        self.grid = MovieGrid()
        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.views.addWidget(self.grid)
        self.views.addWidget(self.empty)
        column.addWidget(self.views, 1)
        return page

    def _build_status_bar(self) -> None:
        self.progress_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setTextVisible(False)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.setStyleSheet("padding: 3px 12px;")
        self.cancel_btn.clicked.connect(self.service.cancel_update)
        for w in (self.progress_label, self.progress_bar, self.cancel_btn):
            self.statusBar().addPermanentWidget(w)
            w.hide()

    def _connect(self) -> None:
        s = self.service
        self.sidebar.filter_changed.connect(self._on_filter)
        self.sidebar.new_collection_requested.connect(lambda: ask_new_collection(self, s))
        self.sidebar.rename_collection_requested.connect(lambda cid: ask_rename_collection(self, s, cid))
        self.sidebar.delete_collection_requested.connect(self._delete_collection)
        self.search.textChanged.connect(self._on_search)
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        self.grid.movie_opened.connect(self.open_movie)
        self.grid.context_requested.connect(self._context_menu)

        s.library_changed.connect(self._on_library_changed)
        s.movie_changed.connect(self._on_movie_changed)
        s.progress.connect(self._on_progress)
        s.busy_changed.connect(self._on_busy)
        s.scan_finished.connect(self._on_scan_finished)
        s.update_finished.connect(self._on_update_finished)
        s.message.connect(lambda text: self.statusBar().showMessage(text, 6000))
        s.error.connect(lambda text: QMessageBox.warning(self, "CineLocal", text))

        QShortcut(QKeySequence.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence("F5"), self, activated=s.start_scan)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)
        QShortcut(QKeySequence("Esc"), self.search, activated=self.search.clear)

    # ---------------------------------------------------------------------- início --
    def start(self) -> None:
        self.service.reload()
        self._rebuild_sidebar()
        self.refresh_view()
        self._update_infobar()
        folder = self.service.settings.get("library_path")
        if folder:
            self.stack.setCurrentIndex(1)
            self.service.start_scan()
        else:
            self.stack.setCurrentIndex(0)

    def _choose_folder(self) -> None:
        import os
        path = QFileDialog.getExistingDirectory(self, "Selecionar pasta de filmes", os.path.expanduser("~"))
        if not path:
            return
        self.service.settings.update(library_path=path)
        self.stack.setCurrentIndex(1)
        self._update_infobar()
        if not self.service.has_key:
            self.open_settings(
                focus_key=True,
                intro="Para baixar capas e informações dos filmes, cole sua chave gratuita do TMDB.\n"
                      "Você pode pular esta etapa e configurá-la depois.")
        self.service.start_scan()

    # ------------------------------------------------------------------ visualização --
    def refresh_view(self) -> None:
        bar = self.grid.verticalScrollBar()
        position = bar.value()
        visible = filters.filter_movies(self.service.movies, self.flt, self.service.membership, self.query)
        visible = filters.sort_movies(visible, self.sort_id)
        self.grid.movie_model.set_movies(visible)
        bar.setValue(position)

        total = len(self.service.movies)
        self.heading.setText(self._heading_text())
        self.count_label.setText(f"{len(visible)} de {total}" if len(visible) != total
                                 else f"{total} filmes")
        if visible:
            self.views.setCurrentWidget(self.grid)
        else:
            self.empty.setText(self._empty_text(total))
            self.views.setCurrentWidget(self.empty)

    def _empty_text(self, total: int) -> str:
        if self.query:
            return "Nenhum filme corresponde à busca."
        if total == 0:
            return "Nenhum filme encontrado na pasta selecionada.\nUse ⚙ para escolher outra pasta."
        return "Nenhum filme nesta seção."

    def _heading_text(self) -> str:
        kind, value = self.flt
        names = {"all": "Todos os filmes", "favorites": "Favoritos", "review": "Precisam de revisão"}
        if kind in names:
            return names[kind]
        if kind == "watched":
            return "Assistidos" if value else "Não assistidos"
        if kind == "collection":
            return self.service.collection_name(value)
        if kind == "decade":
            return f"Anos {value}"
        return str(value)

    def _rebuild_sidebar(self) -> None:
        counts = filters.sidebar_counts(self.service.movies)
        self.sidebar.rebuild(counts, self.service.collections, self.service.membership, self.flt)
        if self.sidebar.current_filter != self.flt:   # seleção anterior deixou de existir
            self.flt = self.sidebar.current_filter
            self.refresh_view()

    def _update_infobar(self) -> None:
        self.infobar.setVisible(not self.service.has_key)

    # ---------------------------------------------------------------------- eventos --
    def _on_filter(self, flt) -> None:
        self.flt = flt
        self.refresh_view()

    def _on_search(self, text: str) -> None:
        self.query = text
        self.refresh_view()

    def _on_sort(self) -> None:
        self.sort_id = self.sort_combo.currentData()
        self.service.settings.update(sort_id=self.sort_id)
        self.refresh_view()

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _on_library_changed(self) -> None:
        self._rebuild_sidebar()
        self.refresh_view()

    def _on_movie_changed(self, movie_id: int) -> None:
        self.grid.movie_model.refresh_movie(movie_id)
        if self.flt[0] in ("favorites", "watched", "review"):
            self.refresh_view()   # o filme pode ter entrado/saído da seção atual
        self._sidebar_timer.start()

    def _on_progress(self, done: int, total: int, title: str) -> None:
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.progress_label.setText(f"Metadados {done}/{total}" + (f" — {title}" if title else ""))

    def _on_busy(self, busy: bool, text: str) -> None:
        updating = self.service.updating
        show_progress = busy and updating
        for w in (self.progress_label, self.progress_bar, self.cancel_btn):
            w.setVisible(show_progress)
        if busy and not updating and text:
            self.statusBar().showMessage(text)
        elif not busy:
            self.statusBar().clearMessage()

    def _on_scan_finished(self, added: int, removed: int) -> None:
        if added or removed:
            self.statusBar().showMessage(f"{added} filme(s) novo(s), {removed} removido(s).", 8000)

    def _on_update_finished(self, summary: dict) -> None:
        text = (f"Metadados: {summary['matched']} atualizado(s), "
                f"{summary['ambiguous'] + summary['not_found']} para revisar, {summary['failed']} com falha.")
        if summary["cancelled"]:
            text += " (cancelado)"
        self.statusBar().showMessage(text, 12000)
        pending_review = summary["ambiguous"] + summary["not_found"]
        if pending_review and not summary["cancelled"]:
            QTimer.singleShot(400, lambda: self._offer_review(pending_review))

    # ---------------------------------------------------------------------- ações --
    def open_movie(self, movie_id: int) -> None:
        if self._sliding:
            return
        self._discard_detail()
        page = MovieDialog(self.service, movie_id, self)
        page.back_requested.connect(self.close_movie)
        self._detail = page
        self.stack.addWidget(page)
        self._slide_to(page, forward=True)

    def close_movie(self) -> None:
        if self._sliding or self._detail is None or self.stack.currentWidget() is not self._detail:
            return

        def done() -> None:
            self._discard_detail()
            self.grid.setFocus()

        self._slide_to(self.stack.widget(1), forward=False, done=done)

    def _discard_detail(self) -> None:
        if self._detail is not None:
            self.stack.removeWidget(self._detail)
            self._detail.deleteLater()
            self._detail = None

    def _slide_to(self, target: QWidget, forward: bool, done=None) -> None:
        """Troca a página do `stack` deslizando para o lado (a lista continua viva por baixo,
        então rolagem, busca, filtro e seleção são preservados)."""
        current = self.stack.currentWidget()
        width, height = self.stack.width(), self.stack.height()
        sign = 1 if forward else -1
        target.setGeometry(sign * width, 0, width, height)
        target.show()
        target.raise_()
        group = QParallelAnimationGroup()
        for widget, start, end in ((current, 0, -sign * width), (target, sign * width, 0)):
            anim = QPropertyAnimation(widget, b"pos")
            anim.setStartValue(QPoint(start, 0))
            anim.setEndValue(QPoint(end, 0))
            anim.setDuration(280)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            group.addAnimation(anim)

        def finish() -> None:
            self.stack.setCurrentWidget(target)
            for widget in (current, target):
                widget.setGeometry(self.stack.rect())
            self._sliding = False
            if done:
                done()

        group.finished.connect(finish)
        self._anim = group
        self._sliding = True
        group.start()

    def open_settings(self, focus_key: bool = False, intro: str = "") -> None:
        s = self.service.settings
        old = {k: s.get(k) for k in ("library_path", "tmdb_api_key", "language")}
        dialog = SettingsDialog(self.service, self, intro=intro, focus_key=focus_key)
        dialog.exec()
        if not dialog.saved:
            return
        s.update(**dialog.values())
        self._update_infobar()
        if not s.get("library_path"):
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)

        language_changed = old["language"] != s.get("language") and bool(self.service.movies)
        if old["library_path"] != s.get("library_path") or (not old["tmdb_api_key"] and s.get("tmdb_api_key")):
            self.service.start_scan()
        if language_changed:
            answer = QMessageBox.question(
                self, "Idioma alterado",
                "Atualizar agora os metadados de todos os filmes para o novo idioma?\n"
                "(Isso usa a internet. Novos filmes já usarão o novo idioma.)")
            if answer == QMessageBox.Yes:
                self.service.start_update("all")

    def _confirm_update_all(self) -> None:
        answer = QMessageBox.question(
            self, "Atualizar metadados",
            "Baixar novamente os metadados de todos os filmes?\n"
            "As correspondências já confirmadas são mantidas.")
        if answer == QMessageBox.Yes:
            self.service.start_update("all")

    def _offer_review(self, count: int) -> None:
        answer = QMessageBox.question(
            self, "Revisão necessária",
            f"{count} filme(s) não puderam ser identificados com segurança.\nRevisar agora?")
        if answer == QMessageBox.Yes:
            self.review_all()

    def review_all(self) -> None:
        ids = [m["id"] for m in self.service.movies if m["status"] in ("ambiguous", "not_found")]
        if not ids:
            self.statusBar().showMessage("Nenhum filme precisa de revisão.", 5000)
            return
        for position, movie_id in enumerate(ids, start=1):
            movie = self.service.by_id.get(movie_id)
            if movie is None:
                continue
            dialog = MatchDialog(self.service, movie, self, allow_skip=True,
                                 position=f"{position}/{len(ids)}")
            dialog.exec()
            if dialog.selected_tmdb_id:
                self.service.apply_match(movie_id, dialog.selected_tmdb_id)
            elif not dialog.skipped:
                break

    def _delete_collection(self, collection_id: int) -> None:
        confirm_delete_collection(self, self.service, collection_id)

    def _context_menu(self, ids: list[int], global_pos) -> None:
        s = self.service
        movies = [s.by_id[i] for i in ids if i in s.by_id]
        if not movies:
            return
        single = len(movies) == 1
        menu = QMenu(self)
        if single:
            menu.addAction("Abrir detalhes", lambda: self.open_movie(ids[0]))
            menu.addAction("▶  Assistir", lambda: self._play(ids[0]))
            menu.addSeparator()

        all_fav = all(m["favorite"] for m in movies)
        all_seen = all(m["watched"] for m in movies)
        menu.addAction("Remover dos favoritos" if all_fav else "♥  Favoritar",
                       lambda: s.set_flag(ids, "favorite", not all_fav))
        menu.addAction("Marcar como não assistido" if all_seen else "✓  Marcar como assistido",
                       lambda: s.set_flag(ids, "watched", not all_seen))
        collections_menu = menu.addMenu("Coleções")
        populate_collections_menu(collections_menu, s, ids, self)
        if self.flt[0] == "collection":
            menu.addAction("Remover desta coleção",
                           lambda: s.set_in_collection(self.flt[1], ids, False))
        menu.addSeparator()
        menu.addAction("Atualizar metadados", lambda: self._refresh_ids(ids))
        if single:
            menu.addAction("Corrigir correspondência…", lambda: self._fix_match(ids[0]))
        menu.exec(global_pos)

    def _play(self, movie_id: int) -> None:
        try:
            self.service.play(movie_id)
        except OSError as exc:
            QMessageBox.warning(self, "Não foi possível abrir", str(exc))

    def _refresh_ids(self, ids: list[int]) -> None:
        if len(ids) == 1:
            self.service.apply_match(ids[0])
        else:
            self.service.start_update("ids", ids)

    def _fix_match(self, movie_id: int) -> None:
        dialog = MatchDialog(self.service, self.service.by_id[movie_id], self)
        dialog.exec()
        if dialog.selected_tmdb_id:
            self.service.apply_match(movie_id, dialog.selected_tmdb_id)

    def closeEvent(self, event) -> None:
        self.service.shutdown()
        super().closeEvent(event)
