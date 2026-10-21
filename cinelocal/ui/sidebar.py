"""Barra lateral: biblioteca, coleções, gêneros e décadas."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from ..filters import Filter
from .theme import COLORS

_NEW_COLLECTION = ("new_collection", None)
_VALUE_ROLE = Qt.UserRole + 1


class Sidebar(QTreeWidget):
    filter_changed = Signal(object)
    new_collection_requested = Signal()
    rename_collection_requested = Signal(int)
    delete_collection_requested = Signal(int)

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
        self.currentItemChanged.connect(self._on_current_changed)
        self._current: Filter = ("home", None)
        self._rebuilding = False

    @property
    def current_filter(self) -> Filter:
        return self._current

    # -- construção -----------------------------------------------------------------
    def rebuild(self, counts: dict, collections: list[dict],
                membership: dict[int, set[int]], current: Filter) -> None:
        self._rebuilding = True
        self.clear()

        self._header("BIBLIOTECA")
        self._entry("Início", ("home", None), None)
        if counts["continue"]:
            self._entry("Continuar assistindo", ("continue", None), counts["continue"])
        self._entry("Todos os filmes", ("all", None), counts["all"])
        self._entry("Favoritos", ("favorites", None), counts["favorites"])
        self._entry("Watchlist", ("watchlist", None), counts["watchlist"])
        self._entry("Assistidos", ("watched", True), counts["watched"])
        self._entry("Não assistidos", ("watched", False), counts["unwatched"])
        if counts["review"]:
            self._entry("Precisam de revisão", ("review", None), counts["review"])

        self._header("COLEÇÕES")
        self._entry("Nova coleção", _NEW_COLLECTION, None)
        for c in collections:
            self._entry(c["name"], ("collection", c["id"]), len(membership.get(c["id"], ())))

        if counts["genres"]:
            self._header("GÊNEROS")
            for name, n in counts["genres"]:
                self._entry(name, ("genre", name), n)

        if counts["decades"]:
            self._header("ANO")
            for decade, n in counts["decades"]:
                self._entry(f"Anos {decade}", ("decade", decade), n)

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
        text = label if count is None else f"{label}   ({count})"
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

    def _select(self, flt: Filter) -> None:
        item = self._find(flt) or self._find(("all", None))
        if item is not None:
            self._current = self._filter_of(item)
            self.setCurrentItem(item)

    # -- eventos --------------------------------------------------------------------------
    def _on_current_changed(self, item, _previous) -> None:
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
        if not data or data[0] != "collection":
            return
        menu = QMenu(self)
        rename = menu.addAction("Renomear coleção…")
        delete = menu.addAction("Excluir coleção")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == rename:
            self.rename_collection_requested.emit(data[1])
        elif chosen == delete:
            self.delete_collection_requested.emit(data[1])
