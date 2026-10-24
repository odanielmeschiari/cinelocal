"""Main window: sidebar + search/sorting + poster grid."""
from __future__ import annotations

import os

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint,
                            QPropertyAnimation, Qt, QTimer)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QInputDialog, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import filters
from ..service import LibraryService
from ..utils import star_text
from .advanced_search import AdvancedSearch
from .dialogs import (MovieSelectionDialog, ask_new_collection, ask_rename_collection,
                      confirm_delete_collection, populate_collections_menu)
from .duplicates_dialog import DuplicatesDialog
from .grid import CELL_H, MovieFlow
from .home import HomeSection
from .home_dialog import HomeDialog
from .icons import IconButton
from .match_dialog import MatchDialog
from .movie_dialog import MovieDialog
from .player_page import VlcPlayerPage, unavailable_reason
from .series_dialog import SeriesDialog
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar
from .stats_dialog import StatsDialog
from .tag_dialog import TagDialog

HOME_ROW_LIMIT = 40   # posters per row on the home screen (the section itself shows them all)
TOOL_BOX, TOOL_ICON = 36, 20   # top-bar icon buttons: a bit smaller than the detail/player ones (44, 24)


class MainWindow(QMainWindow):
    def __init__(self, service: LibraryService):
        super().__init__()
        self.service = service
        self.flt: filters.Filter = ("all", None)
        self.query = ""
        self.advanced: dict = {}   # criteria of the advanced search (empty = off)
        self.sort_id = service.settings.get("sort_id")
        self._home_rows: dict[str, HomeSection] = {}   # row key -> row of the home screen
        self._detail: MovieDialog | None = None
        self._player: VlcPlayerPage | None = None
        self._player_origin: QWidget | None = None
        self._playing_id: int | None = None   # movie/episode in the built-in player
        self._sliding = False
        self.setWindowTitle("CineLocal")
        self.resize(1380, 860)
        self.setMinimumSize(920, 600)

        self._sidebar_timer = QTimer(self, singleShot=True, interval=350)
        self._sidebar_timer.timeout.connect(self._rebuild_sidebar)
        self._home_timer = QTimer(self, singleShot=True, interval=300)   # batches several changes in a row
        self._home_timer.timeout.connect(self._refresh_home)

        self._build_ui()
        self._connect()

    # ------------------------------------------------------------------ construction --
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
        subtitle = QLabel("Your personal movie library, fast and offline.\n"
                          "Choose the folder where your movies are to get started.")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignCenter)
        choose = QPushButton("Select movies folder")
        choose.setProperty("primary", True)
        choose.setMinimumHeight(46)
        choose.setMinimumWidth(280)
        choose.clicked.connect(self._choose_folder)
        key = QPushButton("Set up TMDB key")
        key.clicked.connect(lambda: self.open_settings(focus_key=True))
        note = QLabel("Your files are never modified. The internet is only used to download\n"
                      "posters and info for new movies.")
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
        self.search.setPlaceholderText("Search by title, actor, director or genre…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.advanced_btn = IconButton("search_advanced", box=TOOL_BOX, size=TOOL_ICON)
        self.advanced_btn.setToolTip("Advanced search")
        self.advanced_btn.setCheckable(True)   # lit while advanced filters are active
        self.sort_combo = QComboBox()
        for sort_id, label, *_ in filters.SORT_OPTIONS:
            self.sort_combo.addItem(label, sort_id)
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(self.sort_id)))
        rescan = IconButton("refresh", box=TOOL_BOX, size=TOOL_ICON)
        rescan.setToolTip("Rescan")
        rescan.clicked.connect(self.service.start_scan)
        self.service.scanning.connect(rescan.set_spinning)   # spins while scanning (also F5 / startup)
        meta = IconButton("big_data", box=TOOL_BOX, size=TOOL_ICON)
        meta.setToolTip("Metadata and library tools")
        meta_menu = QMenu(meta)
        meta_menu.addAction("Fetch metadata for pending movies",
                            lambda: self.service.start_update("pending"))
        meta_menu.addAction("Force update of all movies", self._confirm_update_all)
        meta_menu.addSeparator()
        meta_menu.addAction("Review unmatched movies…", self.review_all)
        meta_menu.addAction("Create franchise collections", self._link_franchises)
        meta_menu.addSeparator()
        meta_menu.addAction("Find duplicate files…", lambda: DuplicatesDialog(self.service, self).exec())
        meta_menu.addAction("Statistics…", lambda: StatsDialog(self.service, self).exec())
        meta.setMenu(meta_menu)
        settings = IconButton("gear", box=TOOL_BOX, size=TOOL_ICON)
        settings.setToolTip("Settings (Ctrl+,)")
        settings.clicked.connect(lambda: self.open_settings())
        bar.addWidget(self.search, 1)
        bar.addWidget(self.advanced_btn)
        bar.addWidget(QLabel("Sort:"))
        bar.addWidget(self.sort_combo)
        bar.addWidget(rescan)
        bar.addWidget(meta)
        bar.addWidget(settings)
        column.addLayout(bar)

        self.infobar = QFrame()
        self.infobar.setObjectName("infobar")
        info_row = QHBoxLayout(self.infobar)
        info_row.setContentsMargins(16, 10, 10, 10)
        info_row.addWidget(QLabel("To download posters and info, set up your free TMDB key."), 1)
        info_btn = QPushButton("Set up")
        info_btn.clicked.connect(lambda: self.open_settings(focus_key=True))
        info_row.addWidget(info_btn)
        column.addWidget(self.infobar)

        self.filterbar = QFrame()   # shown while an advanced search is active
        self.filterbar.setObjectName("infobar")
        filter_row = QHBoxLayout(self.filterbar)
        filter_row.setContentsMargins(16, 6, 10, 6)
        self.filter_label = QLabel("")
        filter_row.addWidget(self.filter_label, 1)
        clear_btn = QPushButton("Clear search")
        clear_btn.clicked.connect(self._clear_search)
        filter_row.addWidget(clear_btn)
        self.filterbar.hide()
        column.addWidget(self.filterbar)

        self.head_bar = QWidget()   # moves below the home rows (see _place_heading)
        head = QHBoxLayout(self.head_bar)
        head.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel("All movies")
        self.heading.setObjectName("heading")
        self.manage_btn = QPushButton("+")
        self.manage_btn.setFixedSize(34, 34)
        self.manage_btn.setStyleSheet("QPushButton { padding: 0; font-size: 18pt; font-weight: 700; }")
        self.manage_btn.setToolTip("Manage movies in this section")
        self.manage_btn.clicked.connect(lambda: self._manage_sidebar_items(self.flt))
        self.manage_btn.hide()
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        head.addWidget(self.heading)
        head.addWidget(self.manage_btn)
        head.addSpacing(12)
        head.addWidget(self.count_label, 0, Qt.AlignBottom)
        head.addStretch(1)
        self.head_top = QVBoxLayout()
        self.head_top.addWidget(self.head_bar)
        column.addLayout(self.head_top)

        self.views = QStackedWidget()
        self.grid = MovieFlow()
        self.home_box = QVBoxLayout()   # rows chosen in "Edit home"; only in "All movies", if they have items
        self.home_box.setSpacing(10)
        self.grid_page = QScrollArea()   # scrolls the "Continue watching" row together with the grid
        self.grid_page.setWidgetResizable(True)
        self.grid_page.setFrameShape(QFrame.NoFrame)
        self.grid_page.verticalScrollBar().setSingleStep(48)
        self.grid_content = QWidget()
        self.grid_page.setWidget(self.grid_content)
        grid_col = QVBoxLayout(self.grid_content)
        grid_col.setContentsMargins(0, 0, 0, 0)
        grid_col.setSpacing(10)
        grid_col.addLayout(self.home_box)
        self.head_inline = QVBoxLayout()   # heading between the home rows and the grid
        grid_col.addLayout(self.head_inline)
        grid_col.addWidget(self.grid)
        grid_col.addStretch(1)
        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.views.addWidget(self.grid_page)
        self.views.addWidget(self.empty)
        column.addWidget(self.views, 1)
        return page

    def _build_status_bar(self) -> None:
        self.progress_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setTextVisible(False)
        self.cancel_btn = QPushButton("Cancel")
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
        self.sidebar.edit_tag_requested.connect(self._edit_tag)
        self.sidebar.delete_tag_requested.connect(self._delete_tag)
        self.search.textChanged.connect(self._on_search)
        self.advanced_btn.clicked.connect(self._open_advanced)
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        self.grid.movie_opened.connect(self._open_from_grid)
        self.grid.context_requested.connect(self._context_menu)
        self.grid.itemDelegate().progress_of = s.progress_of
        self.grid.selectionModel().currentChanged.connect(self._reveal_current)

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
        QShortcut(QKeySequence("Esc"), self.search, activated=self.search.clear,
                  context=Qt.WidgetShortcut)   # only while typing in the search (Esc also closes the overlay)

    # ---------------------------------------------------------------------- start --
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
        path = QFileDialog.getExistingDirectory(self, "Select movies folder", os.path.expanduser("~"))
        if not path:
            return
        self.service.settings.update(library_path=path)
        self.stack.setCurrentIndex(1)
        self._update_infobar()
        if not self.service.has_key:
            self.open_settings(
                focus_key=True,
                intro="To download posters and movie info, paste your free TMDB key.\n"
                      "You can skip this step and set it up later.")
        self.service.start_scan()

    # ------------------------------------------------------------------ view --
    def _home_keys(self) -> list[str]:
        """Rows chosen for the home screen, in order (collections that no longer exist are dropped)."""
        known = {"continue", "history", "favorites", "watchlist"}
        known |= {f"collection:{c['id']}" for c in self.service.collections}
        return [k for k in self.service.settings.get("home_sections") or [] if k in known]

    def _home_items(self, key: str) -> list[dict]:
        s = self.service
        if key == "continue":
            items = filters.filter_movies(s.movies, ("continue", None), s.membership, "", s.progress_of)
            return sorted(items, key=lambda m: -s.last_played(m))   # the one you watched last comes first
        if key == "history":
            items = filters.filter_movies(s.movies, ("history", None), s.membership, "", None, None, s.history_stamp)
            return sorted(items, key=lambda m: -s.history_stamp(m))
        flt = (key, None) if key in ("favorites", "watchlist") else ("collection", int(key.split(":")[1]))
        return filters.sort_movies(filters.filter_movies(s.movies, flt, s.membership), self.sort_id)

    def _new_home_row(self, key: str) -> HomeSection:
        section = HomeSection("")
        section.row.itemDelegate().progress_of = self.service.progress_of
        section.row.movie_opened.connect(self.open_movie)
        section.row.context_requested.connect(self._context_menu)
        self._home_rows[key] = section
        return section

    def _refresh_home(self) -> None:
        """Rows above \"All movies\", as chosen in \"Edit home\"; hidden outside that screen."""
        on_home = self.flt[0] == "all" and not self.query and not self.advanced
        keys = self._home_keys() if on_home else []
        for key in [k for k in self._home_rows if k not in keys]:
            section = self._home_rows.pop(key)
            self.home_box.removeWidget(section)
            section.deleteLater()
        titles = {"continue": "Continue watching", "history": "History", "favorites": "Favorites",
                  "watchlist": "Watchlist"}
        for position, key in enumerate(keys):
            section = self._home_rows.get(key) or self._new_home_row(key)
            self.home_box.removeWidget(section)
            self.home_box.insertWidget(position, section)   # keeps the order chosen by the user
            items = self._home_items(key)
            row = section.row
            bar = row.horizontalScrollBar()
            scroll = bar.value()
            row.movie_model.set_movies(items[:HOME_ROW_LIMIT])
            QTimer.singleShot(0, lambda b=bar, v=scroll: b.setValue(v))   # the layout only finishes later
            section.title.setText(titles.get(key) or self.service.collection_name(int(key.split(":")[1])))
            section.count.setText(str(len(items)))
            section.setVisible(bool(items))
        self._place_heading()

    def _place_heading(self) -> None:
        """\"All movies\" goes right above the grid: below the home rows when they are shown."""
        inline = any(not section.isHidden() for section in self._home_rows.values())
        target, other = (self.head_inline, self.head_top) if inline else (self.head_top, self.head_inline)
        if target.indexOf(self.head_bar) < 0:
            other.removeWidget(self.head_bar)
            target.addWidget(self.head_bar)

    def _edit_home(self) -> None:
        dialog = HomeDialog(self.service, self._home_keys(), self)
        if dialog.exec():
            self.service.settings.update(home_sections=dialog.keys())
            self._refresh_home()

    def _reveal_current(self, index) -> None:
        """Keyboard navigation: scrolls the page to the current movie."""
        if index.isValid():
            center = self.grid.viewport().mapTo(self.grid_content, self.grid.visualRect(index).center())
            self.grid_page.ensureVisible(center.x(), center.y(), 0, CELL_H // 2)

    def refresh_view(self) -> None:
        self._refresh_home()
        bar = self.grid_page.verticalScrollBar()
        position = bar.value()
        visible = filters.filter_movies(self.service.movies, self.flt, self.service.membership,
                                        self.query, self.service.progress_of, self.advanced,
                                        self.service.history_stamp)
        visible = filters.sort_movies(visible, self.sort_id)
        if self.flt[0] == "continue":   # the one you watched last comes first
            visible.sort(key=lambda m: -self.service.last_played(m))
        elif self.flt[0] == "history":   # most recently watched first
            visible.sort(key=lambda m: -self.service.history_stamp(m))
        shown = visible
        if self.flt == ("all", None) and not self.query and not self.advanced:   # only in "All movies"
            group_ids = list(self.service.settings.get("grouped_collections") or [])
            if self.service.settings.get("group_auto_collections"):
                group_ids += filters.automatic_collections(self.service.movies, self.service.collections)
            shown = filters.group_collections(visible, self.service.membership, group_ids,
                                              self.service.collection_name)
        self.grid.movie_model.set_movies(shown)
        bar.setValue(position)
        QTimer.singleShot(0, lambda: bar.setValue(position))   # the layout only finishes later

        total = len(self.service.movies)
        kind = self.flt[0]
        self.heading.setText(self._heading_text())
        can_manage = kind in ("favorites", "watchlist", "watched", "collection", "tag")
        self.manage_btn.setVisible(can_manage)
        if can_manage:
            self.manage_btn.setToolTip(f"Manage movies in {self._heading_for_filter(self.flt)}")
        self.count_label.setText(f"{len(visible)} of {total}" if len(visible) != total
                                 else f"{total} movie{'' if total == 1 else 's'}")
        self.filterbar.setVisible(bool(self.advanced))
        self.filter_label.setText(f"Advanced search: {len(visible)} of {total}")
        if visible:
            self.views.setCurrentWidget(self.grid_page)
        else:
            self.empty.setText(self._empty_text(total))
            self.views.setCurrentWidget(self.empty)

    def _empty_text(self, total: int) -> str:
        if self.query or self.advanced:
            return "No movies match your search."
        if total == 0:
            return "No movies found in the selected folder.\nUse the Settings button to choose another folder."
        return "No movies in this section."

    def _heading_text(self) -> str:
        kind, value = self.flt
        names = {"all": "All movies", "favorites": "Favorites", "watchlist": "Watchlist",
                 "review": "Needs review", "continue": "Continue watching", "history": "History"}
        if kind in names:
            return names[kind]
        if kind == "watched":
            return "Watched" if value else "Unwatched"
        if kind == "collection":
            return self.service.collection_name(value)
        if kind == "tag":
            return next((tag["name"] for tag in self.service.tags if tag["id"] == value), "Tag")
        if kind == "decade":
            return f"{value}s"
        if kind == "stars":
            return f"My rating: {star_text(value)}"
        return str(value)

    def _rebuild_sidebar(self) -> None:
        counts = filters.sidebar_counts(self.service.movies, self.service.progress_of, self.service.history_stamp)
        self.sidebar.rebuild(counts, self.service.collections, self.service.membership, self.flt,
                             self.service.tags, self.service.tag_membership)
        if self.sidebar.current_filter != self.flt:   # the previous selection no longer exists
            self.flt = self.sidebar.current_filter
            self.refresh_view()

    def _update_infobar(self) -> None:
        self.infobar.setVisible(not self.service.has_key)

    # ---------------------------------------------------------------------- events --
    def _on_filter(self, flt) -> None:
        self.flt = flt
        self.refresh_view()

    def _manage_sidebar_items(self, flt: filters.Filter) -> None:
        kind, value = flt
        if kind in ("favorites", "watchlist", "watched"):
            movies = self.service.movies
            if kind == "watched":
                selected = {m["id"] for m in movies if m["watched"] == value}
            else:
                selected = {m["id"] for m in movies if m[kind]}
        elif kind == "collection":
            movies = [m for m in self.service.movies if m.get("kind") == "movie"]
            selected = set(self.service.membership.get(value, ()))
        elif kind == "tag":
            movies = [m for m in self.service.movies if m.get("kind") == "movie"]
            selected = {movie_id for movie_id, tag_ids in self.service.tag_membership.items()
                        if value in tag_ids}
        else:
            return

        selected.intersection_update(m["id"] for m in movies)
        dialog = MovieSelectionDialog(movies, selected, f"Manage {self._heading_for_filter(flt)}", self)
        if not dialog.exec():
            return
        updated = dialog.selected_ids()
        added, removed = updated - selected, selected - updated
        if kind in ("favorites", "watchlist"):
            self.service.set_flag(sorted(added), kind, True)
            self.service.set_flag(sorted(removed), kind, False)
        elif kind == "watched":
            self.service.set_flag(sorted(added), "watched", value)
            self.service.set_flag(sorted(removed), "watched", not value)
        elif kind == "collection":
            self.service.set_in_collection(value, sorted(added), True)
            self.service.set_in_collection(value, sorted(removed), False)
        else:
            self.service.set_movie_tags(sorted(added), value, True)
            self.service.set_movie_tags(sorted(removed), value, False)

    def _heading_for_filter(self, flt: filters.Filter) -> str:
        kind, value = flt
        if kind == "watched":
            return "Watched" if value else "Unwatched"
        if kind == "collection":
            return self.service.collection_name(value)
        if kind == "tag":
            return next((tag["name"] for tag in self.service.tags if tag["id"] == value), "Tag")
        return {"favorites": "Favorites", "watchlist": "Watchlist"}[kind]

    def _on_search(self, text: str) -> None:
        self.query = text
        self.refresh_view()

    def _open_advanced(self) -> None:
        s = self.service
        self.advanced_btn.setChecked(bool(self.advanced))   # the click toggled it; it only shows the filter state
        overlay = AdvancedSearch(
            s, self.stack.widget(1), self.advanced,
            lambda adv: len(filters.filter_movies(s.movies, self.flt, s.membership, self.query,
                                                  s.progress_of, adv, s.history_stamp)))
        overlay.applied.connect(self._on_advanced)

    def _clear_search(self) -> None:
        """Back to the whole catalog: no advanced filters, no text search, section \"All\"."""
        self.advanced = {}
        self.advanced_btn.setChecked(False)
        self.flt = ("all", None)
        self.search.clear()
        self._rebuild_sidebar()
        self.refresh_view()

    def _on_advanced(self, criteria: dict) -> None:
        self.advanced = criteria
        self.advanced_btn.setChecked(bool(criteria))
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
        for section in self._home_rows.values():
            section.row.movie_model.refresh_movie(movie_id)
        if self.flt[0] == "all" and not self.query and not self.advanced:
            self._home_timer.start()
        if self.flt[0] in ("favorites", "watchlist", "watched", "review", "stars") or self.advanced or (
                self.flt[0] in ("continue", "history") and self._player is None):
            self.refresh_view()   # the movie may have entered/left the current section
        self._sidebar_timer.start()

    def _on_progress(self, done: int, total: int, title: str) -> None:
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.progress_label.setText(f"Metadata {done}/{total}" + (f" — {title}" if title else ""))

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
            self.statusBar().showMessage(f"{added} new movie(s), {removed} removed.", 8000)

    def _on_update_finished(self, summary: dict) -> None:
        text = (f"Metadata: {summary['matched']} updated, "
                f"{summary['ambiguous'] + summary['not_found']} to review, {summary['failed']} failed.")
        if summary["cancelled"]:
            text += " (cancelled)"
        self.statusBar().showMessage(text, 12000)
        pending_review = summary["ambiguous"] + summary["not_found"]
        if pending_review and not summary["cancelled"]:
            QTimer.singleShot(400, lambda: self._offer_review(pending_review))

    # ---------------------------------------------------------------------- actions --
    def _open_from_grid(self, movie_id: int) -> None:
        collection_id = filters.group_of(movie_id)
        if collection_id is None:
            self.open_movie(movie_id)
        else:   # a grouped collection: enter it
            self._open_filter(("collection", collection_id))

    def open_movie(self, movie_id: int) -> None:
        if self._sliding:
            return
        previous, self._detail = self._detail, None   # opened from a similar movie: it leaves after the slide
        page = (SeriesDialog if movie_id < 0 else MovieDialog)(self.service, movie_id, self)
        page.back_requested.connect(self.close_movie)
        page.play_requested.connect(self.play_movie)
        if isinstance(page, MovieDialog):
            page.open_requested.connect(self.open_movie)
            page.filter_tag_requested.connect(self._open_tag)
        self._detail = page
        self.stack.addWidget(page)

        def drop_previous() -> None:
            self.stack.removeWidget(previous)
            previous.deleteLater()

        self._slide_to(page, forward=True, done=drop_previous if previous is not None else None)

    def close_movie(self) -> None:
        if self._sliding or self._detail is None or self.stack.currentWidget() is not self._detail:
            return

        def done() -> None:
            self._discard_detail()
            self.grid.setFocus()

        self._slide_to(self.stack.widget(1), forward=False, done=done)

    def _use_external(self) -> bool:
        s = self.service.settings
        choice = s.get("default_player") or ("external" if s.get("player_command").strip() else "builtin")
        return choice == "external"

    def play_movie(self, movie_id: int, external: bool | None = None) -> None:
        """Plays in the default player: the built-in one (VLC) or the external one (configured command
        or system default). `external` forces one of the two; without libVLC, uses the external one."""
        if self._sliding:
            return
        if external is None:
            external = self._use_external()
        self._discard_player()
        if movie_id < 0:   # series: plays the next episode to watch
            movie_id = self.service.next_episode(-movie_id)
            if movie_id is None:
                self.statusBar().showMessage("This series has no episodes.", 5000)
                return
        movie = self.service.by_id[movie_id]
        if external or not os.path.exists(movie["path"]):
            return self._play(movie_id)
        reason = unavailable_reason()
        if reason:
            self.statusBar().showMessage(reason + " Using the system player.", 10000)
            return self._play(movie_id)
        self._playing_id = movie_id
        page = VlcPlayerPage(self._movie_title(movie), self)
        page.back_requested.connect(self.close_player)
        page.progress.connect(self.service.save_progress)
        page.finished.connect(self.service.mark_finished)
        page.ended.connect(lambda path: QTimer.singleShot(0, lambda: self._offer_next(path)))
        page.prefs_changed.connect(lambda prefs: self.service.settings.update(player_prefs=prefs))
        page.apply_prefs(self.service.settings.get("player_prefs") or {})
        page.set_track_languages(self.service.settings.get("audio_language"),
                                 self.service.settings.get("subtitle_language"))
        page.set_saved_tracks((self.service.settings.get("track_choices") or {}).get(movie["path"], {}))
        page.tracks_remembered.connect(self.service.remember_tracks)
        page.subtitle_search_requested.connect(
            lambda path, language: self.service.search_subtitle(
                path, lambda saved: self._player is page and page.add_subtitle(saved), language))
        page.external_requested.connect(lambda: self._open_external(self._playing_id))
        page.next_requested.connect(self._play_next)
        page.set_has_next(self._has_next(movie))
        self._player, self._player_origin = page, self.stack.currentWidget()
        self.stack.addWidget(page)
        resume = self.service.resume_info(movie["path"])[0]
        self._slide_to(page, forward=True, done=lambda: page.start(movie["path"], resume))

    def _movie_title(self, movie: dict) -> str:
        title = movie["display_title"]
        if movie.get("kind") == "episode":
            series = self.service.by_id.get(-movie["series_id"])
            title = (f"{series['display_title'] if series else movie['clean_title']}"
                     f" — S{movie['season']}E{movie['episode']} — {title}")
        return title

    def _offer_next(self, path: str) -> None:
        """An episode ended: offers the next one, playing in the same player."""
        movie = self.service.by_path(path)
        if self._player is None or movie is None or movie.get("kind") != "episode":
            return
        nxt = self.service.episode_after(movie)
        if nxt is None:
            return
        ask = QMessageBox.question(
            self, "Next episode",
            f"Watch the next episode?\n\nS{nxt['season']}E{nxt['episode']} — {nxt['display_title']}")
        if ask == QMessageBox.Yes and self._player is not None:
            self._start_episode(nxt)

    def _has_next(self, movie: dict) -> bool:
        return movie.get("kind") == "episode" and self.service.episode_after(movie) is not None

    def _play_next(self) -> None:
        """'Next' button of the player: skips to the next episode of the series."""
        movie = self.service.by_id.get(self._playing_id)
        nxt = self.service.episode_after(movie) if movie else None
        if nxt is not None and self._player is not None:
            self._start_episode(nxt)

    def _start_episode(self, nxt: dict) -> None:
        if not os.path.exists(nxt["path"]):
            self.statusBar().showMessage("The next episode's file was not found.", 6000)
            return
        self._playing_id = nxt["id"]
        self._player.set_title(self._movie_title(nxt))
        self._player.set_has_next(self._has_next(nxt))
        self._player.start(nxt["path"], self.service.resume_info(nxt["path"])[0])

    def _play_from_start(self, movie_id: int) -> None:
        self.service.restart(self.service.by_id[movie_id])
        self.play_movie(movie_id)

    def _open_external(self, movie_id: int) -> None:
        """Closes the built-in player (saving the position) and opens the movie in the external player."""
        self.close_player()
        self._play(movie_id)

    def close_player(self) -> None:
        if self._sliding or self._player is None or self.stack.currentWidget() is not self._player:
            return
        self._player.leave()
        self._slide_to(self._player_origin, forward=False, done=self._discard_player)

    def _discard_player(self) -> None:
        if self._player is not None:
            self.stack.removeWidget(self._player)
            self._player.release()
            self._player.deleteLater()
            self._player = self._player_origin = None
            self.grid.viewport().update()   # progress bars
            if self.flt[0] in ("continue", "history", "all"):
                self.refresh_view()

    def _discard_detail(self) -> None:
        if self._detail is not None:
            self.stack.removeWidget(self._detail)
            self._detail.deleteLater()
            self._detail = None

    def _slide_to(self, target: QWidget, forward: bool, done=None) -> None:
        """Switches the `stack` page by sliding sideways (the list stays alive underneath,
        so scrolling, search, filter and selection are preserved)."""
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
        old = {k: s.get(k) for k in ("library_path", "tmdb_api_key", "language", "grouped_collections",
                                                        "group_auto_collections")}
        had_key = self.service.has_key
        dialog = SettingsDialog(self.service, self, intro=intro, focus_key=focus_key)
        dialog.edit_home_requested.connect(self._edit_home)
        dialog.exec()
        if dialog.restored:
            self._discard_detail()
            self._update_infobar()
            self.stack.setCurrentIndex(1 if s.get("library_path") else 0)
            return
        if not dialog.saved:
            return
        s.update(**dialog.values())
        if any(old[k] != s.get(k) for k in ("grouped_collections", "group_auto_collections")):
            self.refresh_view()
        self._update_infobar()
        if not s.get("library_path"):
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)

        language_changed = old["language"] != s.get("language") and bool(self.service.movies)
        if old["library_path"] != s.get("library_path") or (not had_key and self.service.has_key):
            self.service.start_scan()
        if language_changed:
            answer = QMessageBox.question(
                self, "Language changed",
                "Update the metadata of all movies to the new language now?\n"
                "(This uses the internet. New movies will already use the new language.)")
            if answer == QMessageBox.Yes:
                self.service.start_update("all")

    def _link_franchises(self) -> None:
        if not self.service.link_franchises():
            self.statusBar().showMessage("No new franchises found. Force an update to detect the franchise of "
                                         "movies that already have metadata.", 10000)

    def _confirm_update_all(self) -> None:
        answer = QMessageBox.question(
            self, "Update metadata",
            "Download the metadata of all movies again?\n"
            "Matches that were already confirmed are kept.")
        if answer == QMessageBox.Yes:
            self.service.start_update("all")

    def _offer_review(self, count: int) -> None:
        answer = QMessageBox.question(
            self, "Review needed",
            f"{count} movie(s) could not be identified with confidence.\nReview now?")
        if answer == QMessageBox.Yes:
            self.review_all()

    def review_all(self) -> None:
        ids = [m["id"] for m in self.service.movies if m["status"] in ("ambiguous", "not_found")]
        if not ids:
            self.statusBar().showMessage("No movies need review.", 5000)
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

    def _edit_tag(self, tag_id: int) -> None:
        TagDialog(self.service, tag_id, self).exec()

    def _delete_tag(self, tag_id: int) -> None:
        name = self._heading_for_filter(("tag", tag_id))
        answer = QMessageBox.question(
            self, "Delete tag",
            f"Delete the tag “{name}”?\nThe movies will not be deleted, only lose the tag.")
        if answer == QMessageBox.Yes:
            self.service.delete_tag(tag_id)

    def _open_tag(self, tag_id: int) -> None:
        self._open_filter(("tag", tag_id))

    def _open_filter(self, flt: filters.Filter) -> None:
        if self._detail is not None:
            self.close_movie()
        self.flt = flt
        self.advanced = {}
        self.advanced_btn.setChecked(False)
        self.query = ""
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._rebuild_sidebar()
        self.grid_page.verticalScrollBar().setValue(0)
        self.refresh_view()

    def _context_menu(self, ids: list[int], global_pos) -> None:
        s = self.service
        movies = [s.by_id[i] for i in ids if i in s.by_id]
        if not movies:
            return
        single = len(movies) == 1
        menu = QMenu(self)
        if single:
            menu.addAction("Open details", lambda: self.open_movie(ids[0]))
            menu.addAction("Watch", lambda: self.play_movie(ids[0]))
            other = "built-in player" if self._use_external() else "another player"
            menu.addAction(f"Watch in {other}",
                           lambda: self.play_movie(ids[0], external=not self._use_external()))
            if s.progress_of(movies[0]) > 0:
                menu.addAction("Watch from the beginning", lambda: self._play_from_start(ids[0]))
            menu.addSeparator()

        all_fav = all(m["favorite"] for m in movies)
        all_seen = all(m["watched"] for m in movies)
        menu.addAction("Remove from favorites" if all_fav else "Add to favorites",
                       lambda: s.set_flag(ids, "favorite", not all_fav))
        menu.addAction("Mark as unwatched" if all_seen else "Mark as watched",
                       lambda: s.set_flag(ids, "watched", not all_seen))
        all_listed = all(m["watchlist"] for m in movies)
        menu.addAction("Remove from Watchlist" if all_listed else "Add to Watchlist",
                       lambda: s.set_flag(ids, "watchlist", not all_listed))
        if all(i > 0 for i in ids):   # collections only hold movies
            collections_menu = menu.addMenu("Collections")
            populate_collections_menu(collections_menu, s, ids, self)
            tags_menu = menu.addMenu("Tags")
            for tag in s.tags:
                action = tags_menu.addAction(tag["name"])
                action.setCheckable(True)
                action.setChecked(all(tag["id"] in s.tag_membership.get(movie_id, set()) for movie_id in ids))
                action.triggered.connect(
                    lambda checked, tag_id=tag["id"]: s.set_movie_tags(ids, tag_id, checked))
            tags_menu.addSeparator()
            tags_menu.addAction("Create tag…", lambda: self._create_tag_for(ids))
        if self.flt[0] == "collection":
            menu.addAction("Remove from this collection",
                           lambda: s.set_in_collection(self.flt[1], ids, False))
        menu.addSeparator()
        menu.addAction("Update metadata", lambda: self._refresh_ids(ids))
        if single:
            menu.addAction("Fix match…", lambda: self._fix_match(ids[0]))
        menu.exec(global_pos)

    def _create_tag_for(self, movie_ids: list[int]) -> None:
        name, accepted = QInputDialog.getText(self, "Create tag", "Tag name:")
        if not accepted or not name.strip():
            return
        try:
            tag_id = self.service.create_tag(name)
            self.service.set_movie_tags(movie_ids, tag_id, True)
        except ValueError as exc:
            QMessageBox.warning(self, "Could not create tag", str(exc))

    def _play(self, movie_id: int) -> None:
        try:
            self.service.play(movie_id)
        except OSError as exc:
            QMessageBox.warning(self, "Could not open", str(exc))

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
        self._discard_player()
        self.service.shutdown()
        super().closeEvent(event)
