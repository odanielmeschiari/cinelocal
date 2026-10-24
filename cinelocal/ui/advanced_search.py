"""Advanced search: an overlay on top of the library with every filter available in the local data."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QLocale, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QIcon, QIntValidator, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .. import filters
from ..service import LibraryService
from ..utils import normalize_text, star_text
from .theme import COLORS

_KEY, _SEARCH, _ON = Qt.UserRole, Qt.UserRole + 1, Qt.UserRole + 2


_icons: dict[bool, QIcon] = {}


def check_icon(checked: bool) -> QIcon:
    """Empty box, or the same box with just a check mark (drawn, so it needs no image files)."""
    if checked not in _icons:
        size, ratio = 16, 2
        pixmap = QPixmap(size * ratio, size * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(COLORS["muted"]), 1.2))
        painter.drawRect(1, 1, size - 2, size - 2)
        if checked:
            painter.setPen(QPen(QColor(COLORS["accent_hover"]), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline([QPointF(3.8, 8.4), QPointF(6.9, 11.5), QPointF(12.4, 4.6)])
        painter.end()
        _icons[checked] = QIcon(pixmap)
    return _icons[checked]


class Check(QCheckBox):
    """Check box drawn as a check mark (the whole row, icon included, is clickable)."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("QCheckBox::indicator { width: 0; height: 0; margin: 0; border: none; background: transparent; }")
        self.setIconSize(QSize(16, 16))
        self.toggled.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self.setIcon(check_icon(self.isChecked()))


class NumberField(QWidget):
    """Number you can type, step with the up/down buttons (or arrow keys) or pick from a menu of presets.
    Empty means "no limit"."""
    changed = Signal()

    def __init__(self, presets=(), step=1, low=0, high=10**9, decimals=0, start=None, label=str, parent=None):
        super().__init__(parent)
        self._step, self._low, self._high, self._decimals = step, low, high, decimals
        self._start = start if start is not None else (presets[0] if presets else low)
        self.edit = QLineEdit()
        self.edit.setFixedWidth(84)
        if decimals:
            validator = QDoubleValidator(low, high, decimals)
            validator.setNotation(QDoubleValidator.StandardNotation)
        else:
            validator = QIntValidator(low, high)
        validator.setLocale(QLocale.c())   # always "." as the decimal separator and no thousands separator
        self.edit.setValidator(validator)
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(lambda _t: self.changed.emit())
        self.edit.editingFinished.connect(lambda: self.set_value(self._clamp(self.value())))

        arrows = QVBoxLayout()
        arrows.setSpacing(1)
        for kind, direction in ((Qt.UpArrow, 1), (Qt.DownArrow, -1)):
            button = QToolButton()
            button.setArrowType(kind)
            button.setAutoRepeat(True)
            button.setFixedSize(22, 15)
            button.setStyleSheet("QToolButton { padding: 0; }")
            button.clicked.connect(lambda _c=False, d=direction: self._step_by(d))
            arrows.addWidget(button)
        menu = QMenu(self)
        menu.addAction("Any", lambda: self.set_value(None))
        for value in presets:
            menu.addAction(label(value), lambda v=value: self.set_value(v))
        drop = QToolButton()
        drop.setArrowType(Qt.DownArrow)
        drop.setMenu(menu)
        drop.setPopupMode(QToolButton.InstantPopup)
        drop.setFixedSize(26, 31)
        drop.setToolTip("Preset values")
        drop.setStyleSheet("QToolButton { padding: 0; }")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        row.addWidget(self.edit)
        row.addLayout(arrows)
        row.addWidget(drop)

    def value(self):
        try:
            return float(self.edit.text()) if self._decimals else int(self.edit.text())
        except ValueError:
            return None

    def set_value(self, value) -> None:
        self.edit.setText("" if value is None else f"{value:g}" if self._decimals else str(int(value)))

    def _clamp(self, value):
        return None if value is None else round(min(max(value, self._low), self._high), self._decimals)

    def _step_by(self, direction: int) -> None:
        value = self.value()
        self.set_value(self._clamp(self._start if value is None else value + direction * self._step))

    def eventFilter(self, obj, event) -> bool:
        if obj is self.edit and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Up, Qt.Key_Down):
            self._step_by(1 if event.key() == Qt.Key_Up else -1)
            return True
        return False


