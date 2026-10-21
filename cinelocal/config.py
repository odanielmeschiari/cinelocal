"""Paths, constants and the user's persistent settings."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import APP_ID


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP_ID
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / APP_ID
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / APP_ID

if os.name == "nt":  # Windows: AppData instead of ~/.config, ~/.local/share and ~/.cache
    _roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    _local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    CONFIG_DIR = _roaming / APP_ID
    DATA_DIR = _local / APP_ID
    CACHE_DIR = _local / APP_ID / "cache"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
DB_FILE = DATA_DIR / "library.db"

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".webm", ".flv", ".ts",
}

LANGUAGES = {
    "en-US": "English (US)",
    "pt-BR": "Português (Brasil)",
    "pt-PT": "Português (Portugal)",
    "es-ES": "Español",
    "fr-FR": "Français",
    "de-DE": "Deutsch",
    "it-IT": "Italiano",
    "ja-JP": "日本語",
}

# Preferred audio/subtitle languages for the built-in player: code -> (label, name fragments VLC may use)
TRACK_LANGUAGES = {
    "en": ("English", ("english", "eng", "en")),
    "pt": ("Português", ("portuguese", "português", "portugues", "por", "pt")),
    "es": ("Español", ("spanish", "español", "espanol", "spa", "es")),
    "fr": ("Français", ("french", "français", "francais", "fre", "fra", "fr")),
    "de": ("Deutsch", ("german", "deutsch", "ger", "deu", "de")),
    "it": ("Italiano", ("italian", "italiano", "ita", "it")),
    "ja": ("日本語", ("japanese", "日本語", "jpn", "ja")),
}

DEFAULT_SETTINGS = {
    "library_path": "",
    "tmdb_api_key": "",
    "omdb_api_key": "",
    "provider": "tmdb",
    "language": "en-US",
    "player_command": "",
    "audio_language": "",     # "" = whatever the file defaults to, or a key of TRACK_LANGUAGES
    "subtitle_language": "",  # "" = file default, "off" = no subtitles, or a key of TRACK_LANGUAGES
    "track_choices": {},      # file path -> audio/subtitle track names picked by hand in the player
    "default_player": "",     # "builtin", "external" or "" (= external only if a command is set)
    "player_prefs": {},       # volume and picture settings remembered between movies
    "resume": {},             # file path -> position (ms) where it stopped
    "sort_id": "title_asc",
}


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)


class Settings:
    """Settings in JSON (~/.config/cinelocal/settings.json)."""

    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key in DEFAULT_SETTINGS:
            if key in stored:
                self._data[key] = stored[key]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)  # contains the API key
        os.replace(tmp, self.path)

    def get(self, key: str):
        return self._data.get(key, DEFAULT_SETTINGS.get(key))

    def update(self, **values) -> None:
        for key, value in values.items():
            if key in DEFAULT_SETTINGS:
                self._data[key] = value
        self.save()
