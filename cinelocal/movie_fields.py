"""Derived fields of a movie (search, sorting, display). No Qt."""
from __future__ import annotations

from .utils import normalize_text


def decorate(movie: dict) -> dict:
    """Derived fields used for searching, sorting and display."""
    if movie.get("kind") == "episode":
        movie["display_title"] = movie.get("ep_title") or f"Episode {movie.get('episode') or '?'}"
    else:
        movie["display_title"] = movie["title"] or movie["clean_title"]
    movie["display_year"] = movie["year"] or movie["year_guess"]
    movie["sort_title"] = normalize_text(movie["display_title"])
    cast_names = " ".join(c["name"] for c in movie["cast"])
    movie["search_text"] = normalize_text(" ".join(filter(None, [
        movie["display_title"], movie["original_title"], movie["clean_title"],
        movie["director"], cast_names, " ".join(movie["genres"]),
    ])))
    return movie
