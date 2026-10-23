"""Numbers about the library for the statistics page (no Qt)."""
from __future__ import annotations

from collections import Counter

from .filters import decade_of


def _top(counter: Counter, limit: int) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def library_stats(movies: list[dict], episodes: dict[int, list[dict]]) -> dict:
    """`movies` is the service list (series included, with negative ids); `episodes` maps series id -> episodes."""
    films = [m for m in movies if m.get("kind") != "series"]
    series = [m for m in movies if m.get("kind") == "series"]
    all_episodes = [e for items in episodes.values() for e in items]
    series_runtime = {-s["id"]: s.get("runtime") or 0 for s in series}

    def minutes(item: dict) -> int:   # an episode without its own length counts as the series' usual one
        if item.get("kind") == "episode":
            return item.get("ep_runtime") or series_runtime.get(item.get("series_id"), 0)
        return item.get("runtime") or 0

    watched_films = [m for m in films if m["watched"]]
    watched_episodes = [e for e in all_episodes if e["watched"]]
    genres: Counter = Counter()
    watched_genres: Counter = Counter()
    decades: Counter = Counter()
    directors: Counter = Counter()
    actors: Counter = Counter()
    for m in films:
        genres.update(m["genres"])
        if m["watched"]:
            watched_genres.update(m["genres"])
        decade = decade_of(m)
        if decade:
            decades[decade] += 1
        directors.update({d.strip() for d in (m.get("director") or "").split(",") if d.strip()})
        actors.update({c["name"] for c in m["cast"][:5]})   # the leading cast only
    rated = [m["user_rating"] for m in movies if m.get("user_rating")]

    return {
        "movies": len(films), "watched_movies": len(watched_films),
        "series": len(series), "episodes": len(all_episodes), "watched_episodes": len(watched_episodes),
        "minutes_watched": sum(map(minutes, watched_films)) + sum(map(minutes, watched_episodes)),
        "minutes_to_watch": sum(minutes(m) for m in films if not m["watched"]),
        "size": sum(m.get("size") or 0 for m in films) + sum(e.get("size") or 0 for e in all_episodes),
        "genres": [(name, count, watched_genres[name]) for name, count in _top(genres, 8)],
        "decades": sorted(decades.items()),
        "directors": _top(directors, 5),
        "actors": _top(actors, 5),
        "stars": sorted(Counter(rated).items()),
        "average_stars": sum(rated) / len(rated) if rated else None,
        "rated": len(rated),
    }
