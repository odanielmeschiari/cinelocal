"""Sidebar: library, collections, lists, genres, decades, age ratings, actors and directors."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QMenu, QSizePolicy, QStyledItemDelegate,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QWidget)

from ..filters import Filter
from ..utils import normalize_text, star_text
from .theme import COLORS

_NEW_COLLECTION = ("new_collection", None)
_NEW_LIST = ("new_list", None)
_VALUE_ROLE = Qt.UserRole + 1
_HEADER_ROLE = Qt.UserRole + 2   # True on the headings
_RULE_COLOR = "#4a4a4a"   # the thin line under each heading
# What the user can hide from the sidebar (Settings): (key, label). "All movies" is always there.
SIDEBAR_OPTIONS = (("continue", "Continue watching"), ("foryou", "For you"), ("favorites", "Favorites"),
                   ("watchlist", "Watchlist"), ("watched", "Watched"), ("unwatched", "Unwatched"),
                   ("history", "History"), ("review", "Needs review"), ("collections", "Collections"), ("lists", "Lists"),
                   ("tags", "Tags"), ("stars", "My rating"), ("genres", "Genres"), ("decades", "Year"),
                   ("certifications", "Age rating"), ("cast", "Actors"), ("directors", "Directors"))
# How each long section can be ordered (the user picks it with the button of the section's heading):
# section key -> (the order it has until the user picks another, the orders offered)
_MODE_LABELS = {"count": "Most frequent", "az": "A–Z", "za": "Z–A", "newest": "Newest first", "oldest": "Oldest first"}
_BY_NAME = ("count", ("count", "az", "za"))
_BY_COUNT_AFTER_NAME = ("az", ("az", "za", "count"))
SORT_CHOICES = {"genres": _BY_NAME, "certifications": _BY_NAME, "cast": _BY_NAME, "directors": _BY_NAME,
                "collections": _BY_COUNT_AFTER_NAME, "lists": _BY_COUNT_AFTER_NAME, "tags": _BY_COUNT_AFTER_NAME,
                "decades": ("newest", ("newest", "oldest", "count"))}


def sort_entries(entries: list[tuple], mode: str) -> list[tuple]:
    """`entries` are (name, count, value): the value is what the entry filters by (a year, for the decades)."""
    if mode == "count":
        return sorted(entries, key=lambda e: (-e[1], normalize_text(e[0]), e[0]))
    if mode in ("az", "za"):
        return sorted(entries, key=lambda e: (normalize_text(e[0]), e[0]), reverse=mode == "za")
    return sorted(entries, key=lambda e: e[2], reverse=mode == "newest")


class _Delegate(QStyledItemDelegate):
    """The usual look, plus a thin line under each heading."""

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        if index.data(_HEADER_ROLE):
            painter.save()
            painter.setPen(QPen(QColor(_RULE_COLOR), 1))
            y = option.rect.bottom() - 3
            painter.drawLine(option.rect.left() + 14, y, option.rect.right() - 14, y)
            painter.restore()


class Sidebar(QTreeWidget):
    filter_changed = Signal(object)
    new_collection_requested = Signal()
    new_list_requested = Signal()
    rename_collection_requested = Signal(int)
    configure_collection_requested = Signal(int)
    delete_collection_requested = Signal(int)
    edit_tag_requested = Signal(int)
    delete_tag_requested = Signal(int)
    sort_requested = Signal(str, str)   # section key, mode (see SORT_MODES)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)
        self.itemClicked.connect(self._on_item_clicked)
        self.setItemDelegate(_Delegate(self))
        self._current: Filter = ("all", None)
        self._rebuilding = False
        self._sorts: dict = {}
        self._kinds: dict[int, str] = {}   # id of a collection -> "collection" or "list"

    @property
    def current_filter(self) -> Filter:
        return self._current

    # -- construction -----------------------------------------------------------------
    def rebuild(self, counts: dict, collections: list[dict],
                membership: dict[int, set[int]], current: Filter,
                tags: list[dict] | None = None,
                tag_membership: dict[int, set[int]] | None = None,
                hidden: set[str] | frozenset = frozenset(), sorts: dict | None = None) -> None:
        """`hidden`: keys of SIDEBAR_OPTIONS the user chose not to see. `sorts`: section key -> mode of SORT_CHOICES."""
        self._sorts = sorts or {}
        self._kinds = {c["id"]: c.get("kind", "collection") for c in collections}
        scroll = self.verticalScrollBar().value()   # a rebuild (e.g. a new order) leaves the list where it was
        self._rebuilding = True
        self.clear()

        def shown(key: str) -> bool:
            return key not in hidden

        self._header("LIBRARY")
        if counts["continue"] and shown("continue"):
            self._entry("Continue watching", ("continue", None), counts["continue"])
        self._entry("All movies", ("all", None), counts["all"])
        if shown("foryou"):
            self._entry("For you", ("foryou", None), counts.get("foryou") or None)
        if shown("favorites"):
            self._entry("Favorites", ("favorites", None), counts["favorites"])
        if shown("watchlist"):
            self._entry("Watchlist", ("watchlist", None), counts["watchlist"])
        if shown("watched"):
            self._entry("Watched", ("watched", True), counts["watched"])
        if shown("unwatched"):
            self._entry("Unwatched", ("watched", False), counts["unwatched"])
        if counts["history"] and shown("history"):
            self._entry("History", ("history", None), counts["history"])
        if counts["review"] and shown("review"):
            self._entry("Needs review", ("review", None), counts["review"])

        for key, header, new, kind in (("collections", "COLLECTIONS", ("New collection", _NEW_COLLECTION), "collection"),
                                       ("lists", "LISTS", ("New list", _NEW_LIST), "list")):
            if shown(key):
                self._header(header, key)
                self._entry(new[0], new[1], None)
                entries = [(c["name"], len(membership.get(c["id"], ())), c["id"])
                           for c in collections if c.get("kind", "collection") == kind]
                for name, n, collection_id in self._ordered(key, entries):
                    self._entry(name, ("collection", collection_id), n)

        if tags and shown("tags"):
            self._header("TAGS", "tags")
            tag_membership = tag_membership or {}
            entries = [(tag["name"], sum(tag["id"] in ids for ids in tag_membership.values()), tag["id"])
                       for tag in tags]
            for name, n, tag_id in self._ordered("tags", entries):
                self._entry(name, ("tag", tag_id), n)

        if counts["stars"] and shown("stars"):
            self._header("MY RATING")
            for n, count in counts["stars"]:
                self._entry(star_text(n), ("stars", n), count)

        if counts["genres"] and shown("genres"):
            self._header("GENRES", "genres")
            for name, n, _value in self._ordered("genres", [(name, n, name) for name, n in counts["genres"]]):
                self._entry(name, ("genre", name), n)

        if counts["decades"] and shown("decades"):
            self._header("YEAR", "decades")
            for _name, n, decade in self._ordered("decades", [(f"{d}s", n, d) for d, n in counts["decades"]]):
                self._entry(f"{decade}s", ("decade", decade), n)

        for key, header, kind in (("certifications", "AGE RATING", "certification"), ("cast", "ACTORS", "cast"),
                                  ("directors", "DIRECTORS", "director")):
            if counts[key] and shown(key):
                self._header(header, key)
                for name, n, _value in self._ordered(key, [(name, n, name) for name, n in counts[key]]):
                    self._entry(name, (kind, name), n)

        self._select(current)
        self._rebuilding = False
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(scroll))   # once the list has its size

    def _mode(self, key: str) -> str:
        default, modes = SORT_CHOICES[key]
        return self._sorts.get(key) if self._sorts.get(key) in modes else default

    def _ordered(self, key: str, entries: list[tuple]) -> list[tuple]:
        return sort_entries(entries, self._mode(key))

    def _header(self, text: str, sort_key: str | None = None) -> None:
        """A section heading; with `sort_key`, it has a small button to choose how the section is ordered."""
        item = QTreeWidgetItem([text])   # the text is the item's own, so the row has the same size as any other
        item.setFlags(Qt.ItemIsEnabled)
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(8)
        item.setFont(0, font)
        item.setForeground(0, QBrush(QColor(COLORS["muted"])))
        item.setData(0, _HEADER_ROLE, True)
        self.addTopLevelItem(item)
        if sort_key:   # a transparent layer over the row (the text shows through) holding only the button
            box = QWidget()
            box.setStyleSheet("background: transparent;")
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            button = QToolButton()
            button.setText("⇅")
            button.setFont(font)
            button.setToolTip("Sort")
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Ignored)
            button.setStyleSheet(f"QToolButton {{ border: none; background: transparent; color: {COLORS['muted']};"
                                 f" padding: 0 4px; margin: 0; }} QToolButton:hover {{ color: {COLORS['accent_hover']}; }}")
            button.clicked.connect(lambda _checked=False, b=button, k=sort_key: self._pick_sort(b, k))
            row.addStretch(1)
            row.addWidget(button)
            self.setItemWidget(item, 0, box)

    def _pick_sort(self, button, key: str) -> None:
        menu = QMenu(self)
        current = self._mode(key)
        for mode in SORT_CHOICES[key][1]:
            action = menu.addAction(_MODE_LABELS[mode])
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.setData(mode)
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is not None and chosen.data() != current:
            self.sort_requested.emit(key, chosen.data())

    def _entry(self, label: str, data: Filter, count: int | None) -> None:
        text = label if count is None else f"{label} ({count})"
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.UserRole, data[0])
        item.setData(0, _VALUE_ROLE, data[1])
        item.setToolTip(0, label)
        self.addTopLevelItem(item)

    @staticmethod
    def _filter_of(item) -> Filter | None:
        kind = item.data(0, Qt.UserRole)
        return None if kind is None else (kind, item.data(0, _VALUE_ROLE))

    def _find(self, flt: Filter):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if self._filter_of(item) == flt:
                return item
        return None

    def select(self, flt: Filter) -> None:
        """Highlights `flt` (the "All movies" entry if it is not in the list), without rebuilding the list."""
        self._select(flt)

    def _select(self, flt: Filter) -> None:
        item = self._find(flt) or self._find(("all", None))
        if item is not None:
            self._current = self._filter_of(item)
            self.setCurrentItem(item)

    # -- events --------------------------------------------------------------------------
    def _on_item_clicked(self, item, _column) -> None:
        if self._rebuilding or item is None:
            return
        data = self._filter_of(item)
        if data is None:
            return
        if data in (_NEW_COLLECTION, _NEW_LIST):
            self._rebuilding = True
            self._select(self._current)
            self._rebuilding = False
            (self.new_collection_requested if data == _NEW_COLLECTION else self.new_list_requested).emit()
            return
        self._current = data
        self.filter_changed.emit(data)

    def _on_context(self, pos) -> None:
        item = self.itemAt(pos)
        data = self._filter_of(item) if item else None
        if not data:
            return
        if data[0] == "tag":
            menu = QMenu(self)
            edit = menu.addAction("Edit tag…")
            delete = menu.addAction("Delete tag")
            chosen = menu.exec(self.viewport().mapToGlobal(pos))
            if chosen == edit:
                self.edit_tag_requested.emit(data[1])
            elif chosen == delete:
                self.delete_tag_requested.emit(data[1])
            return
        if data[0] != "collection":
            return
        menu = QMenu(self)
        noun = self._kinds.get(data[1], "collection")
        rename = menu.addAction(f"Rename {noun}…")
        configure = menu.addAction(f"Configure {noun}…")
        delete = menu.addAction(f"Delete {noun}")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == rename:
            self.rename_collection_requested.emit(data[1])
        elif chosen == configure:
            self.configure_collection_requested.emit(data[1])
        elif chosen == delete:
            self.delete_collection_requested.emit(data[1])
