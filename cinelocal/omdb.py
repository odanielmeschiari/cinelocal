"""Minimal OMDb API client (omdbapi.com), adapted to the TMDB format (no Qt).

Returns dictionaries with the same keys as TMDB, so parsing.py and metadata_service.py
work unchanged. The id stored in the database is OMDB_OFFSET + the IMDb number (tt0133093 ->
OMDB_OFFSET + 133093), which tells which provider each match came from.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .tmdb import USER_AGENT, TMDBError

API_BASE = "https://www.omdbapi.com/"
OMDB_OFFSET = 1_000_000_000


def _na(value):
    return None if value in (None, "", "N/A") else value


def _names(text) -> list[str]:
    return [n.strip() for n in (_na(text) or "").split(",") if n.strip()]


class OMDbClient:
    def __init__(self, api_key: str, language: str = "en-US", timeout: int = 15):
        self.api_key = (api_key or "").strip()
        self.language = "en-US"   # OMDb only has English data
        self.timeout = timeout

    def _request(self, url: str, retries: int = 2) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise TMDBError("OMDb API key invalid or not activated.", "auth") from None
                if exc.code in (429, 500, 502, 503) and attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise TMDBError(f"OMDb HTTP error {exc.code}.", "other") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise TMDBError("Could not connect to OMDb.", "network") from None
        raise TMDBError("Failed to query OMDb.", "other")

    def _get_json(self, **params) -> dict:
        if not self.api_key:
            raise TMDBError("OMDb API key not set.", "auth")
        query = {k: v for k, v in params.items() if v is not None}
        url = f"{API_BASE}?{urllib.parse.urlencode({**query, 'apikey': self.api_key})}"
        try:
            data = json.loads(self._request(url))
        except ValueError:
            raise TMDBError("Invalid response from OMDb.", "other") from None
        if data.get("Response") == "False":
            error = data.get("Error") or "OMDb error."
            low = error.lower()
            if "api key" in low:
                raise TMDBError("Invalid OMDb API key.", "auth")
            if "limit" in low:
                raise TMDBError("OMDb daily request limit reached.", "other")
            raise TMDBError(error, "notfound" if "not found" in low else "other")
        return data

    # -- same interface as TMDBClient ------------------------------------------
    def test_key(self) -> None:
        self._get_json(i="tt0133093")

    def search_movie(self, query: str, year: int | None = None) -> list[dict]:
        return self._search(query, year, "movie")

    def search_tv(self, query: str, year: int | None = None) -> list[dict]:
        return self._search(query, year, "series")

    def _search(self, query: str, year: int | None, kind: str) -> list[dict]:
        try:
            data = self._get_json(s=query, type=kind, y=year)
        except TMDBError as exc:
            if exc.kind == "notfound" or "too many" in str(exc).lower():
                return []
            raise
        return [{"id": OMDB_OFFSET + int(r["imdbID"][2:]), "title": r.get("Title", ""),
                 "original_title": r.get("Title", ""), "release_date": (r.get("Year") or "")[:4],
                 "overview": "", "poster_path": _na(r.get("Poster")),
                 "popularity": 0, "vote_count": 0}
                for r in data.get("Search", []) if re.fullmatch(r"tt\d+", r.get("imdbID", ""))]

    def movie_details(self, omdb_id: int, language: str | None = None) -> dict:
        d = self._get_json(i=f"tt{omdb_id - OMDB_OFFSET:07d}", plot="full")
        released, iso = _na(d.get("Released")), None
        if released:
            try:
                iso = datetime.strptime(released, "%d %b %Y").date().isoformat()
            except ValueError:
                pass
        runtime = re.match(r"\d+", _na(d.get("Runtime")) or "")
        rating = _na(d.get("imdbRating"))
        votes = (_na(d.get("imdbVotes")) or "").replace(",", "")
        return {
            "id": omdb_id, "title": d.get("Title"), "original_title": d.get("Title"),
            "release_date": iso or (_na(d.get("Year")) or "")[:4] or None,
            "overview": _na(d.get("Plot")), "tagline": None,
            "runtime": int(runtime.group()) if runtime else None,
            "vote_average": float(rating) if rating else None,
            "vote_count": int(votes) if votes.isdigit() else 0,
            "genres": [{"name": g} for g in _names(d.get("Genre"))],
            "credits": {"crew": [{"name": n, "job": "Director"} for n in _names(d.get("Director"))],
                        "cast": [{"name": n, "character": ""} for n in _names(d.get("Actors"))]},
            "poster_path": _na(d.get("Poster")), "backdrop_path": None,
        }

    def tv_details(self, omdb_id: int, language: str | None = None) -> dict:
        return self.movie_details(omdb_id, language)   # OMDb uses the same query for series

    def season(self, omdb_id: int, number: int, language: str | None = None) -> dict:
        """Episodes of a season in TMDB format (OMDb has no per-episode overview)."""
        data = self._get_json(i=f"tt{omdb_id - OMDB_OFFSET:07d}", Season=number)
        episodes = []
        for e in data.get("Episodes") or []:
            released, iso = _na(e.get("Released")), None
            if released:
                try:
                    iso = datetime.strptime(released, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    pass
            rating = _na(e.get("imdbRating"))
            number_text = str(e.get("Episode") or "")
            if number_text.isdigit():
                episodes.append({"episode_number": int(number_text), "name": _na(e.get("Title")),
                                 "overview": None, "air_date": iso, "runtime": None,
                                 "vote_average": float(rating) if rating else None})
        return {"episodes": episodes}

    def download_image(self, size: str, file_path: str) -> bytes:
        return self._request(file_path)   # in OMDb the "path" is already the full URL
