"""Página inicial: uma fileira rolável por seção (continuar assistindo, favoritos, watchlist...)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .grid import MovieRow

# chave, título, filtro (o mesmo formato usado na barra lateral)
SECTIONS = (
    ("continue", "Continuar assistindo", ("continue", None)),
    ("favorites", "Favoritos", ("favorites", None)),
    ("watchlist", "Watchlist", ("watchlist", None)),
    ("watched", "Assistidos", ("watched", True)),
    ("all", "Todos os filmes", ("all", None)),
)


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


class HomePage(QScrollArea):
    movie_opened = Signal(int)
    context_requested = Signal(list, QPoint)

    def __init__(self, progress_of, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 16, 16)
        layout.setSpacing(18)
        self.sections: dict[str, HomeSection] = {}
        for key, title, _flt in SECTIONS:
            section = HomeSection(title)
            section.row.itemDelegate().progress_of = progress_of
            section.row.movie_opened.connect(self.movie_opened)
            section.row.context_requested.connect(self.context_requested)
            layout.addWidget(section)
            self.sections[key] = section
        layout.addStretch(1)
        self.setWidget(body)

    def set_data(self, data: dict[str, list[dict]]) -> bool:
        """Preenche as fileiras; seções vazias somem. Retorna False se todas estiverem vazias."""
        any_visible = False
        for key, section in self.sections.items():
            items = data.get(key, [])
            bar = section.row.horizontalScrollBar()
            position = bar.value()
            section.row.movie_model.set_movies(items)
            QTimer.singleShot(0, lambda b=bar, p=position: b.setValue(p))   # o layout só termina depois
            section.count.setText(str(len(items)))
            section.setVisible(bool(items))
            any_visible = any_visible or bool(items)
        return any_visible

    def refresh_movie(self, movie_id: int) -> None:
        for section in self.sections.values():
            section.row.movie_model.refresh_movie(movie_id)
