"""Optional libmpv engine for the built-in player: GPU upscaling that adapts itself to the hardware.

It exposes the (small) part of python-vlc that ui/player_page.py uses, so the player page does not change:
`load()` returns the same (module, instance) pair the page gets from VLC. If python-mpv or libmpv are missing,
or fail the probe in `load()`, it returns None and the page keeps using VLC exactly as before.

Upscaling: video smaller than the window is scaled on the GPU with one of the TIERS below. Playback starts on a
cheap tier; while no frame is late or dropped it climbs one tier at a time, and if the GPU cannot keep up it goes
back down and never tries the heavier tier again in this session. A weak GPU therefore settles on a light scaler
and a strong one on the best, with no hardware database.
"""
from __future__ import annotations

import locale
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

# (scale, cscale, dscale, sigmoid-upscaling): cost grows with the index. cscale is the chroma upscaler.
TIERS = (
    ("bilinear", "bilinear", "hermite", False),
    ("spline36", "bilinear", "mitchell", False),
    ("ewa_lanczos", "spline36", "mitchell", False),
    ("ewa_lanczossharp", "ewa_lanczossharp", "mitchell", True),
)
START_TIER = 1
# Quality profiles of Settings > Upscaling: (highest tier allowed, tier to start on or None = what this session learned).
# "auto" (shown as Balanced) is the behaviour the player always had: start light, climb while playback is smooth.
PROFILES = {
    "economy": (1, None),               # never leaves spline36: the lightest good scaler
    "auto": (len(TIERS) - 1, None),
    "high": (len(TIERS) - 1, len(TIERS) - 1),   # starts on the best scaler and steps back if frames are dropped
}
DIAG_ENV = "CINELOCAL_PLAYER_LOG"   # path of a text file: when set, one line of measurements is appended per sample
ADAPT_EVERY = 2.0      # seconds between two samples of the frame counters
CLIMB_AFTER = 15.0     # seconds without late/dropped frames before trying the next tier
DROP_LIMIT = 3         # late or dropped frames within one sample that mean "this tier is too heavy"
MIN_UPSCALE = 1.05     # the picture must be at least 5% larger than the video for the tier to matter

_learned = {"start": START_TIER, "ceiling": len(TIERS) - 1}   # shared by every movie of this session
_profile = "auto"
_engine = None
_failed = False
_reason = ""      # why libmpv could not be used (shown in Settings)


class State:
    """Same values as vlc.State (only the members the player page compares against matter)."""
    NothingSpecial, Opening, Buffering, Playing, Paused, Stopped, Ended, Error = range(8)


class VideoAdjustOption:
    Enable, Brightness, Contrast, Saturation, Hue, Gamma = range(6)


class MediaSlaveType:
    subtitle, audio = range(2)


class _Media:
    def __init__(self, path: str):
        self.path = path
        self.options: list[str] = []

    def add_option(self, option: str) -> None:
        self.options.append(option)


def set_profile(name: str) -> None:
    """Chooses the quality profile for the players created from now on (unknown names mean \"auto\")."""
    global _profile
    _profile = name if name in PROFILES else "auto"


def _options(extra: dict | None = None) -> dict:
    """Options of the mpv core. The window id is added by the player; `extra` is for tests."""
    opts = {
        "input_default_bindings": False, "input_vo_keyboard": False, "input_cursor": False,
        "osc": False, "osd_level": 0, "cursor_autohide": "no",   # keyboard, mouse and controls stay with Qt
        "keep_open": "yes",            # at the end it pauses on the last frame (that is how the end is detected)
        "idle": "yes", "ytdl": False, "hwdec": "auto-safe", "volume_max": 200,
        "gpu_sw": "yes",   # without it mpv refuses software GL (VMs, bad drivers) and falls back to a VO that does not scale
        "sub_auto": "fuzzy", "audio_display": "no",
    }
    opts.update(extra or {})
    return opts


