"""Built-in player, based on libVLC (python-vlc). Appears inside the main window."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeySequence, QLinearGradient, QPainter, QShortcut
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSizePolicy, QSlider, QStyle, QToolTip, QVBoxLayout, QWidget, QWidgetAction)

from ..tracks import choose_track, track_name as _track_name
from .icons import IconButton

SAVE_EVERY_MS = 5000      # how often the playback position is saved
PREFS_DELAY_MS = 800       # waits for volume/adjustments to stop changing before saving
FINISH_FRACTION = 0.95    # from here on the movie counts as watched
RATES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)   # playback speeds
SPU_STEP_US = 250_000     # subtitle delay step (microseconds)
ICON_BOX = 46             # side (px) of the square icon buttons (play, settings, fullscreen)
FADE_MS = 500             # duration of the controls' fade-out
IDLE_HIDE_SECONDS = 2.5   # in fullscreen, controls and pointer disappear after this much idle time
SHADE_ALPHA = 200         # in fullscreen the bars float over the video, on a gradient that fades into the picture
# key, label, minimum, maximum, default (in %). Sharpness 0 = filter off.
_ADJUSTMENTS = (("brightness", "Brightness", 0, 200, 100), ("contrast", "Contrast", 0, 200, 100),
                ("saturation", "Color", 0, 300, 100), ("sharpness", "Sharpness", 0, 100, 0))

_vlc = None      # (vlc module, Instance) after the first successful load
_error = ""      # reason for the failure (kept so we don't try again)


def _use_bundled_vlc() -> None:
    """In the packaged executable, points python-vlc and libVLC to the copy bundled by cinelocal.spec."""
    root = Path(getattr(sys, "_MEIPASS", ""))
    lib = root / ("libvlc.dll" if sys.platform == "win32" else "libvlc.so.5")
    if getattr(sys, "frozen", False) and lib.is_file():
        os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(lib))
        os.environ.setdefault("VLC_PLUGIN_PATH", str(root / "vlc" / "plugins"))


def unavailable_reason() -> str:
    """Why the built-in player cannot be used ('' = it can)."""
    global _vlc, _error
    if sys.platform.startswith("linux") and QGuiApplication.platformName() != "xcb":
        return "The built-in player needs X11 or XWayland (no X server found for this session)."
    if _vlc is None and not _error:
        try:
            _use_bundled_vlc()
            import vlc
            instance = vlc.Instance()
            if instance is None:
                raise RuntimeError("libVLC")
            _vlc = (vlc, instance)
        except Exception:  # noqa: BLE001 - python-vlc or libVLC missing
            _error = "libVLC not found. Install VLC (and the python-vlc package) to use the built-in player."
    return _error


def _clock(ms: int) -> str:
    hours, rest = divmod(max(0, ms) // 1000, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class _SeekSlider(QSlider):
    length_ms = 0   # movie duration, updated by the player

    def __init__(self, *args):
        super().__init__(*args)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event) -> None:   # shows the time at the point under the mouse
        if self.length_ms > 0:
            value = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width())
            QToolTip.showText(event.globalPosition().toPoint(),
                              _clock(self.length_ms * value // self.maximum()), self)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:   # clicking the bar jumps to the clicked point
            self.setValue(QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width()))
            self.sliderMoved.emit(self.value())
        super().mousePressEvent(event)


class _Bar(QWidget):
    """Top or bottom bar. Floating over the video (a translucent window) it paints its own gradient replacing
    whatever was there (CompositionMode_Source); otherwise partial repaints (clock, play icon) would pile up on
    the old pixels and the icons would overlap."""

    def __init__(self, bottom: bool):
        super().__init__()
        self.bottom, self.floating = bottom, False
        self.setAttribute(Qt.WA_StyledBackground)

    def paintEvent(self, event) -> None:
        if not self.floating:
            return super().paintEvent(event)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(0, 0, 0, 0 if self.bottom else SHADE_ALPHA))
        gradient.setColorAt(1, QColor(0, 0, 0, SHADE_ALPHA if self.bottom else 0))
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(event.rect(), gradient)


class VlcPlayerPage(QWidget):
    back_requested = Signal()
    external_requested = Signal()     # open this movie in another player
    next_requested = Signal()         # play the next episode (series only)
    progress = Signal(str, int, int)  # path, position (ms), duration (ms); position 0 = clear
    finished = Signal(str)            # passed 95%: mark as watched
    ended = Signal(str)               # the video reached the end
    tracks_remembered = Signal(str, dict)   # path, audio/subtitle track names picked by hand
    prefs_changed = Signal(dict)      # volume and picture adjustments, to remember for the next movies

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._vlc, self._instance = _vlc
        self._mp = self._instance.media_player_new()
        self._dragging = False
        self._fullscreen = False
        self._path = ""
        self._adjust = {key: default for key, _l, _lo, _hi, default in _ADJUSTMENTS}
        self._sharp_applied = 0          # sharpness (%) the current media was opened with
        self._pending_start = None       # (position in ms, paused?) to restore after reopening the media
        self._playing_seen = False
        self._chosen_audio = self._chosen_spu = None
        self._want_audio = self._want_spu = ""   # preferred languages from the settings
        self._lang_tries = 0             # ticks left to look for those tracks
        self._saved = {}                 # tracks picked by hand for this file in an earlier session
        self._chrome_hidden = False
        self._last_pos = QCursor.pos()
        self._last_activity = time.monotonic()
        self._last_saved = 0
        self._rate = 1.0
        self._spu_delay = 0              # subtitle delay (µs)
        self._finished_sent = self._ended_sent = False
        self._loading_prefs = False
        self._prefs_timer = QTimer(self, singleShot=True, interval=PREFS_DELAY_MS)
        self._prefs_timer.timeout.connect(self._emit_prefs)
        self._build(title)
        self._timer = QTimer(self, interval=250)
        self._timer.timeout.connect(self._tick)
        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setDuration(FADE_MS)
        self._fade.valueChanged.connect(self._set_chrome_opacity)
        self._fade.finished.connect(self._finish_fade)
        self._sharp_timer = QTimer(self, singleShot=True, interval=600)   # waits for the slider to stop
        self._sharp_timer.timeout.connect(self._apply_sharpness)
        for keys, action in (("Space", self.toggle_pause), ("F", self.toggle_fullscreen),
                             ("M", self._mp.audio_toggle_mute), ("Esc", self._escape),
                             ("Left", lambda: self._jump(-10000)), ("Right", lambda: self._jump(10000)),
                             ("Up", lambda: self.volume.setValue(self.volume.value() + 5)),
                             ("Down", lambda: self.volume.setValue(self.volume.value() - 5))):
            QShortcut(QKeySequence(keys), self, activated=lambda a=action: (self._wake(), a()))

    # -- construction ---------------------------------------------------------------
    def _build(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.topbar = _Bar(bottom=False)          # back on the left (same place as the details screen), title in the center
        self.topbar.setObjectName("page")
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(34, 20, 34, 10)
        back = self._svg_button("back", self.back_requested.emit, "plainIcon")
        back.setToolTip("Back (Esc)")
        name = self.title_label = QLabel(title)
        name.setObjectName("muted")
        name.setAlignment(Qt.AlignCenter)
        top.addWidget(back, 0, Qt.AlignLeft)
        top.addWidget(name, 1)
        top.addSpacing(back.sizeHint().width())   # balances the button so the title stays centered
        layout.addWidget(self.topbar)

        self.video = QWidget()
        self.video.setAttribute(Qt.WA_NativeWindow)    # VLC draws in this window
        self.video.setAttribute(Qt.WA_StyledBackground)
        self.video.setStyleSheet("background: #000;")
        self.video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.video, 1)

        self.controls = _Bar(bottom=True)
        self.controls.setObjectName("page")
        row = QHBoxLayout(self.controls)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)
        self.play_btn = self._svg_button("pause", self.toggle_pause)
        self.play_btn.setToolTip("Pause / play (Space)")
        self.next_btn = self._svg_button("next", self.next_requested.emit)   # shown only for series episodes
        self.next_btn.setToolTip("Next episode")
        self.next_btn.hide()
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
        self.volume_label = QLabel("100%")
        self.volume_label.setFixedWidth(42)
        self.volume.valueChanged.connect(lambda v: self.volume_label.setText(f"{v}%"))
        self.volume.valueChanged.connect(lambda _v: self._prefs_changed())
        self.settings_btn = self._svg_button("settings", None)      # audio, subtitles and picture all live here
        self.settings_btn.setToolTip("Settings")
        self.fullscreen_btn = self._svg_button("fullscreen", self.toggle_fullscreen)
        self.fullscreen_btn.setToolTip("Fullscreen (F)")
        menu = QMenu(self.settings_btn)
        for text, fill in (("Audio", self._fill_audio_menu), ("Subtitles", self._fill_subtitle_menu),
                           ("Subtitle delay", self._fill_delay_menu),
                           ("Speed", self._fill_speed_menu)):
            sub = menu.addMenu(text)
            sub.aboutToShow.connect(lambda m=sub, f=fill: f(m))   # the list is built when the menu opens
        self._build_image_menu(menu.addMenu("Picture"))
        menu.addSeparator()
        menu.addAction("Open in another player", lambda: self.external_requested.emit())
        self.settings_btn.setMenu(menu)
        for w in (self.play_btn, self.next_btn, self.elapsed, self.seek, self.total, self.volume, self.volume_label,
                  self.settings_btn, self.fullscreen_btn):
            row.addWidget(w, 1 if w is self.seek else 0)
        layout.addWidget(self.controls)

    def _svg_button(self, icon: str, slot, object_name: str = "iconBtn") -> IconButton:
        button = IconButton(icon, object_name=object_name, box=ICON_BOX)
        button.setFocusPolicy(Qt.NoFocus)   # the space bar is a player shortcut, not the button's
        if slot:
            button.clicked.connect(lambda _checked=False: slot())
        return button

    # -- audio and subtitles (tracks already in the file) ---------------------------------
    def _fill_tracks(self, menu: QMenu, tracks, current, choose) -> None:
        menu.clear()
        if not tracks:
            menu.addAction("No tracks available").setEnabled(False)
            return
        for track_id, name in tracks:
            action = menu.addAction(_track_name(name))
            action.setCheckable(True)
            action.setChecked(track_id == current)
            action.triggered.connect(lambda _checked=False, t=track_id: choose(t))

    def _fill_audio_menu(self, menu: QMenu) -> None:
        self._fill_tracks(menu, self._mp.audio_get_track_description() or [],
                          self._mp.audio_get_track(), self._pick_audio)

    def _fill_subtitle_menu(self, menu: QMenu) -> None:
        self._fill_tracks(menu, self._mp.video_get_spu_description() or [],
                          self._mp.video_get_spu(), self._pick_subtitle)

    def set_track_languages(self, audio: str, subtitles: str) -> None:
        """Preferred audio and subtitle languages ('' = file default, subtitles also 'off')."""
        self._want_audio, self._want_spu = audio or "", subtitles or ""
        self._lang_tries = 40 if (self._want_audio or self._want_spu) else 0

    def set_saved_tracks(self, saved: dict) -> None:
        """Tracks picked by hand the last time this file played; they win over the language settings."""
        self._saved = dict(saved or {})
        if self._saved:
            self._lang_tries = 40

    def _apply_track_languages(self) -> None:
        """Picks the remembered/preferred tracks once VLC lists them (never overrides a choice made now)."""
        done = True
        for kind, tracks, chosen, language, choose in (
                ("audio", self._mp.audio_get_track_description(), self._chosen_audio,
                 self._want_audio, self._choose_audio),
                ("spu", self._mp.video_get_spu_description(), self._chosen_spu,
                 self._want_spu, self._choose_subtitle)):
            if chosen is not None or not (self._saved.get(kind) or language):
                continue
            track, final = choose_track(tracks, self._saved.get(kind, ""), language, self._want_audio)
            if track is not None:
                choose(track)
            elif not final:
                done = False
        self._lang_tries = self._lang_tries - 1 if not done else 0

    def _remember_track(self, kind: str, track_id: int) -> None:
        tracks = (self._mp.audio_get_track_description() if kind == "audio"
                  else self._mp.video_get_spu_description()) or []
        name = next((_track_name(n) for t, n in tracks if t == track_id), None)
        if name is not None and self._path:
            self._saved[kind] = name
            self.tracks_remembered.emit(self._path, dict(self._saved))

    def _pick_audio(self, track_id: int) -> None:   # chosen from the menu
        self._choose_audio(track_id)
        self._remember_track("audio", track_id)

    def _pick_subtitle(self, track_id: int) -> None:
        self._choose_subtitle(track_id)
        self._remember_track("spu", track_id)

    def _choose_audio(self, track_id: int) -> None:
        self._chosen_audio = track_id
        self._mp.audio_set_track(track_id)

    def _choose_subtitle(self, track_id: int) -> None:
        self._chosen_spu = track_id
        self._mp.video_set_spu(track_id)

    # -- speed and subtitle delay ---------------------------------------------------
    def _fill_speed_menu(self, menu: QMenu) -> None:
        menu.clear()
        for rate in RATES:
            action = menu.addAction(f"{rate:g}x" + ("  (normal)" if rate == 1.0 else ""))
            action.setCheckable(True)
            action.setChecked(abs(rate - self._rate) < 1e-6)
            action.triggered.connect(lambda _checked=False, r=rate: self._set_rate(r))

    def _set_rate(self, rate: float) -> None:
        self._rate = rate
        self._mp.set_rate(rate)

    def _fill_delay_menu(self, menu: QMenu) -> None:
        menu.clear()
        menu.addAction(f"Current delay: {self._spu_delay // 1000:+d} ms").setEnabled(False)
        menu.addAction("Subtitles earlier (−250 ms)", lambda: self._shift_delay(-SPU_STEP_US))
        menu.addAction("Subtitles later (+250 ms)", lambda: self._shift_delay(SPU_STEP_US))
        menu.addAction("Reset", lambda: self._shift_delay(None))

    def _shift_delay(self, delta) -> None:
        self._spu_delay = 0 if delta is None else self._spu_delay + delta
        self._mp.video_set_spu_delay(self._spu_delay)

    # -- remember volume and picture adjustments between movies -----------------------------------
    def apply_prefs(self, prefs: dict) -> None:
        self._loading_prefs = True
        try:
            for key, slider in self._sliders.items():
                if key in prefs:
                    slider.setValue(int(prefs[key]))
            if "volume" in prefs:
                self.volume.setValue(int(prefs["volume"]))
        except (TypeError, ValueError):
            pass
        finally:
            self._loading_prefs = False

    def _prefs_changed(self) -> None:
        if not self._loading_prefs:
            self._prefs_timer.start()

    def _emit_prefs(self) -> None:
        self.prefs_changed.emit({**self._adjust, "volume": self.volume.value()})

    def _flush_prefs(self) -> None:
        if self._prefs_timer.isActive():
            self._prefs_timer.stop()
            self._emit_prefs()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_has_next(self, available: bool) -> None:
        self.next_btn.setVisible(available)

    # -- brightness, contrast, color and sharpness --------------------------------------------------
    def _build_image_menu(self, menu: QMenu) -> None:
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
        reset = QPushButton("Restore defaults")
        reset.setFocusPolicy(Qt.NoFocus)
        reset.clicked.connect(lambda _checked=False: [
            s.setValue(d) for s, (_k, _l, _lo, _hi, d) in zip(self._sliders.values(), _ADJUSTMENTS)])
        grid.addWidget(reset, len(_ADJUSTMENTS), 0, 1, 3)
        action = QWidgetAction(menu)
        action.setDefaultWidget(panel)
        menu.addAction(action)

    def _on_adjust(self, key: str, value: int, label: QLabel) -> None:
        label.setText(f"{value}%")
        self._adjust[key] = value
        self._prefs_changed()
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
        """Opens the file; sharpness uses VLC's 'sharpen' filter, which only accepts its strength at open time."""
        media = self._instance.media_new(self._path)
        sharpness = self._adjust["sharpness"]
        if sharpness > 0:
            media.add_option(":avcodec-hw=none")   # GPU decoding ignores video filters
            media.add_option(":video-filter=sharpen")
            media.add_option(f":sharpen-sigma={0.2 + sharpness * 0.018:.2f}")   # 1–100% -> sigma 0.2–2.0
        self._sharp_applied = sharpness
        self._playing_seen = False
        self._mp.set_media(media)

    def _apply_sharpness(self) -> None:
        if not self._path or self._adjust["sharpness"] == self._sharp_applied:
            return
        self._pending_start = (max(0, self._mp.get_time()), not self._mp.is_playing())
        self._open_media()   # reopens at the same position (there is a short pause)
        self._mp.play()

    # -- playback ---------------------------------------------------------------
    def start(self, path: str, resume_ms: int = 0) -> None:
        if self._path:
            self._save_progress()   # switching episodes: keeps where the previous one stopped
        self._path = path
        self._finished_sent = self._ended_sent = False
        if resume_ms > 0:
            self._pending_start = (resume_ms, False)   # applied when playback starts
        self._open_media()
        handle = int(self.video.winId())
        if sys.platform.startswith("linux"):
            self._mp.set_xwindow(handle)
        elif sys.platform == "win32":
            self._mp.set_hwnd(handle)
        elif sys.platform == "darwin":
            self._mp.set_nsobject(handle)
        self._mp.video_set_mouse_input(False)   # keyboard and mouse stay with Qt
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
        """First moment of playback (again after reopening because of sharpness)."""
        self._apply_adjust()
        self._mp.audio_set_volume(self.volume.value())
        if self._rate != 1.0:
            self._mp.set_rate(self._rate)
        if self._spu_delay:
            self._mp.video_set_spu_delay(self._spu_delay)
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
        if self._lang_tries and self._playing_seen:
            self._apply_track_languages()
        self._autohide()
        length = self._mp.get_length()
        if length > 0:
            self.seek.length_ms = length
            self.total.setText(_clock(length))
            self.elapsed.setText(_clock(self._mp.get_time()))
            if not self._dragging:
                self.seek.setValue(int(self._mp.get_position() * 1000))
        self.play_btn.set_icon("pause" if self._mp.is_playing() else "play")
        now = time.monotonic()
        if now - self._last_saved >= SAVE_EVERY_MS / 1000:
            self._last_saved = now
            self._save_progress()
        if (self._playing_seen and not self._ended_sent
                and self._mp.get_state() == self._vlc.State.Ended):
            self._ended_sent = True
            self._save_progress()   # ensures the 'watched' notice
            self.ended.emit(self._path)

    def _save_progress(self) -> None:
        """Reports the current position (or 0, near the end) so the movie can be resumed later."""
        state = self._mp.get_state()
        if not self._playing_seen or self._pending_start is not None:
            return
        length, pos = self._mp.get_length(), self._mp.get_time()
        if state == self._vlc.State.Ended or (length > 0 and pos >= length * FINISH_FRACTION):
            self.progress.emit(self._path, 0, length)
            if not self._finished_sent:
                self._finished_sent = True
                self.finished.emit(self._path)
        elif state in (self._vlc.State.Playing, self._vlc.State.Paused) and pos > 0:
            self.progress.emit(self._path, pos, length)

    # -- fullscreen / exit ---------------------------------------------------------
    def toggle_fullscreen(self) -> None:
        self._set_fullscreen(not self._fullscreen)

    def _set_fullscreen(self, on: bool) -> None:
        window = self.window()
        self._fullscreen = on
        window.statusBar().setVisible(not on)
        window.showFullScreen() if on else window.showNormal()
        self._float_bars(on)
        self._wake()   # restarts the countdown; when leaving fullscreen, everything shows again

    # -- bars over the video (fullscreen) ------------------------------------------------
    def _float_bars(self, on: bool) -> None:
        """Fullscreen: the bars leave the layout and become translucent windows above the video (which
        VLC draws in its own native window, so ordinary child widgets could not overlap it). Windowed: back."""
        layout = self.layout()
        for widget in (self.topbar, self.controls):
            layout.removeWidget(widget)
            if on:
                widget.setParent(self.window(), Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
            else:
                widget.setParent(self, Qt.Widget)
            widget.setAttribute(Qt.WA_TranslucentBackground, on)
            widget.setAttribute(Qt.WA_ShowWithoutActivating, on)
            widget.floating = on
            widget.setStyleSheet("#page { background: transparent; }" if on else "")
            widget.setWindowOpacity(1.0)
        if not on:
            layout.insertWidget(0, self.topbar)
            layout.addWidget(self.controls)
        self._place_bars()
        self.topbar.show()
        self.controls.show()

    def _place_bars(self) -> None:
        if not self._fullscreen:
            return
        origin, width = self.video.mapToGlobal(QPoint(0, 0)), self.video.width()
        top, bottom = self.topbar.sizeHint().height(), self.controls.sizeHint().height()
        for widget, rect in ((self.topbar, QRect(origin.x(), origin.y(), width, top)),
                             (self.controls, QRect(origin.x(), origin.y() + self.video.height() - bottom,
                                                   width, bottom))):
            if widget.geometry() != rect:
                widget.setGeometry(rect)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_bars()

    # -- hide controls and pointer in fullscreen ---------------------------------------
    def _wake(self) -> None:
        self._last_activity = time.monotonic()
        if self._chrome_hidden:
            self._chrome_hidden = False
            self._cancel_fade()
            self.controls.show()
            self.topbar.show()
            self.unsetCursor()

    def _autohide(self) -> None:
        self._place_bars()
        pos = QCursor.pos()
        if pos != self._last_pos:   # VLC draws in its own window, so the mouse is read from here
            self._last_pos = pos
            self._wake()
        if (not self._fullscreen or self._chrome_hidden
                or time.monotonic() - self._last_activity < IDLE_HIDE_SECONDS
                or QApplication.activePopupWidget() is not None   # menu open (audio, subtitles...)
                or self.controls.rect().contains(self.controls.mapFromGlobal(pos))
                or self.topbar.rect().contains(self.topbar.mapFromGlobal(pos))):
            return
        self._chrome_hidden = True
        self._fade.start()

    def _set_chrome_opacity(self, value) -> None:
        for w in (self.topbar, self.controls):
            w.setWindowOpacity(float(value))
            w.update()   # translucent windows (Windows) only apply the opacity when repainted

    def _finish_fade(self) -> None:
        for w in (self.topbar, self.controls):
            w.hide()
            w.setWindowOpacity(1.0)
        self.setCursor(Qt.BlankCursor)

    def _cancel_fade(self) -> None:
        self._fade.stop()
        for w in (self.topbar, self.controls):
            w.setWindowOpacity(1.0)
            w.update()

    def _escape(self) -> None:
        if self._fullscreen:
            self._set_fullscreen(False)
        else:
            self.back_requested.emit()

    def leave(self) -> None:
        """Leaves fullscreen and stops the video (before going back to the previous screen)."""
        if self._fullscreen:
            self._set_fullscreen(False)
        self._wake()
        self._save_progress()
        self._flush_prefs()
        self._timer.stop()
        self._sharp_timer.stop()
        self._mp.stop()

    def release(self) -> None:
        self._save_progress()   # no-op if leave() already stopped the video (e.g. app closed during playback)
        self._flush_prefs()
        self._timer.stop()
        self._sharp_timer.stop()
        self._mp.stop()
        self._mp.release()
