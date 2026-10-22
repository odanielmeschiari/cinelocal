"""Minimal OpenSubtitles.com API client: finds and downloads subtitles (no Qt, standard library only)."""
from __future__ import annotations

import http.client
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

API_BASE = "https://api.opensubtitles.com/api/v1"
USER_AGENT = f"CineLocal v{__version__}"
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".vtt"}


class OpenSubtitlesError(Exception):
    """kind: 'auth' (key rejected) | 'limit' (daily downloads or request rate) | 'network' | 'other'"""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


class OpenSubtitlesClient:
    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def _request(self, url: str, body: dict | None = None, send_key: bool = True, retries: int = 2) -> bytes:
        if not self.api_key:
            raise OpenSubtitlesError("OpenSubtitles API key not set.", "auth")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if send_key:   # the subtitle file itself is fetched from another host, which does not need the key
            headers["Api-Key"] = self.api_key
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers)
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise OpenSubtitlesError("OpenSubtitles rejected the API key. Check it in Settings.",
                                             "auth") from None
                if exc.code == 406:   # the answer to "you have downloaded your allowed N subtitles for 24h"
                    raise OpenSubtitlesError("OpenSubtitles daily download limit reached.", "limit") from None
                if exc.code in (429, 500, 502, 503) and attempt < retries:
                    try:
                        wait = float(exc.headers.get("Retry-After", 1 + attempt))
                    except (TypeError, ValueError):
                        wait = 1 + attempt
                    time.sleep(min(wait, 5))
                    continue
                if exc.code in (429, 500, 502, 503):
                    raise OpenSubtitlesError("OpenSubtitles is busy or unavailable.", "limit") from None
                raise OpenSubtitlesError(f"OpenSubtitles HTTP error {exc.code}.", "other") from None
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
                if attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise OpenSubtitlesError("Could not connect to OpenSubtitles.", "network") from None
        raise OpenSubtitlesError("Failed to query OpenSubtitles.", "other")

    def _json(self, url: str, body: dict | None = None) -> dict:
        try:
            return json.loads(self._request(url, body))
        except ValueError:
            raise OpenSubtitlesError("Invalid response from OpenSubtitles.", "other") from None

    def search(self, **params) -> list[dict]:
        """Results of /subtitles. The API wants lowercase parameters, in alphabetical order."""
        query = sorted((k, str(v).lower()) for k, v in params.items() if v not in (None, ""))
        return self._json(f"{API_BASE}/subtitles?{urllib.parse.urlencode(query)}").get("data") or []

    def download(self, file_id: int) -> bytes:
        info = self._json(f"{API_BASE}/download", {"file_id": file_id, "sub_format": "srt"})
        if not info.get("link"):
            raise OpenSubtitlesError("OpenSubtitles did not return a download link.", "other")
        return self._request(info["link"], send_key=False)


def movie_hash(path: str) -> str | None:
    """OpenSubtitles file hash (size + the first and last 64 KB), which identifies this exact release."""
    size = os.path.getsize(path)
    if size < 2 * 65536:
        return None
    total = size
    with open(path, "rb") as f:
        for offset in (0, size - 65536):
            f.seek(offset)
            total += sum(struct.unpack("<8192Q", f.read(65536)))
    return f"{total & 0xFFFFFFFFFFFFFFFF:016x}"


def has_subtitle(path: str) -> bool:
    """True if a subtitle file already sits next to the video ('Movie.srt', 'Movie.pt-BR.srt'...)."""
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0].lower() + "."
    try:
        names = os.listdir(folder)
    except OSError:
        return False
    return any(n.lower().startswith(stem) and os.path.splitext(n)[1].lower() in SUBTITLE_EXTENSIONS
               for n in names)


def best_subtitle(results: list[dict]) -> dict | None:
    """Attributes of the most reliable result: the one made for this exact file, then human translations
    (not machine ones), then the most downloaded. Forced-only subtitles are ignored."""
    usable = [r.get("attributes") or {} for r in results]
    usable = [a for a in usable if a.get("files") and not a.get("foreign_parts_only")]
    return max(usable, default=None, key=lambda a: (
        bool(a.get("moviehash_match")), not (a.get("ai_translated") or a.get("machine_translated")),
        a.get("download_count") or 0))


def fetch_subtitle(client: OpenSubtitlesClient, path: str, title: str, year: int | None, languages: str,
                   season: int | None = None, episode: int | None = None) -> str | None:
    """Downloads the best subtitle for a video and saves it next to it ('Movie.pt-BR.srt'), where players
    find it every time the video is played. Returns the saved path, or None if there was nothing to do
    (no such video, it already has a subtitle) or nothing was found. `languages`: comma-separated codes."""
    if not os.path.isfile(path) or has_subtitle(path):
        return None
    digest = movie_hash(path)
    found = best_subtitle(client.search(moviehash=digest, languages=languages)) if digest else None
    if not (found and found.get("moviehash_match")):
        extra = ({"type": "episode", "season_number": season, "episode_number": episode}
                 if episode is not None else {"type": "movie", "year": year})
        found = best_subtitle(client.search(query=title, languages=languages, **extra))
    if found is None:
        return None
    content = client.download(found["files"][0]["file_id"])
    if not content:
        return None
    language = "".join(c for c in str(found.get("language") or languages.split(",")[0]) if c.isalnum() or c == "-")
    dest = f"{os.path.splitext(path)[0]}.{language}.srt"
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, dest)
    return dest
