"""Parsing of TMDB responses and choice of the best match (no Qt)."""
from __future__ import annotations

from .utils import comparable_title


def _year_of(date_text) -> int | None:
    text = (date_text or "")[:4]
    return int(text) if text.isdigit() else None


def parse_search_result(raw: dict) -> dict:
    return {
        "id": raw["id"],
        "title": raw.get("title") or raw.get("original_title") or "",
        "original_title": raw.get("original_title") or "",
        "year": _year_of(raw.get("release_date")),
        "overview": raw.get("overview") or "",
        "poster_path": raw.get("poster_path"),
        "popularity": raw.get("popularity") or 0,
        "vote_count": raw.get("vote_count") or 0,
    }


def choose_best(results: list[dict], title: str, year: int | None) -> dict | None:
    """Returns the confident match, or None when manual review is needed."""
    if not results:
        return None
    wanted = comparable_title(title)
    exact = [r for r in results
             if comparable_title(r["title"]) == wanted or comparable_title(r["original_title"]) == wanted]

    if year:
        exact_year = [r for r in exact if r["year"] and abs(r["year"] - year) <= 1]
        if exact_year:
            return max(exact_year, key=lambda r: r["popularity"])
        if results[0]["year"] == year:
            return results[0]

    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        ranked = sorted(exact, key=lambda r: r["vote_count"], reverse=True)
        if ranked[0]["vote_count"] >= 4 * max(ranked[1]["vote_count"], 1):
            return ranked[0]
        return None
    return results[0] if len(results) == 1 else None


def parse_season(raw: dict) -> dict[int, dict]:
    """Converts /tv/{id}/season/{n} into {episode number: database ep_* fields}."""
    episodes = {}
    for e in raw.get("episodes") or []:
        if e.get("episode_number") is None:
            continue
        episodes[e["episode_number"]] = {
            "ep_title": e.get("name") or None,
            "ep_overview": e.get("overview") or None,
            "ep_air_date": e.get("air_date") or None,
            "ep_runtime": e.get("runtime") or None,
            "ep_rating": e.get("vote_average") or None,
        }
    return episodes


def _pick_trailer(videos: list[dict]) -> str | None:
    youtube = [v for v in videos if v.get("site") == "YouTube" and v.get("key")]
    for kind in ("Trailer", "Teaser"):
        options = [v for v in youtube if v.get("type") == kind]
        if options:
            options.sort(key=lambda v: not v.get("official", False))
            return options[0]["key"]
    return None


def needs_fallback(raw: dict) -> bool:
    return (not raw.get("overview") or not raw.get("tagline")
            or not (raw.get("videos") or {}).get("results"))


def parse_details(raw: dict, fallback: dict | None = None) -> dict:
    """Converts the /movie/{id} response into database fields.
    `fallback` (in English) fills in whatever the translation lacks."""
    fb = fallback or {}

    def pick(key):
        return raw.get(key) or fb.get(key) or None

    credits = raw.get("credits") or {}
    directors = [p["name"] for p in credits.get("crew", []) if p.get("job") == "Director"]
    cast = [{"name": p["name"], "character": p.get("character") or ""}
            for p in credits.get("cast", [])[:12]]
    videos = (raw.get("videos") or {}).get("results") or (fb.get("videos") or {}).get("results") or []

    fields = {
        "title": pick("title"),
        "original_title": raw.get("original_title"),
        "release_date": raw.get("release_date") or None,
        "year": _year_of(raw.get("release_date")),
        "overview": pick("overview"),
        "tagline": pick("tagline"),
        "runtime": raw.get("runtime") or None,
        "rating": raw.get("vote_average") or None,
        "votes": raw.get("vote_count") or 0,
        "genres": [g["name"] for g in (raw.get("genres") or [])] or
                  [g["name"] for g in (fb.get("genres") or [])],
        "director": ", ".join(dict.fromkeys(directors)) or None,
        "cast": cast,
        "trailer_key": _pick_trailer(videos),
        "certification": pick("certification"),
    }
    if "belongs_to_collection" in raw:   # only movies have it: the franchise ("The Matrix Collection"), or none
        fields["franchise"] = (raw["belongs_to_collection"] or {}).get("name") or None
    return fields
