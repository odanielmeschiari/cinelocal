"""Sidebar: library, collections, genres, decades, age ratings, actors and directors."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from ..filters import Filter
from ..utils import star_text
from .theme import COLORS

_NEW_COLLECTION = ("new_collection", None)
_VALUE_ROLE = Qt.UserRole + 1
# What the user can hide from the sidebar (Settings): (key, label). "All movies" is always there.
SIDEBAR_OPTIONS = (("continue", "Continue watching"), ("foryou", "For you"), ("favorites", "Favorites"),
                   ("watchlist", "Watchlist"), ("watched", "Watched"), ("unwatched", "Unwatched"),
                   ("history", "History"), ("review", "Needs review"), ("collections", "Collections"),
                   ("tags", "Tags"), ("stars", "My rating"), ("genres", "Genres"), ("decades", "Year"),
                   ("certifications", "Age rating"), ("cast", "Actors"), ("directors", "Directors"))


class Sidebar(QTreeWidget):
    filter_changed = Signal(object)
    new_collection_requested = Signal()
    rename_collection_requested = Signal(int)
    configure_collection_requested = Signal(int)
    delete_collection_requested = Signal(int)
    edit_tag_requested = Signal(int)
    delete_tag_requested = Signal(int)

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
        self._current: Filter = ("all", None)
        self._rebuilding = False

    @property
    def current_filter(self) -> Filter:
        return self._current

    # -- construction -----------------------------------------------------------------
    def rebuild(self, counts: dict, collections: list[dict],
                membership: dict[int, set[int]], current: Filter,
                tags: list[dict] | None = None,
                tag_membership: dict[int, set[int]] | None = None,
                hidden: set[str] | frozenset = frozenset()) -> None:
        """`hidden`: keys of SIDEBAR_OPTIONS the user chose not to see."""
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

        if shown("collections"):
            self._header("COLLECTIONS")
            self._entry("New collection", _NEW_COLLECTION, None)
            for c in collections:
                self._entry(c["name"], ("collection", c["id"]), len(membership.get(c["id"], ())))

        if tags and shown("tags"):
            self._header("TAGS")
            tag_membership = tag_membership or {}
            for tag in tags:
                self._entry(tag["name"], ("tag", tag["id"]),
                            sum(tag["id"] in ids for ids in tag_membership.values()))

        if counts["stars"] and shown("stars"):
            self._header("MY RATING")
            for n, count in counts["stars"]:
                self._entry(star_text(n), ("stars", n), count)

        if counts["genres"] and shown("genres"):
            self._header("GENRES")
            for name, n in counts["genres"]:
                self._entry(name, ("genre", name), n)

        if counts["decades"] and shown("decades"):
            self._header("YEAR")
            for decade, n in counts["decades"]:
                self._entry(f"{decade}s", ("decade", decade), n)

        for key, header, kind in (("certifications", "AGE RATING", "certification"), ("cast", "ACTORS", "cast"),
                                  ("directors", "DIRECTORS", "director")):
            if counts[key] and shown(key):
                self._header(header)
                for name, n in counts[key]:
                    self._entry(name, (kind, name), n)

        self._select(current)
        self._rebuilding = False

    def _header(self, text: str) -> None:
        item = QTreeWidgetItem([text])
        item.setFlags(Qt.ItemIsEnabled)
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(8)
        item.setFont(0, font)
        item.setForeground(0, QBrush(QColor(COLORS["muted"])))
        self.addTopLevelItem(item)

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
        if data == _NEW_COLLECTION:
            self._rebuilding = True
            self._select(self._current)
            self._rebuilding = False
            self.new_collection_requested.emit()
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
        rename = menu.addAction("Rename collection…")
        configure = menu.addAction("Configure collection…")
        delete = menu.addAction("Delete collection")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == rename:
            self.rename_collection_requested.emit(data[1])
        elif chosen == configure:
            self.configure_collection_requested.emit(data[1])
        elif chosen == delete:
            self.delete_collection_requested.emit(data[1])
