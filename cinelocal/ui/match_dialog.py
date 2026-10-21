"""Escolha manual do filme correto no TMDB (ambiguidade, sem resultado ou correção)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from ..service import LibraryService


class MatchDialog(QDialog):
    def __init__(self, service: LibraryService, movie: dict, parent=None,
                 allow_skip: bool = False, position: str = ""):
        super().__init__(parent)
        self.service = service
        self.selected_tmdb_id: int | None = None
        self.skipped = False
        self._series = movie.get("kind") == "series"
        self._closed = False
        self.setWindowTitle("Corrigir correspondência")
        self.setModal(True)
        self.resize(640, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        head = QLabel(f"{'Série' if self._series else 'Arquivo'}: <b>{movie['file_name']}</b>" + (f"  ({position})" if position else ""))
        head.setWordWrap(True)
        layout.addWidget(head)

        row = QHBoxLayout()
        self.title_edit = QLineEdit(movie["clean_title"])
        self.title_edit.setPlaceholderText("Título do filme")
        self.year_edit = QLineEdit(str(movie["year_guess"] or ""))
        self.year_edit.setPlaceholderText("Ano")
        self.year_edit.setMaximumWidth(90)
        self.search_btn = QPushButton("Buscar")
        self.search_btn.setProperty("primary", True)
        row.addWidget(self.title_edit, 1)
        row.addWidget(self.year_edit)
        row.addWidget(self.search_btn)
        layout.addLayout(row)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        self.results = QListWidget()
        self.results.setWordWrap(True)
        layout.addWidget(self.results, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        self.confirm_btn = QPushButton("Usar este filme")
        self.confirm_btn.setProperty("primary", True)
        self.confirm_btn.setEnabled(False)
        if allow_skip:
            skip = QPushButton("Pular")
            skip.clicked.connect(self._skip)
            buttons.addWidget(skip)
        buttons.addWidget(cancel)
        buttons.addWidget(self.confirm_btn)
        layout.addLayout(buttons)

        self.search_btn.clicked.connect(self._search)
        self.title_edit.returnPressed.connect(self._search)
        self.year_edit.returnPressed.connect(self._search)
        self.results.itemSelectionChanged.connect(
            lambda: self.confirm_btn.setEnabled(bool(self.results.selectedItems())))
        self.results.itemDoubleClicked.connect(lambda _item: self._confirm())
        self.confirm_btn.clicked.connect(self._confirm)
        cancel.clicked.connect(self.reject)

        if service.has_key:
            QTimer.singleShot(0, self._search)
        else:
            self.status.setText("Configure a chave da API para buscar.")
            self.search_btn.setEnabled(False)

    def done(self, result: int) -> None:
        self._closed = True
        super().done(result)

    def _skip(self) -> None:
        self.skipped = True
        self.reject()

    def _search(self) -> None:
        query = self.title_edit.text().strip()
        if not query:
            return
        year_text = self.year_edit.text().strip()
        year = int(year_text) if year_text.isdigit() else None
        self.status.setText("Buscando…")
        self.results.clear()
        self.search_btn.setEnabled(False)
        self.service.search_tmdb(query, year, self._on_results, self._on_error, series=self._series)

    def _on_results(self, results: list[dict]) -> None:
        if self._closed:
            return
        self.search_btn.setEnabled(True)
        self.status.setText(f"{len(results)} resultado(s)." if results
                            else "Nada encontrado. Tente outro título ou remova o ano.")
        for r in results:
            year = f" ({r['year']})" if r["year"] else ""
            original = (f"\n{r['original_title']}"
                        if r["original_title"] and r["original_title"] != r["title"] else "")
            overview = r["overview"][:160] + ("…" if len(r["overview"]) > 160 else "")
            item = QListWidgetItem(f"{r['title']}{year}{original}\n{overview or 'Sem sinopse.'}")
            item.setData(Qt.UserRole, r["id"])
            self.results.addItem(item)
        if results:
            self.results.setCurrentRow(0)

    def _on_error(self, exc: Exception) -> None:
        if self._closed:
            return
        self.search_btn.setEnabled(True)
        self.status.setText(str(exc))

    def _confirm(self) -> None:
        items = self.results.selectedItems()
        if items:
            self.selected_tmdb_id = items[0].data(Qt.UserRole)
            self.accept()
