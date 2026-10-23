"""Movies of the library that resemble a given one, from the metadata already stored (no Qt, no network)."""
from __future__ import annotations


def _directors(movie: dict) -> set[str]:
    return {d.strip() for d in (movie.get("director") or "").split(",") if d.strip()}


def similarity(a: dict, b: dict) -> float:
    """How alike two movies are. 0 when nothing links them (no genre, director, actor or franchise in common)."""
    genres_a, genres_b = set(a["genres"]), set(b["genres"])
    shared_genres = genres_a & genres_b
    shared_directors = _directors(a) & _directors(b)
    shared_cast = {c["name"] for c in a["cast"]} & {c["name"] for c in b["cast"]}
    same_franchise = bool(a.get("franchise")) and a.get("franchise") == b.get("franchise")
    if not (shared_genres or shared_directors or shared_cast or same_franchise):
        return 0.0
    score = 3 * len(shared_genres) / len(genres_a | genres_b) if shared_genres else 0.0
    score += 2 if shared_directors else 0
    score += 0.5 * min(len(shared_cast), 4)
    score += 3 if same_franchise else 0
    year_a, year_b = a.get("year") or a.get("year_guess"), b.get("year") or b.get("year_guess")
    if year_a and year_b:
        score += 0.5 * max(0.0, 1 - abs(year_a - year_b) / 40)   # films from the same time feel alike
    if b.get("votes") and b.get("rating"):
        score += b["rating"] / 100   # tie-breaker: the better rated one first
    return score


def similar_movies(movie: dict, movies: list[dict], limit: int = 20) -> list[dict]:
    """The `limit` most similar items of the same kind (movie or series), best first."""
    kind = movie.get("kind") == "series"
    scored = []
    for other in movies:
        if other["id"] == movie["id"] or (other.get("kind") == "series") != kind:
            continue
        score = similarity(movie, other)
        if score >= 1.0:
            scored.append((score, other))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["sort_title"]))
    return [other for _score, other in scored[:limit]]
