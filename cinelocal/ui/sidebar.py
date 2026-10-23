"""Sidebar: library, collections, genres and decades."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import (QAbstractItemView, QMenu, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem)

from ..filters import Filter
from ..utils import star_text
from .theme import COLORS

_NEW_COLLECTION = ("new_collection", None)
_VALUE_ROLE = Qt.UserRole + 1
_COLOR_ROLE = Qt.UserRole + 2
_LABEL_ROLE = Qt.UserRole + 3
_COUNT_ROLE = Qt.UserRole + 4


class _SidebarItemDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        color_value = index.data(_COLOR_ROLE)
        if not color_value:
            return super().paint(painter, option, index)

        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        option.text = ""
        super().paint(painter, option, index)

        color = QColor(color_value)
        selected = bool(option.state & QStyle.State_Selected)
        text_color = QColor("#17202a" if color.lightness() > 175 else "#ffffff")
        rect = option.rect.adjusted(10, 2, -10, -2)
        height = min(26, rect.height())
        pill_rect = rect.adjusted(0, (rect.height() - height) // 2, 0,
                                  -(rect.height() - height) // 2)
        label = str(index.data(_LABEL_ROLE) or "")
        count = index.data(_COUNT_ROLE)
        font = option.font
        metrics = QFontMetrics(font)
        pill_width = metrics.horizontalAdvance(label) + 20
        pill_rect.setWidth(min(pill_width, rect.width()))

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        radius = height / 2
        pill_path = QPainterPath()
        pill_path.moveTo(pill_rect.left(), pill_rect.top())
        pill_path.lineTo(pill_rect.right() - radius, pill_rect.top())
        pill_path.quadTo(pill_rect.right(), pill_rect.top(), pill_rect.right(), pill_rect.top() + radius)
        pill_path.lineTo(pill_rect.right(), pill_rect.bottom() - radius)
        pill_path.quadTo(pill_rect.right(), pill_rect.bottom(),
                         pill_rect.right() - radius, pill_rect.bottom())
        pill_path.lineTo(pill_rect.left(), pill_rect.bottom())
        pill_path.closeSubpath()
        painter.drawPath(pill_path)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(pill_rect.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
        if count is not None:
            count_color = QColor("#ffffff" if selected else "#aeb8c4")
            count_rect = rect.adjusted(pill_rect.width() + 8, 0, 0, 0)
            painter.setPen(count_color)
            painter.drawText(count_rect, Qt.AlignVCenter | Qt.AlignLeft, f"({count})")
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        if index.data(_COLOR_ROLE):
            size.setHeight(max(size.height(), 30))
        return size


class Sidebar(QTreeWidget):
    filter_changed = Signal(object)
    new_collection_requested = Signal()
    rename_collection_requested = Signal(int)
    delete_collection_requested = Signal(int)
    edit_tag_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(_SidebarItemDelegate(self))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)
        self.currentItemChanged.connect(self._on_current_changed)
        self._current: Filter = ("all", None)
        self._rebuilding = False

    @property
    def current_filter(self) -> Filter:
        return self._current

    # -- construction -----------------------------------------------------------------
    def rebuild(self, counts: dict, collections: list[dict],
                membership: dict[int, set[int]], current: Filter,
                tags: list[dict] | None = None,
                tag_membership: dict[int, set[int]] | None = None) -> None:
        self._rebuilding = True
        self.clear()

        self._header("LIBRARY")
        if counts["continue"]:
            self._entry("Continue watching", ("continue", None), counts["continue"])
        self._entry("All movies", ("all", None), counts["all"])
        self._entry("Favorites", ("favorites", None), counts["favorites"])
        self._entry("Watchlist", ("watchlist", None), counts["watchlist"])
        self._entry("Watched", ("watched", True), counts["watched"])
        self._entry("Unwatched", ("watched", False), counts["unwatched"])
        if counts["history"]:
            self._entry("History", ("history", None), counts["history"])
        if counts["review"]:
            self._entry("Needs review", ("review", None), counts["review"])

        self._header("COLLECTIONS")
        self._entry("New collection", _NEW_COLLECTION, None)
        for c in collections:
            self._entry(c["name"], ("collection", c["id"]), len(membership.get(c["id"], ())))

        if tags:
            self._header("TAGS")
            tag_membership = tag_membership or {}
            for tag in tags:
                self._entry(tag["name"], ("tag", tag["id"]),
                            sum(tag["id"] in ids for ids in tag_membership.values()), tag["color"])

        if counts["stars"]:
            self._header("MY RATING")
            for n, count in counts["stars"]:
                self._entry(star_text(n), ("stars", n), count)

        if counts["genres"]:
            self._header("GENRES")
            for name, n in counts["genres"]:
                self._entry(name, ("genre", name), n)

        if counts["decades"]:
            self._header("YEAR")
            for decade, n in counts["decades"]:
                self._entry(f"{decade}s", ("decade", decade), n)

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

    def _entry(self, label: str, data: Filter, count: int | None, color: str | None = None) -> None:
        text = label if count is None else f"{label} ({count})"
        item = QTreeWidgetItem(["" if color else text])
        item.setData(0, Qt.UserRole, data[0])
        item.setData(0, _VALUE_ROLE, data[1])
        item.setToolTip(0, label)
        item.setData(0, _LABEL_ROLE, label)
        item.setData(0, _COUNT_ROLE, count)
        if color:
            item.setData(0, _COLOR_ROLE, color)
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

    # -- events --------------------------------------------------------------------------
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
        if not data:
            return
        if data[0] == "tag":
            menu = QMenu(self)
            edit = menu.addAction("Edit tag…")
            if menu.exec(self.viewport().mapToGlobal(pos)) == edit:
                self.edit_tag_requested.emit(data[1])
            return
        if data[0] != "collection":
            return
        menu = QMenu(self)
        rename = menu.addAction("Rename collection…")
        delete = menu.addAction("Delete collection")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == rename:
            self.rename_collection_requested.emit(data[1])
        elif chosen == delete:
            self.delete_collection_requested.emit(data[1])
