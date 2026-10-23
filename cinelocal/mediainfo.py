"""Technical info of a video file (resolution, codecs, audio channels) read with libVLC, and its badges."""
from __future__ import annotations

import struct

_vlc = None        # (vlc module, Instance) after the first successful load
_failed = False    # libVLC is missing: do not try again

_VIDEO, _AUDIO = 1, 0   # libvlc_track_type_t
_VIDEO_CODECS = {"h264": "H.264", "avc1": "H.264", "hevc": "HEVC", "hvc1": "HEVC", "h265": "HEVC", "av01": "AV1",
                 "vp90": "VP9", "vp80": "VP8", "mp4v": "MPEG-4", "xvid": "MPEG-4", "divx": "MPEG-4",
                 "mpgv": "MPEG-2", "mp2v": "MPEG-2", "wmv3": "VC-1", "wvc1": "VC-1", "vc-1": "VC-1"}
_AUDIO_CODECS = {"mp4a": "AAC", "a52 ": "AC3", "ac-3": "AC3", "eac3": "E-AC3", "dts ": "DTS", "dtsh": "DTS-HD",
                 "dtse": "DTS", "mpga": "MP3", "mp3 ": "MP3", "opus": "Opus", "flac": "FLAC", "vorb": "Vorbis",
                 "trhd": "TrueHD", "mlp ": "TrueHD"}
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


def video_codec_label(code: int) -> str:
    name = _fourcc(code)
    return _VIDEO_CODECS.get(name, name.strip().upper())


def audio_codec_label(code: int) -> str:
    name = _fourcc(code)
    return _AUDIO_CODECS.get(name, name.strip().upper())


def channels_label(channels: int) -> str:
    return _CHANNELS.get(channels, f"{channels}ch" if channels else "")


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
        for track in ([tracks[i] for i in range(len(tracks))] if tracks else []):
            kind = int(getattr(track.type, "value", track.type))
            if kind == _VIDEO and "video" not in info:
                video = track.u.video.contents
                info.update(width=video.width, height=video.height, video=video_codec_label(track.codec))
            elif kind == _AUDIO and track.u.audio.contents.channels > best_channels:   # the richest audio track
                best_channels = track.u.audio.contents.channels
                info.update(audio=audio_codec_label(track.codec), channels=best_channels)
    except Exception:  # noqa: BLE001 - unreadable file or a libVLC without these calls
        return {}
    return info