def _use_bundled_mpv() -> None:
    """Windows: lets python-mpv find the DLL, either bundled by cinelocal.spec in the packaged build, or downloaded
    by install.bat / packaging/fetch_libmpv.py into the `libmpv` folder next to the app."""
    if sys.platform != "win32":
        return
    roots = [Path(__file__).resolve().parent.parent / "libmpv"]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(getattr(sys, "_MEIPASS", "")))
    for root in roots:
        if (root / "libmpv-2.dll").is_file() or (root / "mpv-2.dll").is_file():
            os.add_dll_directory(str(root))
            os.environ["PATH"] = str(root) + os.pathsep + os.environ.get("PATH", "")
            return


def _new_core(**opts):
    import mpv
    locale.setlocale(locale.LC_NUMERIC, "C")   # libmpv refuses to start otherwise (Qt changes the locale)
    return mpv.MPV(**opts)


class _Player:
    """Plays one movie in a native window (the same one the page gives to VLC)."""

    def __init__(self, extra: dict | None = None, profile: str = "auto"):
        self._extra = extra
        self._max_tier, self._forced = PROFILES.get(profile, PROFILES["auto"])
        self._m = None                 # the mpv core, created at the first play() (it needs the window id)
        self._wid = None
        self._media = None
        self._loaded = False
        self._released = False
        self._props: dict[str, object] = {}   # volume, picture, speed...: kept to survive reopening the file
        self._tier = min(self._ceiling(), _learned["start"] if self._forced is None else self._forced)
        self._sample_at = 0.0
        self._counted = None           # late+dropped frames at the last sample (None = start over)
        self._clean_since = time.monotonic()

    def _ceiling(self) -> int:
        """Heaviest tier allowed: by the profile, and by what this GPU proved it can afford in this session."""
        return min(self._max_tier, _learned["ceiling"])

    # -- low level: errors from a core that is closing or has nothing loaded are not the player's business --------
    def _get(self, name: str, default=None):
        if self._m is None:
            return default
        try:
            value = getattr(self._m, name)
        except Exception:  # noqa: BLE001 - property unavailable, or the core is shutting down
            return default
        return default if value is None else value

    def _set(self, name: str, value, remember: bool = False) -> None:
        if remember:
            self._props[name] = value
        if self._m is None:
            return
        try:
            self._m.command("set", name, "yes" if value is True else "no" if value is False else str(value))
        except Exception:  # noqa: BLE001 - option unknown in this libmpv version, or nothing loaded
            pass

    def _cmd(self, *args) -> None:
        if self._m is None:
            return
        try:
            self._m.command(*args)
        except Exception:  # noqa: BLE001
            pass

    def _core(self):
        if self._m is None and not self._released:
            opts = _options(self._extra)
            if self._wid is not None:
                opts["wid"] = str(self._wid)
            self._m = _new_core(**opts)
            self._apply_tier()
            for name, value in self._props.items():
                self._set(name, value)
        return self._m

    # -- window --------------------------------------------------------------------------------------------------
    def set_xwindow(self, wid) -> None:
        self._wid = wid

    set_hwnd = set_nsobject = set_xwindow

    def video_set_mouse_input(self, _on) -> None:   # already off in _options
        pass

    video_set_key_input = video_set_mouse_input

    # -- playback ------------------------------------------------------------------------------------------------
    def set_media(self, media: _Media) -> None:
        self._media, self._loaded = media, False
        sigma = next((float(o.split("=", 1)[1]) for o in media.options if o.startswith(":sharpen-sigma=")), None)
        # the page's sharpness slider (VLC sigma 0.2-2.0) becomes mpv's GPU unsharp mask (0-1); 0 = off
        self._set("sharpen", 0 if sigma is None else round((sigma - 0.2) / 1.8, 2), remember=True)

    def play(self) -> int:
        if self._media is None or self._core() is None:
            return -1
        self._set("pause", False)
        if not self._loaded:
            self._loaded = True
            self._counted = None
            self._cmd("loadfile", self._media.path, "replace")
        return 0

    def pause(self) -> None:
        self._set("pause", not self._get("pause", False))

    def set_pause(self, paused) -> None:
        self._set("pause", bool(paused))

    def stop(self) -> None:
        self._loaded = False
        self._cmd("stop")

    def release(self) -> None:
        self._released, m, self._m = True, self._m, None
        if m is not None:
            try:
                m.terminate()
            except Exception:  # noqa: BLE001
                pass

    def get_state(self) -> int:
        if self._m is None or not self._loaded:
            return State.Stopped
        self._adapt()
        if self._get("eof_reached", False):
            return State.Ended
        if self._get("idle_active", False):
            return State.Error
        if self._get("pause", False):
            return State.Paused
        return State.Buffering if self._get("core_idle", True) else State.Playing

    def is_playing(self) -> bool:
        return (self._loaded and not self._get("eof_reached", False) and not self._get("idle_active", False)
                and not self._get("pause", False))

    def get_time(self) -> int:
        return int(self._get("time_pos", 0) * 1000)

    def get_length(self) -> int:
        return int(self._get("duration", 0) * 1000)

    def get_position(self) -> float:
        return min(1.0, max(0.0, self._get("percent_pos", 0) / 100))

    def set_time(self, ms: int) -> None:
        self._cmd("seek", ms / 1000, "absolute+exact")

    def set_position(self, fraction: float) -> None:
        self._cmd("seek", fraction * 100, "absolute-percent+exact")

    def set_rate(self, rate: float) -> int:
        self._set("speed", rate, remember=True)
        return 0

    # -- audio ---------------------------------------------------------------------------------------------------
    def audio_set_volume(self, volume: int) -> int:
        self._set("volume", volume, remember=True)
        return 0

    def audio_toggle_mute(self) -> None:
        self._set("mute", not self._get("mute", False))

    # -- tracks (ids are mpv's per-type ids; -1 = off, like VLC's "Disable" entry) ------------------------------
    def _descriptions(self, kind: str) -> list:
        found = [(-1, b"Disable")]
        for t in self._get("track_list", []):
            if t.get("type") != kind:
                continue
            # "Track 2 - [por] title Forced": the words are what tracks.py matches languages and "forced" against
            name = f"Track {t['id']}" + (f" - [{t['lang']}]" if t.get("lang") else "")
            name += (f" {t['title']}" if t.get("title") else "") + (" Forced" if t.get("forced") else "")
            found.append((t["id"], name.encode("utf-8")))
        return found

    def _current(self, prop: str) -> int:
        value = self._get(prop, -1)
        return value if isinstance(value, int) and not isinstance(value, bool) else -1

    def audio_get_track_description(self) -> list:
        return self._descriptions("audio")

    def video_get_spu_description(self) -> list:
        return self._descriptions("sub")

    def audio_get_track(self) -> int:
        return self._current("aid")

    def video_get_spu(self) -> int:
        return self._current("sid")

    def audio_set_track(self, track_id: int) -> int:
        self._set("aid", "no" if track_id < 0 else track_id)
        return 0

    def video_set_spu(self, track_id: int) -> int:
        self._set("sid", "no" if track_id < 0 else track_id)
        return 0

    def video_set_spu_delay(self, microseconds: int) -> int:
        self._set("sub-delay", microseconds / 1_000_000, remember=True)
        return 0

    def add_slave(self, _kind, uri: str, select: bool) -> int:
        self._cmd("sub-add", url2pathname(urlparse(uri).path), "select" if select else "auto")
        return 0

    # -- picture (VLC: brightness/contrast 0-2 and saturation 0-3, 1 = unchanged; mpv: -100..100, 0 = unchanged) ---
    def video_set_adjust_int(self, _option, _value) -> int:   # "Enable": mpv always applies them
        return 0

    def video_set_adjust_float(self, option: int, value: float) -> int:
        name = {VideoAdjustOption.Brightness: "brightness", VideoAdjustOption.Contrast: "contrast",
                VideoAdjustOption.Saturation: "saturation"}.get(option)
        if name:
            self._set(name, max(-100, min(100, round((value - 1) * 100))), remember=True)
        return 0

    # -- upscaling -----------------------------------------------------------------------------------------------
    def _apply_tier(self) -> None:
        scale, cscale, dscale, sigmoid = TIERS[self._tier]
        for name, value in (("scale", scale), ("cscale", cscale), ("dscale", dscale), ("sigmoid-upscaling", sigmoid)):
            self._set(name, value)
        if self._forced is None:   # a profile that starts on a fixed tier must not change where the others start
            _learned["start"] = self._tier

    def _upscaling(self) -> bool:
        """Is the video being enlarged right now? (otherwise the tier changes nothing and drops mean other things)"""
        window, video = self._get("osd_dimensions", {}), self._get("video_params", {})
        try:
            return min(window["w"] / video["dw"], window["h"] / video["dh"]) > MIN_UPSCALE
        except (KeyError, TypeError, ZeroDivisionError):
            return False

    def _log_diagnostics(self, late) -> None:
        """Opt-in (environment variable CINELOCAL_PLAYER_LOG=<file>): appends what libmpv is really doing, to measure
        a tier on a given machine. Does nothing, and costs nothing, when the variable is not set."""
        path = os.environ.get(DIAG_ENV)
        if not path:
            return
        video, window = self._get("video_params", {}) or {}, self._get("osd_dimensions", {}) or {}
        fields = (("mpv", self._get("mpv_version", "?")), ("vo", self._get("current_vo", "?")),
                  ("hwdec", self._get("hwdec_current", "?")), ("tier", f"{self._tier}:{TIERS[self._tier][0]}"),
                  ("video", f"{video.get('dw', '?')}x{video.get('dh', '?')}"),
                  ("window", f"{window.get('w', '?')}x{window.get('h', '?')}"),
                  ("late_in_sample", "?" if late is None else late),
                  ("dropped", self._get("frame_drop_count", 0)), ("vo_delayed", self._get("vo_delayed_frame_count", 0)),
                  ("decoder_dropped", self._get("decoder_frame_drop_count", 0)))
        line = time.strftime("%H:%M:%S ") + " ".join(f"{k}={str(v).replace(' ', '-')}" for k, v in fields)
        try:
            with open(path, "a", encoding="utf-8") as log:
                log.write(line + "\n")
        except OSError:
            pass   # a log that cannot be written must never disturb playback

    def _adapt(self) -> None:
        """Called by get_state() (the page polls it 4x per second): climbs or drops one tier by what was measured."""
        now = time.monotonic()
        if now - self._sample_at < ADAPT_EVERY:
            return
        self._sample_at = now
        if self._get("pause", False) or self._get("core_idle", True) or self._get("eof_reached", False):
            self._counted, self._clean_since = None, now   # paused, seeking or ending: the counters mean nothing
            return
        total = self._get("frame_drop_count", 0) + self._get("vo_delayed_frame_count", 0)
        late, self._counted = (None if self._counted is None else total - self._counted), total
        self._log_diagnostics(late)
        if late is None or not self._upscaling():
            self._clean_since = now
        elif late >= DROP_LIMIT:
            self._clean_since = now
            if self._tier > 0:
                self._tier -= 1
                _learned["ceiling"] = self._tier   # that GPU cannot afford the heavier tier: do not try it again
                self._apply_tier()
        elif now - self._clean_since >= CLIMB_AFTER and self._tier < self._ceiling():
            self._clean_since = now
            self._tier += 1
            self._apply_tier()


class _Engine:
    """Plays the role of both the `vlc` module and the `vlc.Instance` the page receives from VLC."""
    State = State
    VideoAdjustOption = VideoAdjustOption
    MediaSlaveType = MediaSlaveType

    def media_player_new(self) -> _Player:
        return _Player(profile=_profile)

    def media_new(self, path: str) -> _Media:
        return _Media(path)


def load():
    """(engine, engine) in the shape of the page's (vlc module, Instance), or None if libmpv cannot be used here."""
    global _engine, _failed, _reason
    if _engine is None and not _failed:
        try:
            _use_bundled_mpv()
            _new_core(**_options({"vo": "null", "ao": "null"})).terminate()   # the real options, no window
            _engine = _Engine()
        except (Exception, SystemExit) as e:  # noqa: BLE001 - python-mpv or libmpv missing, or an option this libmpv lacks
            _failed, _reason = True, f"{type(e).__name__}: {e}".splitlines()[0][:120]
    return (_engine, _engine) if _engine else None


def unavailable_reason() -> str:
    """'' if libmpv can be used here, otherwise why not (the first call loads it)."""
    load()
    return "" if _engine else _reason
