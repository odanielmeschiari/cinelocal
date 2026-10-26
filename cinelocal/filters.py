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
    ("popularity_desc", "Popularity (highest)", "popularity", True),
    ("popularity_asc", "Popularity (lowest)", "popularity", False),
    ("votes_desc", "Votes (most)", "votes", True),
    ("votes_asc", "Votes (fewest)", "votes", False),
    ("runtime_asc", "Runtime (shortest)", "runtime", False),
    ("runtime_desc", "Runtime (longest)", "runtime", True),
    ("added_desc", "Recently added", "added", True),
    ("myrating_desc", "My rating (highest)", "user_rating", True),
    ("myrating_asc", "My rating (lowest)", "user_rating", False),
    ("match_desc", "Best match for you", "match", True),
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
    if kind == "tag":
        return any(tag["id"] == value for tag in movie.get("tags", ()))
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
        if key == "runtime" and movie.get("kind") == "series":
            continue   # a series has no single runtime: that limit only applies to movies
        if not _in_range(value, adv.get(f"{key}_min"), adv.get(f"{key}_max")):
            return False
    if "certifications" in adv and movie.get("certification") not in adv["certifications"]:
        return False
    extra = movie.get("extra") or {}
    if "countries" in adv and not set(extra.get("production_countries") or ()) & set(adv["countries"]):
        return False
    if "languages" in adv:
        languages = set(extra.get("spoken_languages") or ())
        if extra.get("original_language_name"):
            languages.add(extra["original_language_name"])
        if not languages & set(adv["languages"]):
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
    if "tags" in adv and not {tag["id"] for tag in movie.get("tags", ())} & set(adv["tags"]):
        return False
    if "stars" in adv and (movie.get("user_rating") or 0) not in adv["stars"]:
        return False
    if "added_days" in adv and movie["added_at"] < (now or time.time()) - adv["added_days"] * 86400:
        return False
    return True


def advanced_options(movies: list[dict]) -> dict:
    """What the advanced search can choose from: [(name, count)] in alphabetical order, and the range of years."""
    genres: Counter = Counter()
    directors: Counter = Counter()
    cast: Counter = Counter()
    certifications: Counter = Counter()
    countries: Counter = Counter()
    languages: Counter = Counter()
    tags: Counter = Counter()
    for m in movies:
        genres.update(m["genres"])
        directors.update(_directors(m))
        cast.update({c["name"] for c in m["cast"]})
        if m.get("certification"):
            certifications[m["certification"]] += 1
        extra = m.get("extra") or {}
        countries.update(set(extra.get("production_countries") or ()))
        language_names = set(extra.get("spoken_languages") or ())
        if extra.get("original_language_name"):
            language_names.add(extra["original_language_name"])
        languages.update(language_names)
        tags.update({(tag["id"], tag["name"]) for tag in m.get("tags", ())})
    years = [m.get("year") or m.get("year_guess") for m in movies]
    years = [y for y in years if y]

    def ranked(counter: Counter) -> list[tuple[str, int]]:
        return sorted(counter.items(), key=lambda kv: (normalize_text(kv[0]), kv[0]))

    tag_options = sorted(((tag_id, name, count) for (tag_id, name), count in tags.items()),
                         key=lambda item: (normalize_text(item[1]), item[1]))
    return {"genres": ranked(genres), "directors": ranked(directors), "cast": ranked(cast),
            "certifications": ranked(certifications), "countries": ranked(countries),
            "languages": ranked(languages), "tags": [(tag_id, f"{name}  ({count})")
                                                       for tag_id, name, count in tag_options],
            "years": (min(years), max(years)) if years else None}


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


def _sort_value(movie: dict, field: str, match: dict | None = None):
    if field == "match":   # how much it looks like what the user likes (see recommend.py)
        return (match or {}).get(movie["id"])
    if field == "title":
        return movie["sort_title"]
    if field == "year":
        return movie.get("year") or movie.get("year_guess")
    if field == "user_rating":
        return movie.get("user_rating") or None   # unrated movies go last
    if field == "rating":
        return movie.get("rating") if movie.get("votes") else None
    if field == "runtime":
        return movie.get("runtime") if movie.get("kind") != "series" else None
    if field == "votes":
        return movie.get("votes") or None
    if field == "popularity":
        return (movie.get("extra") or {}).get("popularity")
    return movie["added_at"]


def sort_movies(movies: list[dict], sort_id: str, match: dict | None = None) -> list[dict]:
    _, _, field, desc = _SORT_BY_ID.get(sort_id, SORT_OPTIONS[0])
    present = [m for m in movies if _sort_value(m, field, match) is not None]
    missing = [m for m in movies if _sort_value(m, field, match) is None]
    # Two stable sorts: first by title, then by the chosen field,
    # so ties stay in alphabetical order.
    present.sort(key=lambda m: m["sort_title"])
    if field != "title":
        present.sort(key=lambda m: _sort_value(m, field, match), reverse=desc)
    elif desc:
        present.reverse()
    missing.sort(key=lambda m: m["sort_title"])
    return present + missing


GROUP_ID_BASE = 10 ** 9   # a grouped collection gets the (negative) id -(GROUP_ID_BASE + collection id)


def group_of(movie_id: int) -> int | None:
    """Collection id behind the id of a grouped poster, or None for a real movie/series."""
    return -movie_id - GROUP_ID_BASE if movie_id <= -GROUP_ID_BASE else None


def automatic_collections(movies: list[dict], collections: list[dict]) -> list[int]:
    """Ids of the collections named after a TMDB franchise of the library (the ones made by `link_franchises`)."""
    franchises = {m["franchise"].lower() for m in movies if m.get("franchise")}
    return [c["id"] for c in collections if c["name"].lower() in franchises]


def group_collections(movies: list[dict], membership: dict[int, set[int]], group_ids: list[int], name_of,
                      cover_of=None) -> list[dict]:
    """Replaces the movies of the collections in `group_ids` by one stand-in per collection, placed where its first
    movie was. The stand-in takes the cover of the collection's earliest movie and the collection's name
    (`stack_movies`: the next two movies, whose covers are piled behind it), unless
    `cover_of(collection id)` gives (image path, modification time): then that image is the cover."""
    owner = {}
    for collection_id in reversed(group_ids):   # a movie in two grouped collections goes to the first one listed
        for movie_id in membership.get(collection_id, ()):
            owner[movie_id] = collection_id
    slots: list = []
    members: dict[int, list[dict]] = {}
    for m in movies:
        collection_id = owner.get(m["id"])
        if collection_id is None:
            slots.append(m)
        else:
            if collection_id not in members:
                slots.append(collection_id)
            members.setdefault(collection_id, []).append(m)
    result = []
    for slot in slots:
        if isinstance(slot, dict):
            result.append(slot)
            continue
        group = members[slot]
        group.sort(key=lambda m: (m.get("year") or m.get("year_guess") or 9999, m["sort_title"]))
        cover = group[0]
        stand_in = {**cover, "id": -(GROUP_ID_BASE + slot), "poster_id": cover["id"], "group": slot,
                    "display_title": name_of(slot), "display_year": None, "status": "matched",
                    "genres": [f"{len(group)} movies"], "stack_movies": group[1:3]}
        custom = cover_of(slot) if cover_of else None
        if custom:
            stand_in.update(cover_file=custom[0], updated_at=custom[1], has_poster=True, stack_movies=[])
        result.append(stand_in)
    return result


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
