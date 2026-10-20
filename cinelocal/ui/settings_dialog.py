"""Tela de configurações: pasta, chave do TMDB, idioma e player."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ..config import LANGUAGES
from ..service import LibraryService


class SettingsDialog(QDialog):
    def __init__(self, service: LibraryService, parent=None, intro: str = "",
                 focus_key: bool = False):
        super().__init__(parent)
        self.service = service
        self._closed = False
        self.saved = False
        s = service.settings
        self.setWindowTitle("Configurações")
        self.setModal(True)
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(14)
        if intro:
            note = QLabel(intro)
            note.setWordWrap(True)
            root.addWidget(note)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(form.labelAlignment())

        self.folder_edit = QLineEdit(s.get("library_path"))
        self.folder_edit.setPlaceholderText("Pasta onde estão todos os seus filmes")
        browse = QPushButton("Procurar…")
        browse.clicked.connect(self._browse_folder)
        form.addRow("Pasta de filmes", self._with_button(self.folder_edit, browse))

        self.key_edit = QLineEdit(s.get("tmdb_api_key"))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Cole aqui a chave da API do TMDB")
        self.test_btn = QPushButton("Testar")
        self.test_btn.clicked.connect(self._test_key)
        form.addRow("Chave do TMDB", self._with_button(self.key_edit, self.test_btn))

        self.key_status = QLabel("")
        self.key_status.setObjectName("muted")
        form.addRow("", self.key_status)
        help_label = QLabel(
            'Gratuita: crie uma conta em <a href="https://www.themoviedb.org/signup">themoviedb.org</a>, '
            'abra <a href="https://www.themoviedb.org/settings/api">Configurações → API</a> e copie a '
            '“Chave da API” (ou o “Token de leitura”).')
        help_label.setOpenExternalLinks(True)
        help_label.setWordWrap(True)
        help_label.setObjectName("muted")
        form.addRow("", help_label)

        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(f"{name}  ({code})", code)
        current = s.get("language")
        index = self.language.findData(current)
        if index < 0:
            self.language.addItem(current, current)
            index = self.language.count() - 1
        self.language.setCurrentIndex(index)
        form.addRow("Idioma dos metadados", self.language)

        self.player_edit = QLineEdit(s.get("player_command"))
        self.player_edit.setPlaceholderText("Vazio = player padrão do sistema (xdg-open)")
        pbrowse = QPushButton("Procurar…")
        pbrowse.clicked.connect(self._browse_player)
        form.addRow("Player externo", self._with_button(self.player_edit, pbrowse))
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        save = QPushButton("Salvar")
        save.setProperty("primary", True)
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        if focus_key:
            self.key_edit.setFocus()

    @staticmethod
    def _with_button(edit: QLineEdit, button: QPushButton) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return box

    def _save(self) -> None:
        self.saved = True
        self.accept()

    def done(self, result: int) -> None:
        self._closed = True
        super().done(result)

    def _browse_folder(self) -> None:
        start = self.folder_edit.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Selecionar pasta de filmes", start)
        if path:
            self.folder_edit.setText(path)

    def _browse_player(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher player", "/usr/bin")
        if path:
            self.player_edit.setText(path)

    def _test_key(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self.key_status.setText("Cole uma chave primeiro.")
            return
        self.key_status.setText("Testando…")
        self.test_btn.setEnabled(False)
        self.service.test_key(key, self._key_ok, self._key_failed)

    def _key_ok(self, _result) -> None:
        if not self._closed:
            self.test_btn.setEnabled(True)
            self.key_status.setText("✓ Chave válida.")

    def _key_failed(self, exc: Exception) -> None:
        if not self._closed:
            self.test_btn.setEnabled(True)
            self.key_status.setText(f"✗ {exc}")

    def values(self) -> dict:
        return {
            "library_path": self.folder_edit.text().strip(),
            "tmdb_api_key": self.key_edit.text().strip(),
            "language": self.language.currentData(),
            "player_command": self.player_edit.text().strip(),
        }
