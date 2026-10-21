"""Filtros, ordenação e contagens da barra lateral (sem Qt)."""
from __future__ import annotations

from collections import Counter

from .utils import normalize_text

# (id, rótulo, campo, decrescente)
SORT_OPTIONS = [
    ("title_asc", "Título (A–Z)", "title", False),
    ("title_desc", "Título (Z–A)", "title", True),
    ("year_desc", "Ano (mais recentes)", "year", True),
    ("year_asc", "Ano (mais antigos)", "year", False),
    ("rating_desc", "Nota (maior)", "rating", True),
    ("rating_asc", "Nota (menor)", "rating", False),
    ("added_desc", "Adicionados recentemente", "added", True),
]
_SORT_BY_ID = {o[0]: o for o in SORT_OPTIONS}

Filter = tuple  # (tipo, valor)


def decade_of(movie: dict) -> int | None:
    year = movie.get("year") or movie.get("year_guess")
    return (year // 10) * 10 if year else None


def matches(movie: dict, flt: Filter, membership: dict[int, set[int]], progress=None) -> bool:
    kind, value = flt
    if kind == "all":
        return True
    if kind == "continue":   # começou a assistir e não terminou
        return bool(progress and progress(movie) > 0)
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
    if kind == "genre":
        return value in movie["genres"]
    if kind == "decade":
        return decade_of(movie) == value
    return True


def filter_movies(movies: list[dict], flt: Filter, membership: dict[int, set[int]],
                  query: str = "", progress=None) -> list[dict]:
    terms = normalize_text(query).split()
    result = []
    for m in movies:
        if not matches(m, flt, membership, progress):
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
    if field == "rating":
        return movie.get("rating") if movie.get("votes") else None
    return movie["added_at"]


def sort_movies(movies: list[dict], sort_id: str) -> list[dict]:
    _, _, field, desc = _SORT_BY_ID.get(sort_id, SORT_OPTIONS[0])
    present = [m for m in movies if _sort_value(m, field) is not None]
    missing = [m for m in movies if _sort_value(m, field) is None]
    # Duas ordenações estáveis: primeiro por título, depois pelo campo escolhido,
    # assim empates ficam em ordem alfabética.
    present.sort(key=lambda m: m["sort_title"])
    if field != "title":
        present.sort(key=lambda m: _sort_value(m, field), reverse=desc)
    elif desc:
        present.reverse()
    missing.sort(key=lambda m: m["sort_title"])
    return present + missing


def sidebar_counts(movies: list[dict], progress=None) -> dict:
    genres: Counter = Counter()
    decades: Counter = Counter()
    for m in movies:
        genres.update(m["genres"])
        d = decade_of(m)
        if d:
            decades[d] += 1
    return {
        "all": len(movies),
        "continue": sum(1 for m in movies if progress and progress(m) > 0),
        "favorites": sum(m["favorite"] for m in movies),
        "watchlist": sum(m["watchlist"] for m in movies),
        "watched": sum(m["watched"] for m in movies),
        "unwatched": sum(not m["watched"] for m in movies),
        "review": sum(m["status"] in ("ambiguous", "not_found") for m in movies),
        "genres": sorted(genres.items(), key=lambda kv: (-kv[1], kv[0])),
        "decades": sorted(decades.items(), reverse=True),
    }
