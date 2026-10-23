"""Finds the same movie or episode in more than one file (no Qt)."""
from __future__ import annotations

from collections.abc import Callable

from .utils import comparable_title, normalize_text


def find_duplicates(movies: list[dict], episodes: dict[int, list[dict]],
                    series_title: Callable[[int], str]) -> list[dict]:
    """Groups of files that look like the same thing: [{"title": ..., "files": [movie or episode dicts]}].

    Identified movies are compared by their TMDB id, the others by the title and year of the file name;
    episodes by series, season and number. Sorted by title.
    """
    movie_groups: dict[tuple, list[dict]] = {}
    for m in movies:
        if m.get("kind") == "series":
            continue
        if m.get("status") == "matched" and m.get("tmdb_id"):
            key = ("tmdb", m["tmdb_id"])
        else:
            title = comparable_title(m["clean_title"])
            if not title:
                continue
            key = ("title", title, m.get("year_guess"))
        movie_groups.setdefault(key, []).append(m)

    groups = [{"title": files[0]["display_title"], "files": files}
              for files in movie_groups.values() if len(files) > 1]
    for series_id, items in episodes.items():
        by_number: dict[tuple[int, int], list[dict]] = {}
        for e in items:
            if e.get("season") is not None and e.get("episode") is not None:
                by_number.setdefault((e["season"], e["episode"]), []).append(e)
        groups += [{"title": f"{series_title(series_id)} S{season:02d}E{number:02d}", "files": files}
                   for (season, number), files in by_number.items() if len(files) > 1]
    for group in groups:
        group["files"].sort(key=lambda f: f["path"])
    return sorted(groups, key=lambda g: normalize_text(g["title"]))
