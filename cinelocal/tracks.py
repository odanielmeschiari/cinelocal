"""Choosing audio/subtitle tracks from the user's preferences (no Qt, no VLC)."""
from __future__ import annotations

import re

from .config import TRACK_LANGUAGES

# VLC does not expose the "forced" flag, so forced subtitle tracks are recognised by their name.
FORCED_WORDS = ("forced", "forçad", "forzad", "forzat", "forcé", "erzwung", "強制")


def track_name(name) -> str:
    return name.decode("utf-8", "replace") if isinstance(name, bytes) else str(name)


def matches_language(code: str, name: str) -> bool:
    aliases = TRACK_LANGUAGES[code][1]
    return any(word in aliases for word in re.findall(r"\w+", name.lower()))


def is_forced(name: str) -> bool:
    return any(word in name.lower() for word in FORCED_WORDS)


def choose_track(tracks, saved: str = "", language: str = "", prefer_language: str = ""):
    """Track to select, as (track id or None, final?).

    `tracks` is VLC's (id, name) list. `saved` is the name of a track the user picked earlier for this
    file; `language` is a TRACK_LANGUAGES key, or for subtitles also "off" / "forced". Not final means
    the wanted track may still show up (VLC lists the tracks a moment after playback starts).
    """
    tracks = [(i, track_name(n)) for i, n in tracks or []]
    if not any(i >= 0 for i, _name in tracks):
        return None, False
    for track_id, name in tracks:
        if saved and name == saved:
            return track_id, True
    if language == "off":
        return -1, True
    if language == "forced":
        forced = [i for i, n in tracks if i >= 0 and is_forced(n)]
        if prefer_language in TRACK_LANGUAGES:   # the forced track in the audio language, if there is one
            forced = [i for i in forced if matches_language(prefer_language, dict(tracks)[i])] or forced
        return (forced[0] if forced else -1), True
    if language in TRACK_LANGUAGES:
        found = [(i, n) for i, n in tracks if i >= 0 and matches_language(language, n)]
        full = [i for i, n in found if not is_forced(n)]   # forced tracks only have the foreign dialogue
        pick = full or [i for i, _n in found]
        return (pick[0], True) if pick else (None, False)
    return None, True
