"""Reprodutor integrado, baseado no libVLC (python-vlc). Aparece dentro da janela principal."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QStyle,
                               QVBoxLayout, QWidget)

_vlc = None      # (módulo vlc, Instance) depois da primeira carga bem-sucedida
_error = ""      # motivo da falha (guardado para não tentar de novo)


def unavailable_reason() -> str:
    """Por que o player integrado não pode ser usado ('' = pode)."""
    global _vlc, _error
    if sys.platform.startswith("linux") and QGuiApplication.platformName() != "xcb":
        return "O player integrado precisa de uma sessão X11 (ou rode com QT_QPA_PLATFORM=xcb)."
    if _vlc is None and not _error:
        try:
            import vlc
            instance = vlc.Instance()
            if instance is None:
                raise RuntimeError("libVLC")
            _vlc = (vlc, instance)
        except Exception:  # noqa: BLE001 - python-vlc ou libVLC ausentes
            _error = "libVLC não encontrado. Instale o VLC (e o pacote python-vlc) para usar o player integrado."
    return _error


def _clock(ms: int) -> str:
    hours, rest = divmod(max(0, ms) // 1000, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class _SeekSlider(QSlider):
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:   # clicar na barra salta para o ponto clicado
            self.setValue(QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width()))
            self.sliderMoved.emit(self.value())
        super().mousePressEvent(event)


class VlcPlayerPage(QWidget):
    back_requested = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._vlc, self._instance = _vlc
        self._mp = self._instance.media_player_new()
        self._dragging = False
        self._fullscreen = False
        self._build(title)
        self._timer = QTimer(self, interval=250)
        self._timer.timeout.connect(self._tick)
        for keys, action in (("Space", self.toggle_pause), ("F", self.toggle_fullscreen),
                             ("M", self._mp.audio_toggle_mute), ("Esc", self._escape),
                             ("Left", lambda: self._jump(-10000)), ("Right", lambda: self._jump(10000)),
                             ("Up", lambda: self.volume.setValue(self.volume.value() + 5)),
                             ("Down", lambda: self.volume.setValue(self.volume.value() - 5))):
            QShortcut(QKeySequence(keys), self, activated=action)

    # -- construção ---------------------------------------------------------------
    def _build(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.video = QWidget()
        self.video.setAttribute(Qt.WA_NativeWindow)    # o VLC desenha nesta janela
        self.video.setAttribute(Qt.WA_StyledBackground)
        self.video.setStyleSheet("background: #000;")
        self.video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.video, 1)

        self.controls = QWidget()
        self.controls.setObjectName("page")
        row = QHBoxLayout(self.controls)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)
        self.play_btn = self._button("⏸", self.toggle_pause)
        self.elapsed, self.total = QLabel("0:00"), QLabel("0:00")
        self.seek = _SeekSlider(Qt.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.seek.sliderMoved.connect(lambda v: self._mp.set_position(v / 1000))
        self.seek.sliderReleased.connect(self._seek_released)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip("Volume")
        self.volume.valueChanged.connect(self._mp.audio_set_volume)
        name = QLabel(title)
        name.setObjectName("muted")
        for w in (self._button("←  Voltar", self.back_requested.emit), self.play_btn,
                  self.elapsed, self.seek, self.total, self.volume,
                  self._button("⛶", self.toggle_fullscreen), name):
            row.addWidget(w, 1 if w is self.seek else 0)
        layout.addWidget(self.controls)

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.NoFocus)   # a barra de espaço é atalho do player, não do botão
        button.clicked.connect(lambda _checked=False: slot())
        return button

    # -- reprodução ---------------------------------------------------------------
    def start(self, path: str) -> None:
        self._mp.set_media(self._instance.media_new(path))
        handle = int(self.video.winId())
        if sys.platform.startswith("linux"):
            self._mp.set_xwindow(handle)
        elif sys.platform == "win32":
            self._mp.set_hwnd(handle)
        elif sys.platform == "darwin":
            self._mp.set_nsobject(handle)
        self._mp.video_set_mouse_input(False)   # teclado e mouse ficam com o Qt
        self._mp.video_set_key_input(False)
        self._mp.play()
        self._timer.start()

    def toggle_pause(self) -> None:
        if self._mp.get_state() == self._vlc.State.Ended:
            self._mp.stop()
            self._mp.play()
        else:
            self._mp.pause()

    def _jump(self, delta_ms: int) -> None:
        if self._mp.get_length() > 0:
            self._mp.set_time(max(0, self._mp.get_time() + delta_ms))

    def _seek_released(self) -> None:
        self._dragging = False
        self._mp.set_position(self.seek.value() / 1000)

    def _tick(self) -> None:
        length = self._mp.get_length()
        if length > 0:
            self.total.setText(_clock(length))
            self.elapsed.setText(_clock(self._mp.get_time()))
            if not self._dragging:
                self.seek.setValue(int(self._mp.get_position() * 1000))
        self.play_btn.setText("⏸" if self._mp.is_playing() else "▶")

    # -- tela cheia / saída ---------------------------------------------------------
    def toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self._fullscreen)

    def _set_fullscreen(self, on: bool) -> None:
        window = self.window()
        self._fullscreen = on
        window.statusBar().setVisible(not on)
        window.showFullScreen() if on else window.showNormal()

    def _escape(self) -> None:
        if self._fullscreen:
            self._set_fullscreen(False)
        else:
            self.back_requested.emit()

    def leave(self) -> None:
        """Sai da tela cheia e para o vídeo (antes de voltar à tela anterior)."""
        if self._fullscreen:
            self._set_fullscreen(False)
        self._timer.stop()
        self._mp.stop()

    def release(self) -> None:
        self._timer.stop()
        self._mp.stop()
        self._mp.release()
