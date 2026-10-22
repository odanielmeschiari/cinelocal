"""Icon buttons drawn from SVG (QtSvg): theme colors, one common size, no dependence on installed fonts."""
from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton

from .icon_data import ICONS
from .theme import COLORS

ICON_SIZE = 24   # side (px) of the square every icon is drawn in
_renderers: dict[tuple[str, str], QSvgRenderer] = {}


def _renderer(name: str, color: str) -> QSvgRenderer:
    key = (name, color)
    if key not in _renderers:
        view, shapes = ICONS[name]
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" fill="{color}">{shapes}</svg>'
        _renderers[key] = QSvgRenderer(svg.encode())
    return _renderers[key]


def draw_icon(painter: QPainter, name: str, color: str, rect: QRectF) -> None:
    """Draws one of the SVG icons inside `rect` (for custom painting, e.g. the poster badges)."""
    _renderer(name, color).render(painter, rect)


class IconButton(QPushButton):
    """Square button with an SVG icon centered in it. `icon_on` is shown while the button is checked.
    The look of the button itself (hover background...) comes from theme.py through `object_name`; the icon takes the
    text color, or the accent color on hover/checked. `color` forces one color (e.g. white over the blue play button);
    `checked_color` is the theme color of a checked button, `size` the side of the drawing."""

    def __init__(self, icon: str, icon_on: str | None = None, object_name: str = "bigIcon", box: int = 44,
                 size: int = ICON_SIZE, color: str | None = None, checked_color: str = "accent_hover", parent=None):
        super().__init__(parent)
        if object_name:
            self.setObjectName(object_name)
        self.setFixedSize(box, box)
        self._icon, self._icon_on, self._size = icon, icon_on, size
        self._color, self._checked_color = color, checked_color
        self._recolor = object_name != "iconBtn"   # "iconBtn" shows hover with a background, not a color

    def set_icon(self, icon: str) -> None:
        if icon != self._icon:
            self._icon = icon
            self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._color:
            color = self._color
        elif self._recolor and self.isDown():
            color = COLORS["accent"]
        elif self.isChecked():
            color = COLORS[self._checked_color]
        elif self._recolor and self.underMouse():
            color = COLORS["accent_hover"]
        else:
            color = COLORS["text"]
        name = self._icon_on if self.isChecked() and self._icon_on else self._icon
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        _renderer(name, color).render(painter, QRectF((self.width() - self._size) / 2,
                                                      (self.height() - self._size) / 2, self._size, self._size))
        painter.end()
