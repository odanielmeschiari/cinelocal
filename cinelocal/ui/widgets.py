"""Pequenos componentes visuais reutilizáveis."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap


def rounded_pixmap(pixmap: QPixmap, radius: float) -> QPixmap:
    dpr = pixmap.devicePixelRatio() or 1.0
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pixmap.width() / dpr, pixmap.height() / dpr), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out
