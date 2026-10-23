"""Icon buttons drawn from SVG (QtSvg): theme colors, one common size, no dependence on installed fonts."""
from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton

from .icon_data import ICONS
from .theme import COLORS

ICON_SIZE = 24   # side (px) of the square every icon is drawn in
LABEL_PAD, LABEL_GAP = 16, 8   # buttons with text: side padding and space between icon and text
SPIN_MS, SPIN_MIN_TURNS = 1200, 3   # one turn of a spinning icon; fewest turns once started
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
    `checked_color` is the theme color of a checked button, `size` the side of the drawing; `text` adds a label
    (the button gets wider) to the right of the icon."""

    def __init__(self, icon: str, icon_on: str | None = None, object_name: str = "bigIcon", box: int = 44,
                 size: int = ICON_SIZE, color: str | None = None, checked_color: str = "accent_hover", text: str = "",
                 parent=None):
        super().__init__(parent)
        if object_name:
            self.setObjectName(object_name)
        self.setFixedSize(box, box)
        self._icon, self._icon_on, self._size = icon, icon_on, size
        self._color, self._checked_color = color, checked_color
        self._recolor = object_name != "iconBtn"   # "iconBtn" shows hover with a background, not a color
        self._angle, self._spin = 0.0, None
        self._text = text
        if text:
            self._font = QFont(self.font())
            self._font.setWeight(QFont.DemiBold)
            self._text_w = QFontMetrics(self._font).horizontalAdvance(text) + 2
            self.setFixedWidth(2 * LABEL_PAD + size + LABEL_GAP + self._text_w)

    def set_icon(self, icon: str) -> None:
        if icon != self._icon:
            self._icon = icon
            self.update()

    def set_spinning(self, on: bool) -> None:
        """Turns the icon around its center while `on`; after `on` goes False the current turn is finished."""
        if self._spin is None:
            self._spin = QVariantAnimation(self)
            self._spin.setStartValue(0.0)
            self._spin.setEndValue(360.0)
            self._spin.setDuration(SPIN_MS)
            self._spin.valueChanged.connect(self._set_angle)
        if on:
            self._spin.setLoopCount(-1)
            if self._spin.state() != QAbstractAnimation.Running:
                self._spin.start()
        elif self._spin.state() == QAbstractAnimation.Running:
            self._spin.setLoopCount(max(self._spin.currentLoop() + 1, SPIN_MIN_TURNS))

    def _set_angle(self, angle) -> None:
        self._angle = angle
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
        if self._angle:
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(self._angle)
            painter.translate(-self.width() / 2, -self.height() / 2)
        x = LABEL_PAD if self._text else (self.width() - self._size) / 2
        _renderer(name, color).render(painter, QRectF(x, (self.height() - self._size) / 2, self._size, self._size))
        if self._text:
            painter.setFont(self._font)
            painter.setPen(QColor(color))
            painter.drawText(QRectF(x + self._size + LABEL_GAP, 0, self._text_w, self.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, self._text)
        painter.end()
