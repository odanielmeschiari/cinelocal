"""Advanced search: an overlay on top of the library with every filter available in the local data."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import filters
from ..service import LibraryService
from ..utils import normalize_text, star_text

_KEY, _SEARCH = Qt.UserRole, Qt.UserRole + 1


class CheckList(QWidget):
    """Searchable list of choices with check boxes (the search box only shows up on long lists)."""
    changed = Signal()

    def __init__(self, items: list[tuple], empty_hint: str = "", parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.box = QLineEdit()
        self.box.setPlaceholderText("Filter the list…")
        self.box.setClearButtonEnabled(True)
        self.box.setVisible(len(items) > 8)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setFixedHeight(150)
        self.list.setStyleSheet(
            "QListWidget::item { padding: 3px 6px; }"
            "QListWidget::indicator { width: 14px; height: 14px; border-radius: 4px;"
            " border: 1px solid #1f2b40; background: #131a26; }"
            "QListWidget::indicator:checked { background: #2f80ff; border-color: #2f80ff; }")
        for key, text in items:   # no ItemIsUserCheckable: itemClicked toggles, so the whole row is clickable
            item = QListWidgetItem(text)
            item.setData(_KEY, key)
            item.setData(_SEARCH, normalize_text(text))
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)
        self.hint = QLabel(empty_hint)
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.hint.setVisible(not items and bool(empty_hint))
        self.list.setVisible(bool(items))
        for w in (self.box, self.list, self.hint):
            column.addWidget(w)
        self.box.textChanged.connect(self._filter)
        self.list.itemClicked.connect(self._toggle)

    def _filter(self, text: str) -> None:
        terms = normalize_text(text).split()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(not all(t in item.data(_SEARCH) for t in terms))

    def _toggle(self, item: QListWidgetItem) -> None:
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self.changed.emit()

    def checked(self) -> list:
        items = (self.list.item(i) for i in range(self.list.count()))
        return [item.data(_KEY) for item in items if item.checkState() == Qt.Checked]

    def set_checked(self, keys) -> None:
        keys = set(keys)
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setCheckState(Qt.Checked if item.data(_KEY) in keys else Qt.Unchecked)


def _spin(low: int, high: int, special: str = "Any", suffix: str = "", step: int = 1) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setSpecialValueText(special)   # shown at the minimum value, which means "no limit"
    spin.setSuffix(suffix)
    spin.setSingleStep(step)
    spin.setGroupSeparatorShown(True)
    spin.setMinimumWidth(110)
    return spin


def _row(*widgets) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    for w in widgets:
        row.addWidget(QLabel(w) if isinstance(w, str) else w)
    row.addStretch(1)
    return row


class AdvancedSearch(QWidget):
    """Covers the library page. `current` is the active criteria; `count_for(criteria)` tells how many items
    would be shown; `applied(criteria)` is emitted by Apply (an empty dict removes the advanced filter)."""
    applied = Signal(dict)

    def __init__(self, service: LibraryService, parent: QWidget, current: dict, count_for):
        super().__init__(parent)
        self.service, self._count_for, self._loading = service, count_for, True
        self.setObjectName("scrim")
        self.setAttribute(Qt.WA_StyledBackground, True)
        parent.installEventFilter(self)   # follows the size of the page
        options = filters.advanced_options(service.movies)
        self._build(options)
        self._refresh_saved()
        self.load(current)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.setFocus()

    # ------------------------------------------------------------------ construction --
    def _build(self, options: dict) -> None:
        scrim = QHBoxLayout(self)
        scrim.setContentsMargins(30, 30, 30, 30)
        self.panel = QFrame()
        self.panel.setObjectName("overlayPanel")
        self.panel.setMaximumWidth(900)
        scrim.addStretch(1)
        scrim.addWidget(self.panel, 100)
        scrim.addStretch(1)
        outer = QVBoxLayout(self.panel)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Advanced search")
        title.setObjectName("heading")
        self.saved = QComboBox()
        self.saved.setMinimumWidth(200)
        self.save_btn = QPushButton("Save…")
        self.delete_btn = QPushButton("Delete")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.saved)
        head.addWidget(self.save_btn)
        head.addWidget(self.delete_btn)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 14, 0)
        form.setSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        def section(text: str) -> None:
            label = QLabel(text.upper())
            label.setObjectName("section")
            form.addSpacing(6)
            form.addWidget(label)

        def pair(*columns: tuple[str, QWidget]) -> None:   # side-by-side lists, each with its caption
            grid = QGridLayout()
            grid.setHorizontalSpacing(18)
            for col, (caption, widget) in enumerate(columns):
                grid.addWidget(QLabel(caption), 0, col)
                grid.addWidget(widget, 1, col, Qt.AlignTop)
                grid.setColumnStretch(col, 1)
            form.addLayout(grid)

        def named(pairs):
            return [(name, f"{name}  ({count})") for name, count in pairs]

        # -- content --
        section("Content")
        self.kind = QComboBox()
        for label, value in (("Movies and series", None), ("Movies only", "movie"), ("Series only", "series")):
            self.kind.addItem(label, value)
        self.runtime_min = _spin(0, 600, suffix=" min", step=5)
        self.runtime_max = _spin(0, 600, suffix=" min", step=5)
        form.addLayout(_row("Type", self.kind, "   Runtime (series: per episode)  from",
                            self.runtime_min, "to", self.runtime_max))

        # -- release year, ratings --
        section("Release and ratings")
        low, high = options["years"] or (1900, 2100)
        self.year_mode = QComboBox()
        self.year_mode.addItem("Between", "between")
        self.year_mode.addItem("Only in", "exact")
        self.year_from = _spin(low - 1, max(high, low), step=1)
        self.year_from.setGroupSeparatorShown(False)
        self.year_to = _spin(low - 1, max(high, low), step=1)
        self.year_to.setGroupSeparatorShown(False)
        self.year_and = QLabel("and")
        form.addLayout(_row("Year", self.year_mode, self.year_from, self.year_and, self.year_to))
        self.rating_min = QDoubleSpinBox()
        self.rating_max = QDoubleSpinBox()
        for spin in (self.rating_min, self.rating_max):
            spin.setRange(0, 10)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setMinimumWidth(110)
        self.rating_min.setSpecialValueText("Any")
        self.rating_max.setValue(10)
        form.addLayout(_row("TMDB rating from", self.rating_min, "to", self.rating_max))
        self.votes_min = _spin(0, 100_000_000, step=100)
        self.votes_max = _spin(0, 100_000_000, step=1000)
        form.addLayout(_row("TMDB votes from", self.votes_min, "to", self.votes_max))

        # -- genre and age rating --
        section("Genre and age rating")
        self.genres = CheckList(named(options["genres"]))
        self.genres_all = QCheckBox("Must have all the selected genres")
        genres_box = QWidget()
        column = QVBoxLayout(genres_box)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.genres)
        column.addWidget(self.genres_all)
        self.certs = CheckList(named(options["certifications"]),
                               "No age ratings saved yet. Use “Force update of all movies” in the Metadata "
                               "menu to download them.")
        pair(("Genres", genres_box), ("Age rating", self.certs))

        # -- people --
        section("People")
        self.directors = CheckList(named(options["directors"]), "No directors saved yet.")
        self.cast = CheckList(named(options["cast"]), "No cast saved yet.")
        pair(("Directors / creators", self.directors), ("Cast", self.cast))

        # -- my library --
        section("My library")
        self.watched = QComboBox()
        for label, value in (("Watched or not", None), ("Watched", True), ("Unwatched", False)):
            self.watched.addItem(label, value)
        self.favorite = QCheckBox("Favorites")
        self.watchlist = QCheckBox("Watchlist")
        self.in_progress = QCheckBox("Continue watching")
        form.addLayout(_row(self.watched, self.favorite, self.watchlist, self.in_progress))
        self.added_days = _spin(0, 3650, suffix=" days", step=1)
        form.addLayout(_row("Added in the last", self.added_days))
        s = self.service
        self.collections = CheckList(
            [(c["id"], f"{c['name']}  ({len(s.membership.get(c['id'], ()))})") for c in s.collections],
            "You have not created any collections yet.")
        stars_box = QWidget()
        column = QVBoxLayout(stars_box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        self.stars = {}
        for value in (5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1, 0.5, 0):
            self.stars[value] = QCheckBox(star_text(value) if value else "Not rated")
            column.addWidget(self.stars[value])
        column.addStretch(1)
        pair(("My collections", self.collections), ("My rating", stars_box))

        # -- footer --
        foot = QHBoxLayout()
        clear = QPushButton("Clear all")
        cancel = QPushButton("Cancel")
        self.apply_btn = QPushButton("Show results")
        self.apply_btn.setProperty("primary", True)
        self.apply_btn.setMinimumWidth(170)
        foot.addWidget(clear)
        foot.addStretch(1)
        foot.addWidget(cancel)
        foot.addWidget(self.apply_btn)
        outer.addLayout(foot)

        clear.clicked.connect(lambda: self.load({}))
        cancel.clicked.connect(self.close_overlay)
        self.apply_btn.clicked.connect(self._apply)
        self.save_btn.clicked.connect(self._save)
        self.delete_btn.clicked.connect(self._delete)
        self.saved.activated.connect(self._load_saved)
        self.year_mode.currentIndexChanged.connect(self._sync_year)
        for w in (self.kind, self.year_mode, self.watched):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.runtime_min, self.runtime_max, self.year_from, self.year_to, self.votes_min,
                  self.votes_max, self.added_days, self.rating_min, self.rating_max):
            w.valueChanged.connect(self._changed)
        for w in (self.genres_all, self.favorite, self.watchlist, self.in_progress, *self.stars.values()):
            w.toggled.connect(self._changed)
        for w in (self.genres, self.certs, self.directors, self.cast, self.collections):
            w.changed.connect(self._changed)

    # ---------------------------------------------------------------------- criteria --
    def criteria(self) -> dict:
        c: dict = {}
        if self.kind.currentData():
            c["kind"] = self.kind.currentData()
        if self.genres.checked():
            c["genres"] = self.genres.checked()
            if self.genres_all.isChecked():
                c["genres_all"] = True
        year_low = self.year_from.value() if self.year_from.value() > self.year_from.minimum() else None
        year_high = self.year_to.value() if self.year_to.value() > self.year_to.minimum() else None
        if self.year_mode.currentData() == "exact":
            year_high = year_low
        if year_low is not None:
            c["year_min"] = year_low
        if year_high is not None:
            c["year_max"] = year_high
        if self.rating_min.value() > 0:
            c["rating_min"] = self.rating_min.value()
        if self.rating_max.value() < 10:
            c["rating_max"] = self.rating_max.value()
        for key, spin in (("votes_min", self.votes_min), ("votes_max", self.votes_max),
                          ("runtime_min", self.runtime_min), ("runtime_max", self.runtime_max),
                          ("added_days", self.added_days)):
            if spin.value():
                c[key] = spin.value()
        for key, widget in (("certifications", self.certs), ("directors", self.directors),
                            ("cast", self.cast), ("collections", self.collections)):
            if widget.checked():
                c[key] = widget.checked()
        if self.watched.currentData() is not None:
            c["watched"] = self.watched.currentData()
        for key, box in (("favorite", self.favorite), ("watchlist", self.watchlist),
                         ("in_progress", self.in_progress)):
            if box.isChecked():
                c[key] = True
        stars = [value for value, box in self.stars.items() if box.isChecked()]
        if stars:
            c["stars"] = stars
        return c

    def load(self, c: dict) -> None:
        self._loading = True
        self.kind.setCurrentIndex(max(0, self.kind.findData(c.get("kind"))))
        self.genres.set_checked(c.get("genres", ()))
        self.genres_all.setChecked(bool(c.get("genres_all")))
        exact = c.get("year_min") is not None and c.get("year_min") == c.get("year_max")
        self.year_mode.setCurrentIndex(1 if exact else 0)
        self.year_from.setValue(c.get("year_min") or self.year_from.minimum())
        self.year_to.setValue(c.get("year_max") or self.year_to.minimum())
        self.rating_min.setValue(c.get("rating_min", 0))
        self.rating_max.setValue(c.get("rating_max", 10))
        for key, spin in (("votes_min", self.votes_min), ("votes_max", self.votes_max),
                          ("runtime_min", self.runtime_min), ("runtime_max", self.runtime_max),
                          ("added_days", self.added_days)):
            spin.setValue(c.get(key, 0))
        for key, widget in (("certifications", self.certs), ("directors", self.directors),
                            ("cast", self.cast), ("collections", self.collections)):
            widget.set_checked(c.get(key, ()))
        self.watched.setCurrentIndex(max(0, self.watched.findData(c.get("watched"))))
        for key, box in (("favorite", self.favorite), ("watchlist", self.watchlist),
                         ("in_progress", self.in_progress)):
            box.setChecked(bool(c.get(key)))
        for value, box in self.stars.items():
            box.setChecked(value in c.get("stars", ()))
        self._loading = False
        self._sync_year()
        self._changed()

    def _sync_year(self) -> None:
        between = self.year_mode.currentData() == "between"
        self.year_and.setVisible(between)
        self.year_to.setVisible(between)
        self._changed()

    def _changed(self, *_) -> None:
        if self._loading:
            return
        self.apply_btn.setText(f"Show {self._count_for(self.criteria())} results")

    # ------------------------------------------------------------------ saved filters --
    def _stored(self) -> dict:
        return dict(self.service.settings.get("saved_filters") or {})

    def _refresh_saved(self, select: str | None = None) -> None:
        self.saved.clear()
        self.saved.addItem("Saved filters…", None)
        for name in sorted(self._stored(), key=str.casefold):
            self.saved.addItem(name, name)
        self.saved.setCurrentIndex(max(0, self.saved.findData(select)))
        self.delete_btn.setEnabled(self.saved.currentData() is not None)

    def _load_saved(self) -> None:
        name = self.saved.currentData()
        self.delete_btn.setEnabled(name is not None)
        if name is not None:
            self.load(self._stored().get(name, {}))

    def _save(self) -> None:
        criteria = self.criteria()
        if not criteria:
            QMessageBox.information(self, "Advanced search", "Choose at least one filter before saving.")
            return
        name, ok = QInputDialog.getText(self, "Save filters", "Name:", text=self.saved.currentData() or "")
        name = name.strip()
        if not ok or not name:
            return
        stored = self._stored()
        if name in stored and QMessageBox.question(
                self, "Save filters", f"Replace the saved filters “{name}”?") != QMessageBox.Yes:
            return
        stored[name] = criteria
        self.service.settings.update(saved_filters=stored)
        self._refresh_saved(name)

    def _delete(self) -> None:
        name = self.saved.currentData()
        if name is None or QMessageBox.question(
                self, "Delete filters", f"Delete the saved filters “{name}”?") != QMessageBox.Yes:
            return
        stored = self._stored()
        stored.pop(name, None)
        self.service.settings.update(saved_filters=stored)
        self._refresh_saved()

    # ---------------------------------------------------------------------- window --
    def _apply(self) -> None:
        self.applied.emit(self.criteria())
        self.close_overlay()

    def close_overlay(self) -> None:
        self.hide()
        self.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parentWidget() and event.type() == QEvent.Resize:
            self.setGeometry(obj.rect())
        return False

    def mousePressEvent(self, event) -> None:
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.close_overlay()   # click outside the panel

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)
