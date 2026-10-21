"""Reprodutor integrado, baseado no libVLC (python-vlc). Aparece dentro da janela principal."""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSizePolicy, QSlider, QStyle, QVBoxLayout, QWidget, QWidgetAction)

IDLE_HIDE_SECONDS = 2.5   # em tela cheia, controles e ponteiro somem depois deste tempo parado
# chave, rótulo, mínimo, máximo, padrão (em %). Nitidez 0 = filtro desligado.
_ADJUSTMENTS = (("brightness", "Brilho", 0, 200, 100), ("contrast", "Contraste", 0, 200, 100),
                ("saturation", "Cor", 0, 300, 100), ("sharpness", "Nitidez", 0, 100, 0))

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


def _track_name(name) -> str:
    return name.decode("utf-8", "replace") if isinstance(name, bytes) else str(name)


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
        self._path = ""
        self._adjust = {key: default for key, _l, _lo, _hi, default in _ADJUSTMENTS}
        self._sharp_applied = 0          # nitidez (%) com que a mídia atual foi aberta
        self._pending_start = None       # (posição em ms, pausado?) a restaurar após reabrir a mídia
        self._playing_seen = False
        self._chosen_audio = self._chosen_spu = None
        self._chrome_hidden = False
        self._last_pos = QCursor.pos()
        self._last_activity = time.monotonic()
        self._build(title)
        self._timer = QTimer(self, interval=250)
        self._timer.timeout.connect(self._tick)
        self._sharp_timer = QTimer(self, singleShot=True, interval=600)   # espera o slider parar
        self._sharp_timer.timeout.connect(self._apply_sharpness)
        for keys, action in (("Space", self.toggle_pause), ("F", self.toggle_fullscreen),
                             ("M", self._mp.audio_toggle_mute), ("Esc", self._escape),
                             ("Left", lambda: self._jump(-10000)), ("Right", lambda: self._jump(10000)),
                             ("Up", lambda: self.volume.setValue(self.volume.value() + 5)),
                             ("Down", lambda: self.volume.setValue(self.volume.value() - 5))):
            QShortcut(QKeySequence(keys), self, activated=lambda a=action: (self._wake(), a()))

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
        self.audio_btn = self._menu_button("🔊  Áudio", self._fill_audio_menu)
        self.sub_btn = self._menu_button("💬  Legendas", self._fill_subtitle_menu)
        self.image_btn = QPushButton("🎨  Imagem")
        self.image_btn.setFocusPolicy(Qt.NoFocus)
        self.image_btn.setMenu(self._build_image_menu())
        for w in (self._button("←  Voltar", self.back_requested.emit), self.play_btn,
                  self.elapsed, self.seek, self.total, self.volume,
                  self.audio_btn, self.sub_btn, self.image_btn,
                  self._button("⛶", self.toggle_fullscreen), name):
            row.addWidget(w, 1 if w is self.seek else 0)
        layout.addWidget(self.controls)

    def _button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.NoFocus)   # a barra de espaço é atalho do player, não do botão
        button.clicked.connect(lambda _checked=False: slot())
        return button

    def _menu_button(self, text: str, fill) -> QPushButton:
        button = QPushButton(text)
        button.setFocusPolicy(Qt.NoFocus)
        menu = QMenu(button)
        menu.aboutToShow.connect(lambda m=menu: fill(m))   # a lista é montada na hora de abrir
        button.setMenu(menu)
        return button

    # -- áudio e legendas (faixas que já vêm no arquivo) ---------------------------------
    def _fill_tracks(self, menu: QMenu, tracks, current, choose) -> None:
        menu.clear()
        if not tracks:
            menu.addAction("Nenhuma faixa disponível").setEnabled(False)
            return
        for track_id, name in tracks:
            action = menu.addAction(_track_name(name))
            action.setCheckable(True)
            action.setChecked(track_id == current)
            action.triggered.connect(lambda _checked=False, t=track_id: choose(t))

    def _fill_audio_menu(self, menu: QMenu) -> None:
        self._fill_tracks(menu, self._mp.audio_get_track_description() or [],
                          self._mp.audio_get_track(), self._choose_audio)

    def _fill_subtitle_menu(self, menu: QMenu) -> None:
        self._fill_tracks(menu, self._mp.video_get_spu_description() or [],
                          self._mp.video_get_spu(), self._choose_subtitle)

    def _choose_audio(self, track_id: int) -> None:
        self._chosen_audio = track_id
        self._mp.audio_set_track(track_id)

    def _choose_subtitle(self, track_id: int) -> None:
        self._chosen_spu = track_id
        self._mp.video_set_spu(track_id)

    # -- brilho, contraste, cor e nitidez --------------------------------------------------
    def _build_image_menu(self) -> QMenu:
        menu = QMenu(self.image_btn)
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        self._sliders = {}
        for row, (key, label, low, high, default) in enumerate(_ADJUSTMENTS):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(low, high)
            slider.setValue(default)
            slider.setFixedWidth(190)
            slider.setFocusPolicy(Qt.NoFocus)
            value = QLabel(f"{default}%")
            value.setFixedWidth(42)
            slider.valueChanged.connect(lambda v, k=key, lbl=value: self._on_adjust(k, v, lbl))
            self._sliders[key] = slider
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value, row, 2)
        reset = QPushButton("Restaurar padrão")
        reset.setFocusPolicy(Qt.NoFocus)
        reset.clicked.connect(lambda _checked=False: [
            s.setValue(d) for s, (_k, _l, _lo, _hi, d) in zip(self._sliders.values(), _ADJUSTMENTS)])
        grid.addWidget(reset, len(_ADJUSTMENTS), 0, 1, 3)
        action = QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        return menu

    def _on_adjust(self, key: str, value: int, label: QLabel) -> None:
        label.setText(f"{value}%")
        self._adjust[key] = value
        if key == "sharpness":
            self._sharp_timer.start()
        else:
            self._apply_adjust()

    def _apply_adjust(self) -> None:
        option = self._vlc.VideoAdjustOption
        self._mp.video_set_adjust_int(option.Enable, 1)
        self._mp.video_set_adjust_float(option.Brightness, self._adjust["brightness"] / 100)
        self._mp.video_set_adjust_float(option.Contrast, self._adjust["contrast"] / 100)
        self._mp.video_set_adjust_float(option.Saturation, self._adjust["saturation"] / 100)

    def _open_media(self) -> None:
        """Abre o arquivo; a nitidez usa o filtro 'sharpen' do VLC, que só aceita a força ao abrir."""
        media = self._instance.media_new(self._path)
        sharpness = self._adjust["sharpness"]
        if sharpness > 0:
            media.add_option(":video-filter=sharpen")
            media.add_option(f":sharpen-sigma={sharpness / 50:.2f}")   # 0–100% -> sigma 0–2
        self._sharp_applied = sharpness
        self._playing_seen = False
        self._mp.set_media(media)

    def _apply_sharpness(self) -> None:
        if not self._path or self._adjust["sharpness"] == self._sharp_applied:
            return
        self._pending_start = (max(0, self._mp.get_time()), not self._mp.is_playing())
        self._open_media()   # reabre na mesma posição (há uma pequena pausa)
        self._mp.play()

    # -- reprodução ---------------------------------------------------------------
    def start(self, path: str) -> None:
        self._path = path
        self._open_media()
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

    def _on_playing(self) -> None:
        """Primeiro instante de reprodução (de novo após reabrir por causa da nitidez)."""
        self._apply_adjust()
        if self._pending_start is not None:
            position, paused = self._pending_start
            self._pending_start = None
            self._mp.set_time(position)
            if paused:
                self._mp.set_pause(1)
        if self._chosen_audio is not None:
            self._mp.audio_set_track(self._chosen_audio)
        if self._chosen_spu is not None:
            self._mp.video_set_spu(self._chosen_spu)

    def _tick(self) -> None:
        if not self._playing_seen and self._mp.get_state() == self._vlc.State.Playing:
            self._playing_seen = True
            self._on_playing()
        self._autohide()
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
        self._wake()   # recomeça a contagem; ao sair da tela cheia, tudo volta a aparecer

    # -- esconder controles e ponteiro em tela cheia ---------------------------------------
    def _wake(self) -> None:
        self._last_activity = time.monotonic()
        if self._chrome_hidden:
            self._chrome_hidden = False
            self.controls.show()
            self.unsetCursor()

    def _autohide(self) -> None:
        pos = QCursor.pos()
        if pos != self._last_pos:   # o VLC desenha numa janela própria, então o mouse é lido daqui
            self._last_pos = pos
            self._wake()
        if (not self._fullscreen or self._chrome_hidden
                or time.monotonic() - self._last_activity < IDLE_HIDE_SECONDS
                or QApplication.activePopupWidget() is not None   # menu aberto (áudio, legendas...)
                or self.controls.rect().contains(self.controls.mapFromGlobal(pos))):
            return
        self._chrome_hidden = True
        self.controls.hide()
        self.setCursor(Qt.BlankCursor)

    def _escape(self) -> None:
        if self._fullscreen:
            self._set_fullscreen(False)
        else:
            self.back_requested.emit()

    def leave(self) -> None:
        """Sai da tela cheia e para o vídeo (antes de voltar à tela anterior)."""
        if self._fullscreen:
            self._set_fullscreen(False)
        self._wake()
        self._timer.stop()
        self._sharp_timer.stop()
        self._mp.stop()

    def release(self) -> None:
        self._timer.stop()
        self._sharp_timer.stop()
        self._mp.stop()
        self._mp.release()
