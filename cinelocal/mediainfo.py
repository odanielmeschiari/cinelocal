"""Technical info of a video file (resolution, codecs, audio channels) read with libVLC, and its badges."""
from __future__ import annotations

import os
import re
import struct

_vlc = None        # (vlc module, Instance) after the first successful load
_failed = False    # libVLC is missing: do not try again

_VIDEO, _AUDIO, _TEXT = 1, 0, 2   # libvlc_track_type_t
_VIDEO_CODECS = {"h264": "H.264", "avc1": "H.264", "hevc": "HEVC", "hvc1": "HEVC", "h265": "HEVC", "av01": "AV1",
                 "vp90": "VP9", "vp80": "VP8", "mp4v": "MPEG-4", "xvid": "MPEG-4", "divx": "MPEG-4",
                 "mpgv": "MPEG-2", "mp2v": "MPEG-2", "wmv3": "VC-1", "wvc1": "VC-1", "vc-1": "VC-1"}
_AUDIO_CODECS = {"mp4a": "AAC", "a52 ": "AC3", "ac-3": "AC3", "eac3": "E-AC3", "dts ": "DTS", "dtsh": "DTS-HD",
                 "dtse": "DTS", "mpga": "MP3", "mp3 ": "MP3", "opus": "Opus", "flac": "FLAC", "vorb": "Vorbis",
                 "trhd": "TrueHD", "mlp ": "TrueHD"}
_LANGUAGES = {"eng": "English", "por": "Portuguese", "spa": "Spanish", "fre": "French", "fra": "French",
              "ger": "German", "deu": "German", "ita": "Italian", "jpn": "Japanese", "kor": "Korean",
              "chi": "Chinese", "zho": "Chinese", "rus": "Russian"}
_CHANNELS = {1: "1.0", 2: "2.0", 3: "2.1", 6: "5.1", 7: "6.1", 8: "7.1"}


def _fourcc(code: int) -> str:
    return struct.pack("<I", code & 0xFFFFFFFF).decode("latin-1").lower()


def resolution_label(width: int, height: int) -> str:
    """'4K', '1080p'... Widescreen films have fewer lines (1920x800 is still 1080p), so the width is what counts."""
    if not width or not height:
        return ""
    effective = max(width, round(height * 16 / 9))
    for limit, label in ((3400, "4K"), (2400, "1440p"), (1800, "1080p"), (1200, "720p")):
        if effective >= limit:
            return label
    return "SD"


_NAME_QUALITY = ((re.compile(r"(?<![a-z0-9])(2160p|4k|uhd)(?![a-z0-9])", re.I), "4K"),
                 (re.compile(r"(?<![a-z0-9])1440p(?![a-z0-9])", re.I), "1440p"),
                 (re.compile(r"(?<![a-z0-9])(1080[pi]|fullhd|fhd)(?![a-z0-9])", re.I), "1080p"),
                 (re.compile(r"(?<![a-z0-9])720[pi](?![a-z0-9])", re.I), "720p"),
                 (re.compile(r"(?<![a-z0-9])(576p|480p|dvdrip|dvdscr)(?![a-z0-9])", re.I), "SD"))


def name_quality(path: str | None) -> str:
    """Quality written in the file name, or in its folder's ('Movie.2010.1080p.BluRay.mkv' -> '1080p'); '' if none.
    Used when the real resolution could not be read from the file (no libVLC, or an unreadable file)."""
    if not path:
        return ""
    folder, name = os.path.split(path)
    for text in (name, os.path.basename(folder)):
        for pattern, label in _NAME_QUALITY:
            if pattern.search(text):
                return label
    return ""


def video_codec_label(code: int) -> str:
    name = _fourcc(code)
    return _VIDEO_CODECS.get(name, name.strip().upper())


def audio_codec_label(code: int) -> str:
    name = _fourcc(code)
    return _AUDIO_CODECS.get(name, name.strip().upper())


def channels_label(channels: int) -> str:
    return _CHANNELS.get(channels, f"{channels}ch" if channels else "")


def language_label(code) -> str:
    """'por' -> 'Portuguese'; unknown codes are kept ('pol' -> 'POL'); '' when there is no language."""
    if isinstance(code, bytes):
        code = code.decode("utf-8", "ignore")
    code = (code or "").strip()
    if code.lower() in ("", "und", "unk"):
        return ""
    return _LANGUAGES.get(code.lower(), code.upper() if len(code) <= 3 else code.title())


def badges(info: dict | None) -> list[str]:
    """Short labels for the movie page: ['1080p', 'H.264', 'AC3 5.1']."""
    if not info:
        return []
    audio = " ".join(p for p in (info.get("audio"), channels_label(info.get("channels") or 0)) if p)
    return [b for b in (resolution_label(info.get("width") or 0, info.get("height") or 0),
                        info.get("video") or "", audio) if b]


def _load():
    global _vlc, _failed
    if _vlc is None and not _failed:
        try:
            from .ui.player_page import _use_bundled_vlc   # same libVLC as the built-in player
            _use_bundled_vlc()
            import vlc
            instance = vlc.Instance("--quiet")
            if instance is None:
                raise RuntimeError("libVLC")
            _vlc = (vlc, instance)
        except (Exception, SystemExit):  # noqa: BLE001 - python-vlc missing, or libVLC (it calls sys.exit())
            _failed = True
    return _vlc


def available() -> bool:
    """True if libVLC can be loaded."""
    return _load() is not None


def reset() -> None:
    """Forgets a failed load, so the next call tries again (after VLC was installed)."""
    global _vlc, _failed
    _vlc, _failed = None, False


def probe(path: str) -> dict | None:
    """{'width', 'height', 'video', 'audio', 'channels'} of the file; {} if it cannot be read; None if libVLC
    is not available. Runs in a background thread (parsing a file takes a moment)."""
    loaded = _load()
    if loaded is None:
        return None
    _vlc_module, instance = loaded
    info: dict = {}
    try:
        media = instance.media_new(path)
        media.parse()   # synchronous in libVLC 3
        tracks = media.tracks_get()
        best_channels = -1
        audio_langs: list[str] = []
        sub_langs: list[str] = []
        for track in ([tracks[i] for i in range(len(tracks))] if tracks else []):
            kind = int(getattr(track.type, "value", track.type))
            if kind in (_AUDIO, _TEXT):
                language = language_label(getattr(track, "language", None))
                languages = audio_langs if kind == _AUDIO else sub_langs
                if language and language not in languages:
                    languages.append(language)
            if kind == _VIDEO and "video" not in info:
                video = track.u.video.contents
                fps = video.frame_rate_num / video.frame_rate_den if video.frame_rate_den else 0
                info.update(width=video.width, height=video.height, video=video_codec_label(track.codec),
                            fps=round(fps, 3))
            elif kind == _AUDIO and track.u.audio.contents.channels > best_channels:   # the richest audio track
                best_channels = track.u.audio.contents.channels
                info.update(audio=audio_codec_label(track.codec), channels=best_channels)
        if info:
            seconds = (media.get_duration() or 0) / 1000
            info.update(audio_langs=audio_langs, sub_langs=sub_langs,
                        bitrate=round(os.path.getsize(path) * 8 / seconds / 1000) if seconds else 0)   # kbps
    except Exception:  # noqa: BLE001 - unreadable file or a libVLC without these calls
        return {}
    return info
