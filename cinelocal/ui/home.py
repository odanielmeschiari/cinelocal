"""Fileira rolável com título e setas (usada em "Continuar assistindo")."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .grid import MovieRow


class HomeSection(QWidget):
    """Título + setas + uma única fileira de capas."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        head = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("font-size: 14pt; font-weight: 700;")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        self.left = self._arrow("←", -1)
        self.right = self._arrow("→", 1)
        head.addWidget(name)
        head.addSpacing(10)
        head.addWidget(self.count, 0, Qt.AlignBottom)
        head.addStretch(1)
        head.addWidget(self.left)
        head.addWidget(self.right)
        layout.addLayout(head)
        self.row = MovieRow()
        layout.addWidget(self.row)
        bar = self.row.horizontalScrollBar()
        bar.valueChanged.connect(self._sync_arrows)
        bar.rangeChanged.connect(self._sync_arrows)
        self._sync_arrows()

    def _arrow(self, text: str, direction: int) -> QPushButton:
        button = QPushButton(text)
        button.setFixedWidth(44)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(lambda _checked=False: self.row.scroll_page(direction))
        return button

    def _sync_arrows(self, *_args) -> None:
        bar = self.row.horizontalScrollBar()
        self.left.setEnabled(bar.value() > bar.minimum())
        self.right.setEnabled(bar.value() < bar.maximum())
