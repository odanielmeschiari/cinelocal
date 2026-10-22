"""Rules for finding and saving a movie's metadata (runs in threads)."""
from __future__ import annotations

from . import images
from .db import Database
from .parsing import (choose_best, needs_fallback, parse_details, parse_search_result,
                      parse_season)
from .scanner import search_attempts
from .tmdb import TMDBClient, TMDBError


def find_candidates(client: TMDBClient, title: str, year: int | None) -> list[dict]:
    """Tries the `search_attempts` queries until some results come back."""
    for query, attempt_year in search_attempts(title, year):
        results = [parse_search_result(r) for r in client.search_movie(query, attempt_year)]
        if results:
            return results
    return []


def find_series_candidates(client: TMDBClient, title: str, year: int | None) -> list[dict]:
    for query, attempt_year in search_attempts(title, year):
        results = [parse_search_result(r) for r in client.search_tv(query, attempt_year)]
        if results:
            return results
    return []


def _download_images(client: TMDBClient, movie_id: int, raw: dict, keep_poster: bool = False) -> tuple[bool, bool]:
    """`keep_poster`: the user chose their own cover, so the poster is neither downloaded nor discarded."""
    has_poster, has_backdrop = keep_poster, False
    for path, saver, is_poster in ((raw.get("poster_path"), images.save_poster, True),
                                   (raw.get("backdrop_path"), images.save_backdrop, False)):
        if not path or (is_poster and keep_poster):
            continue
        try:
            ok = saver(client, movie_id, path)
        except TMDBError as exc:
            if exc.kind == "auth":
                raise
            ok = False
        if is_poster:
            has_poster = ok
        else:
            has_backdrop = ok
    return has_poster, has_backdrop


def _season_data(client: TMDBClient, tmdb_id: int, number: int, language: str | None = None) -> dict:
    try:
        return parse_season(client.season(tmdb_id, number, language))
    except TMDBError as exc:
        if exc.kind == "notfound":
            return {}
        raise


def _fill_episodes(db: Database, client: TMDBClient, series_id: int, tmdb_id: int) -> None:
    """Downloads the data of each season that has files and saves it into the episodes."""
    episodes = db.episodes_of(series_id)
    for number in sorted({e["season"] for e in episodes if e["season"] is not None}):
        data = _season_data(client, tmdb_id, number)
        if client.language != "en-US" and any(
                not d["ep_overview"] or not d["ep_title"] for d in data.values()):
            fallback = _season_data(client, tmdb_id, number, "en-US")   # fills in what the translation lacks
            for n, d in data.items():
                d.update({k: v for k, v in fallback.get(n, {}).items() if d.get(k) is None})
        for e in episodes:
            if e["season"] == number:
                db.save_episode(e["id"], data.get(e["episode"], {}))


def process_series(db: Database, client: TMDBClient, series: dict, tmdb_id: int | None = None) -> str:
    """Like process_movie, for a series. `series['id']` is negative (the id used in the interface).

    Identifies the series, downloads metadata and poster, and fills in each season's episodes.
    """
    series_id = abs(series["id"])
    if tmdb_id is None:
        results = find_series_candidates(client, series["clean_title"], series.get("year_guess"))
        best = choose_best(results, series["clean_title"], series.get("year_guess"))
        if best is None:
            outcome = "ambiguous" if results else "not_found"
            db.set_status(series_id, outcome, table="series")
            return outcome
        tmdb_id = best["id"]

    raw = client.tv_details(tmdb_id)
    fallback = None
    if client.language != "en-US" and needs_fallback(raw):
        fallback = client.tv_details(tmdb_id, language="en-US")

    custom = (db.get_series(series_id) or {}).get("custom", [])   # fields edited by the user are kept
    fields = {k: v for k, v in parse_details(raw, fallback).items() if k not in custom}
    source = {"poster_path": raw.get("poster_path") or (fallback or {}).get("poster_path"),
              "backdrop_path": raw.get("backdrop_path") or (fallback or {}).get("backdrop_path")}
    has_poster, has_backdrop = _download_images(client, -series_id, source, "poster" in custom)   # series images: negative id
    images.delete_images(-series_id, poster=not has_poster, backdrop=not has_backdrop)

    fields.update(tmdb_id=tmdb_id, has_poster=has_poster, has_backdrop=has_backdrop, status="matched")
    db.save_metadata(series_id, fields, table="series")
    _fill_episodes(db, client, series_id, tmdb_id)
    return "matched"


def process_movie(db: Database, client: TMDBClient, movie: dict, tmdb_id: int | None = None) -> str:
    """Identifies the movie (if needed), downloads metadata and images and saves them to the database.

    Returns 'matched', 'ambiguous' or 'not_found'. Network/key errors become TMDBError.
    """
    movie_id = movie["id"]
    if tmdb_id is None:
        results = find_candidates(client, movie["clean_title"], movie.get("year_guess"))
        best = choose_best(results, movie["clean_title"], movie.get("year_guess"))
        if best is None:
            outcome = "ambiguous" if results else "not_found"
            db.set_status(movie_id, outcome)
            return outcome
        tmdb_id = best["id"]

    raw = client.movie_details(tmdb_id)
    fallback = None
    if client.language != "en-US" and needs_fallback(raw):
        fallback = client.movie_details(tmdb_id, language="en-US")

    custom = (db.get_movie(movie_id) or {}).get("custom", [])   # fields edited by the user are kept
    fields = {k: v for k, v in parse_details(raw, fallback).items() if k not in custom}
    source = {"poster_path": raw.get("poster_path") or (fallback or {}).get("poster_path"),
              "backdrop_path": raw.get("backdrop_path") or (fallback or {}).get("backdrop_path")}
    has_poster, has_backdrop = _download_images(client, movie_id, source, "poster" in custom)
    # With no new image, discard the old one (e.g. match corrected to another movie).
    images.delete_images(movie_id, poster=not has_poster, backdrop=not has_backdrop)

    fields.update(tmdb_id=tmdb_id, has_poster=has_poster,
                  has_backdrop=has_backdrop, status="matched")
    db.save_metadata(movie_id, fields)
    return "matched"
