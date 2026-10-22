"""Filters, sorting and sidebar counts (no Qt)."""
from __future__ import annotations

import time
from collections import Counter

from .utils import normalize_text

# (id, label, field, descending)
SORT_OPTIONS = [
    ("title_asc", "Title (A–Z)", "title", False),
    ("title_desc", "Title (Z–A)", "title", True),
    ("year_desc", "Year (newest)", "year", True),
    ("year_asc", "Year (oldest)", "year", False),
    ("rating_desc", "Rating (highest)", "rating", True),
    ("rating_asc", "Rating (lowest)", "rating", False),
    ("added_desc", "Recently added", "added", True),
    ("myrating_desc", "My rating (highest)", "user_rating", True),
    ("myrating_asc", "My rating (lowest)", "user_rating", False),
]
_SORT_BY_ID = {o[0]: o for o in SORT_OPTIONS}

Filter = tuple  # (kind, value)


def decade_of(movie: dict) -> int | None:
    year = movie.get("year") or movie.get("year_guess")
    return (year // 10) * 10 if year else None


def matches(movie: dict, flt: Filter, membership: dict[int, set[int]], progress=None, history=None) -> bool:
    kind, value = flt
    if kind == "all":
        return True
    if kind == "continue":   # started watching but not finished
        return bool(progress and progress(movie) > 0)
    if kind == "history":    # watched, or watched in part
        return bool(history and history(movie))
    if kind == "favorites":
        return movie["favorite"]
    if kind == "watchlist":
        return movie["watchlist"]
    if kind == "watched":
        return movie["watched"] == value
    if kind == "review":
        return movie["status"] in ("ambiguous", "not_found")
    if kind == "collection":
        return movie["id"] in membership.get(value, ())
    if kind == "stars":      # the user's own 1-5 star rating
        return movie.get("user_rating") == value
    if kind == "genre":
        return value in movie["genres"]
    if kind == "decade":
        return decade_of(movie) == value
    return True


def _directors(movie: dict) -> set[str]:
    return {d.strip() for d in (movie.get("director") or "").split(",") if d.strip()}


def _in_range(value, low, high) -> bool:
    if low is None and high is None:
        return True
    return value is not None and (low is None or value >= low) and (high is None or value <= high)


def matches_advanced(movie: dict, adv: dict, membership: dict[int, set[int]],
                     progress=None, now: float | None = None) -> bool:
    """Advanced search. `adv` only holds the criteria that are set; every one of them must match
    (inside a list of choices, any choice is enough, except genres with `genres_all`)."""
    if "kind" in adv and (movie.get("kind") == "series") != (adv["kind"] == "series"):
        return False
    if "genres" in adv:
        have, want = set(movie["genres"]), set(adv["genres"])
        if not (want <= have if adv.get("genres_all") else want & have):
            return False
    year = movie.get("year") or movie.get("year_guess")
    for key, value in (("year", year), ("rating", movie.get("rating")), ("votes", movie.get("votes")),
                       ("runtime", movie.get("runtime"))):
        if not _in_range(value, adv.get(f"{key}_min"), adv.get(f"{key}_max")):
            return False
    if "certifications" in adv and movie.get("certification") not in adv["certifications"]:
        return False
    if "directors" in adv and not _directors(movie) & set(adv["directors"]):
        return False
    if "cast" in adv and not {c["name"] for c in movie["cast"]} & set(adv["cast"]):
        return False
    if "watched" in adv and movie["watched"] != adv["watched"]:
        return False
    if adv.get("favorite") and not movie["favorite"]:
        return False
    if adv.get("watchlist") and not movie["watchlist"]:
        return False
    if adv.get("in_progress") and not (progress and progress(movie) > 0):
        return False
    if "collections" in adv and not any(movie["id"] in membership.get(c, ()) for c in adv["collections"]):
        return False
    if "stars" in adv and (movie.get("user_rating") or 0) not in adv["stars"]:
        return False
    if "added_days" in adv and movie["added_at"] < (now or time.time()) - adv["added_days"] * 86400:
        return False
    return True


def advanced_options(movies: list[dict]) -> dict:
    """What the advanced search can choose from: [(name, count)] sorted by count, and the range of years."""
    genres: Counter = Counter()
    directors: Counter = Counter()
    cast: Counter = Counter()
    certifications: Counter = Counter()
    for m in movies:
        genres.update(m["genres"])
        directors.update(_directors(m))
        cast.update({c["name"] for c in m["cast"]})
        if m.get("certification"):
            certifications[m["certification"]] += 1
    years = [m.get("year") or m.get("year_guess") for m in movies]
    years = [y for y in years if y]

    def ranked(counter: Counter) -> list[tuple[str, int]]:
        return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))

    return {"genres": ranked(genres), "directors": ranked(directors), "cast": ranked(cast),
            "certifications": ranked(certifications), "years": (min(years), max(years)) if years else None}


def filter_movies(movies: list[dict], flt: Filter, membership: dict[int, set[int]],
                  query: str = "", progress=None, advanced: dict | None = None, history=None) -> list[dict]:
    terms = normalize_text(query).split()
    result = []
    for m in movies:
        if not matches(m, flt, membership, progress, history):
            continue
        if advanced and not matches_advanced(m, advanced, membership, progress):
            continue
        if terms and not all(t in m["search_text"] for t in terms):
            continue
        result.append(m)
    return result


def _sort_value(movie: dict, field: str):
    if field == "title":
        return movie["sort_title"]
    if field == "year":
        return movie.get("year") or movie.get("year_guess")
    if field == "user_rating":
        return movie.get("user_rating") or None   # unrated movies go last
    if field == "rating":
        return movie.get("rating") if movie.get("votes") else None
    return movie["added_at"]


def sort_movies(movies: list[dict], sort_id: str) -> list[dict]:
    _, _, field, desc = _SORT_BY_ID.get(sort_id, SORT_OPTIONS[0])
    present = [m for m in movies if _sort_value(m, field) is not None]
    missing = [m for m in movies if _sort_value(m, field) is None]
    # Two stable sorts: first by title, then by the chosen field,
    # so ties stay in alphabetical order.
    present.sort(key=lambda m: m["sort_title"])
    if field != "title":
        present.sort(key=lambda m: _sort_value(m, field), reverse=desc)
    elif desc:
        present.reverse()
    missing.sort(key=lambda m: m["sort_title"])
    return present + missing


def sidebar_counts(movies: list[dict], progress=None, history=None) -> dict:
    genres: Counter = Counter()
    decades: Counter = Counter()
    stars: Counter = Counter(m["user_rating"] for m in movies if m.get("user_rating"))
    for m in movies:
        genres.update(m["genres"])
        d = decade_of(m)
        if d:
            decades[d] += 1
    return {
        "all": len(movies),
        "continue": sum(1 for m in movies if progress and progress(m) > 0),
        "history": sum(1 for m in movies if history and history(m)),
        "favorites": sum(m["favorite"] for m in movies),
        "watchlist": sum(m["watchlist"] for m in movies),
        "watched": sum(m["watched"] for m in movies),
        "unwatched": sum(not m["watched"] for m in movies),
        "review": sum(m["status"] in ("ambiguous", "not_found") for m in movies),
        "genres": sorted(genres.items(), key=lambda kv: (-kv[1], kv[0])),
        "decades": sorted(decades.items(), reverse=True),
        "stars": sorted(stars.items(), reverse=True),
    }