class CheckList(QWidget):
    """Searchable list of choices with check marks; "Select all" / "Clear" act on the rows being shown."""
    changed = Signal()

    def __init__(self, items: list[tuple], empty_hint: str = "", parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.box = QLineEdit()
        self.box.setPlaceholderText("Filter the list…")
        self.box.setClearButtonEnabled(True)
        self.box.setVisible(len(items) > 12)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        for text, state in (("Select all", True), ("Clear", False)):
            button = QPushButton(text)
            button.setStyleSheet("padding: 3px 10px;")
            button.clicked.connect(lambda _c=False, st=state: self._set_visible(st))
            actions.addWidget(button)
        actions.addStretch(1)
        self.actions = QWidget()
        self.actions.setLayout(actions)
        actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setVisible(bool(items))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setFixedHeight(150)
        self.list.setStyleSheet(
            "QListWidget::item { padding: 3px 6px; }")
        self.list.setIconSize(QSize(16, 16))
        for key, text in items:   # the check mark is the item's icon; itemClicked toggles it (box or text)
            item = QListWidgetItem(check_icon(False), text)
            item.setData(_KEY, key)
            item.setData(_SEARCH, normalize_text(text))
            item.setData(_ON, False)
            self.list.addItem(item)
        self.hint = QLabel(empty_hint)
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.hint.setVisible(not items and bool(empty_hint))
        self.list.setVisible(bool(items))
        for w in (self.box, self.actions, self.list, self.hint):
            column.addWidget(w)
        self.box.textChanged.connect(self._filter)
        self.list.itemClicked.connect(self._toggle)

    def _filter(self, text: str) -> None:
        terms = normalize_text(text).split()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(not all(t in item.data(_SEARCH) for t in terms))

    @staticmethod
    def _mark(item: QListWidgetItem, on: bool) -> None:
        item.setData(_ON, on)
        item.setIcon(check_icon(on))

    def _toggle(self, item: QListWidgetItem) -> None:
        self._mark(item, not item.data(_ON))
        self.changed.emit()

    def _set_visible(self, on: bool) -> None:
        for i in range(self.list.count()):
            if not self.list.item(i).isHidden():
                self._mark(self.list.item(i), on)
        self.changed.emit()

    def checked(self) -> list:
        items = (self.list.item(i) for i in range(self.list.count()))
        return [item.data(_KEY) for item in items if item.data(_ON)]

    def set_checked(self, keys) -> None:
        keys = set(keys)
        for i in range(self.list.count()):
            self._mark(self.list.item(i), self.list.item(i).data(_KEY) in keys)


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
        minutes = dict(presets=(60, 90, 120, 150, 180), step=5, high=1000, label=lambda v: f"{v} min")
        self.runtime_min = NumberField(**minutes)
        self.runtime_max = NumberField(**minutes)
        form.addLayout(_row("Type", self.kind, "   Runtime  from",
                            self.runtime_min, "to", self.runtime_max, "min"))

        # -- release year, ratings --
        section("Release and ratings")
        low, high = options["years"] or (1900, 2100)
        self.year_mode = QComboBox()
        self.year_mode.addItem("Between", "between")
        self.year_mode.addItem("Only in", "exact")
        decades = tuple(range(low // 10 * 10 + 10, high + 1, 10))
        self.year_from = NumberField(decades, 1, 1800, 2100, start=low)
        self.year_to = NumberField(tuple(reversed(decades)), 1, 1800, 2100, start=high)
        self.year_and = QLabel("and")
        form.addLayout(_row("Year", self.year_mode, self.year_from, self.year_and, self.year_to))
        rating = dict(presets=(5, 6, 7, 8, 9), step=0.5, high=10, decimals=1, label=lambda v: f"{v:g}")
        self.rating_min = NumberField(**rating)
        self.rating_max = NumberField(**rating)
        form.addLayout(_row("TMDB rating from", self.rating_min, "to", self.rating_max))
        votes = dict(presets=(100, 500, 1000, 5000, 10000, 100000), step=100, label=lambda v: f"{v:,}")
        self.votes_min = NumberField(**votes)
        self.votes_max = NumberField(**votes)
        form.addLayout(_row("TMDB votes from", self.votes_min, "to", self.votes_max))

        # -- genre and age rating --
        section("Genre and age rating")
        self.genres = CheckList(named(options["genres"]))
        self.genres_all = Check("Must have all the selected genres")
        genres_box = QWidget()
        column = QVBoxLayout(genres_box)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.genres)
        column.addWidget(self.genres_all)
        self.certs = CheckList(named(options["certifications"]),
                               "No age ratings saved yet. Use “Force update of all movies” in the Metadata "
                               "menu to download them.")
        pair(("Genres", genres_box), ("Age rating", self.certs))

        section("Countries and languages")
        self.countries = CheckList(named(options["countries"]), "No production countries saved yet.")
        self.languages = CheckList(named(options["languages"]), "No spoken languages saved yet.")
        pair(("Production countries", self.countries), ("Languages", self.languages))

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
        self.favorite = Check("Favorites")
        self.watchlist = Check("Watchlist")
        self.in_progress = Check("Continue watching")
        form.addLayout(_row(self.watched, self.favorite, self.watchlist, self.in_progress))
        self.added_days = NumberField((7, 30, 90, 180, 365), 1, 1, 36500, label=lambda v: f"{v} days")
        form.addLayout(_row("Added in the last", self.added_days, "days"))
        s = self.service
        self.collections = CheckList(
            [(c["id"], f"{c['name']}  ({len(s.membership.get(c['id'], ()))})") for c in sorted(s.collections, key=lambda c: normalize_text(c["name"]))],
            "You have not created any collections yet.")
        self.tags = CheckList(options["tags"], "You have not created any tags yet.")
        self.stars = CheckList([(v, star_text(v) if v else "Not rated")
                                for v in (5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1, 0.5, 0)])
        pair(("My collections", self.collections), ("My tags", self.tags), ("My rating", self.stars))

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
            w.changed.connect(self._changed)
        for w in (self.genres_all, self.favorite, self.watchlist, self.in_progress):
            w.toggled.connect(self._changed)
        for w in (self.genres, self.certs, self.countries, self.languages, self.directors, self.cast,
                  self.collections, self.tags, self.stars):
            w.changed.connect(self._changed)

    # ---------------------------------------------------------------------- criteria --
    def _numbers(self) -> dict:
        return {"year_min": self.year_from, "year_max": self.year_to, "rating_min": self.rating_min,
                "rating_max": self.rating_max, "votes_min": self.votes_min, "votes_max": self.votes_max,
                "runtime_min": self.runtime_min, "runtime_max": self.runtime_max,
                "added_days": self.added_days}

    def _lists(self) -> dict:
        return {"genres": self.genres, "certifications": self.certs, "countries": self.countries,
                "languages": self.languages, "directors": self.directors, "cast": self.cast,
                "collections": self.collections, "tags": self.tags, "stars": self.stars}

    def criteria(self) -> dict:
        c: dict = {}
        if self.kind.currentData():
            c["kind"] = self.kind.currentData()
        for key, widget in self._lists().items():
            if widget.checked():
                c[key] = widget.checked()
        if "genres" in c and self.genres_all.isChecked():
            c["genres_all"] = True
        for key, field in self._numbers().items():
            value = field.value()
            if value:   # empty or 0 = no limit
                c[key] = value
        if c.get("rating_max", 0) >= 10:
            del c["rating_max"]
        if self.year_mode.currentData() == "exact":
            c.pop("year_max", None)
            if "year_min" in c:
                c["year_max"] = c["year_min"]
        if self.watched.currentData() is not None:
            c["watched"] = self.watched.currentData()
        for key, box in (("favorite", self.favorite), ("watchlist", self.watchlist),
                         ("in_progress", self.in_progress)):
            if box.isChecked():
                c[key] = True
        return c

    def load(self, c: dict) -> None:
        self._loading = True
        self.kind.setCurrentIndex(max(0, self.kind.findData(c.get("kind"))))
        for key, widget in self._lists().items():
            widget.set_checked(c.get(key, ()))
        self.genres_all.setChecked(bool(c.get("genres_all")))
        exact = c.get("year_min") is not None and c.get("year_min") == c.get("year_max")
        self.year_mode.setCurrentIndex(1 if exact else 0)
        for key, field in self._numbers().items():
            field.set_value(c.get(key))
        self.watched.setCurrentIndex(max(0, self.watched.findData(c.get("watched"))))
        for key, box in (("favorite", self.favorite), ("watchlist", self.watchlist),
                         ("in_progress", self.in_progress)):
            box.setChecked(bool(c.get(key)))
        self._loading = False
        self._sync_year()

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
