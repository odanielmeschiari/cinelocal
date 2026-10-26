"""'For you': how much each title resembles the user's taste, from the metadata already stored (no Qt, no network).

The taste is the weighted average of the titles the user favorited, rated or otherwise showed interest in
(`signal`): stars count most, a favorite a lot, and having watched or queued something only a little. Low
stars weigh negative, so they push similar titles down. Every title then gets a 0-1 score:

    base  = genres * (55% + 45% context): genres is the cosine to the average genre mix (rare genres weigh more)
            and the context is 50% TMDB rating (as good as the ones you like, or better), 25% era (close to the
            years you like) and 25% original language; without genres in common there is no base
    score = base + (1 - base) * bonus, where the bonus grows with the director, cast and franchise
            of the titles the user loved (a favorite director lifts a title from 70% to ~85%).
"""
from __future__ import annotations

import math
from collections import Counter

STAR_WEIGHT = ((1, -1.0), (2, -0.5), (3, 0.1), (4, 0.6), (5, 1.0))   # (stars, weight); half stars in between
FAVORITE_WEIGHT, WATCHED_WEIGHT, WATCHLIST_WEIGHT = 0.8, 0.1, 0.2
MIN_MATCH = 0.40       # below this a title is not worth recommending
LIMIT = 100            # recommendations kept
RATING_PRIOR, RATING_CONFIDENCE = 6.0, 200   # TMDB rating of a title with few votes is pulled towards 6.0
BONUS = {"director": 0.5, "cast": 0.25, "franchise": 0.6}   # strength of a title the user loves (1.0 = full)
_GENRE_ALIASES = {"sci-fi": "science fiction"}   # series use "Sci-Fi & Fantasy", "Action & Adventure"...


def _stars(stars: float) -> float:
    if stars <= 0:
        return 0.0
    for (low, a), (high, b) in zip(STAR_WEIGHT, STAR_WEIGHT[1:]):
        if stars <= high:
            return a + (b - a) * max(0.0, stars - low) / (high - low)
    return STAR_WEIGHT[-1][1]


def signal(movie: dict) -> float:
    """How much the user liked a title: -1 (hated) to 1 (loved); 0 = no opinion."""
    value = _stars(movie.get("user_rating") or 0)
    if movie.get("favorite"):
        value += FAVORITE_WEIGHT
    if movie.get("watchlist"):
        value += WATCHLIST_WEIGHT
    if movie.get("watched") and not movie.get("user_rating"):
        value += WATCHED_WEIGHT
    return max(-1.0, min(1.0, value))


def _genres(movie: dict) -> set[str]:
    names = set()
    for genre in movie["genres"]:
        for part in genre.lower().split(" & "):
            names.add(_GENRE_ALIASES.get(part.strip(), part.strip()))
    return names


def _people(movie: dict) -> dict[str, set[str]]:
    directors = {d.strip() for d in (movie.get("director") or "").split(",") if d.strip()}
    cast = {c["name"] for c in movie["cast"][:5]}   # the billed cast: the minor roles say little about taste
    franchise = {movie["franchise"]} if movie.get("franchise") else set()
    return {"director": directors, "cast": cast, "franchise": franchise}


def _rating(movie: dict) -> float:
    """TMDB rating pulled towards the average when few people voted."""
    votes = movie.get("votes") or 0
    return ((movie.get("rating") or 0) * votes + RATING_PRIOR * RATING_CONFIDENCE) / (votes + RATING_CONFIDENCE)


def _language(movie: dict) -> str | None:
    return (movie.get("extra") or {}).get("original_language_name")


def _year(movie: dict) -> int | None:
    return movie.get("year") or movie.get("year_guess")


def _cosine(a: dict, b: dict) -> float:
    dot = sum(value * b.get(key, 0.0) for key, value in a.items())
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm if norm else 0.0


class Taste:
    """What the titles the user liked have in common."""

    def __init__(self, movies: list[dict]):
        counts = Counter(g for m in movies for g in _genres(m))
        self.idf = {g: math.log((len(movies) + 1) / (n + 1)) + 1 for g, n in counts.items()}
        genres: Counter = Counter()
        liked_weight = total = 0.0
        years, ratings, languages = [], [], Counter()
        affinity = {kind: {"+": {}, "-": {}} for kind in BONUS}   # name -> chance it is "loved" (noisy-or)
        for m in movies:
            w = signal(m)
            if not w or m["status"] != "matched" or not m["genres"]:
                continue
            total += abs(w)
            own = {g: self.idf[g] for g in _genres(m)}
            norm = math.sqrt(sum(v * v for v in own.values())) or 1.0
            for genre, value in own.items():
                genres[genre] += w * value / norm
            for kind, names in _people(m).items():
                side = affinity[kind]["+" if w > 0 else "-"]
                for name in names:
                    side[name] = 1 - (1 - side.get(name, 0.0)) * (1 - abs(w))
            if w > 0:
                liked_weight += w
                if _year(m):
                    years.append((w, _year(m)))
                if m.get("votes"):
                    ratings.append((w, _rating(m)))
                if _language(m):
                    languages[_language(m)] += w
        self.genres = {g: v / total for g, v in genres.items() if v > 0} if total else {}
        self.year = self.year_spread = None
        if years:
            mass = sum(w for w, _ in years)
            self.year = sum(w * y for w, y in years) / mass
            variance = sum(w * (y - self.year) ** 2 for w, y in years) / mass
            self.year_spread = max(10.0, math.sqrt(variance))
        self.rating = (sum(w * r for w, r in ratings) / sum(w for w, _ in ratings)) if ratings else None
        self.languages = {k: v / liked_weight for k, v in languages.items()} if liked_weight else {}
        self.loved = {kind: {name: max(0.0, value - sides["-"].get(name, 0.0))
                             for name, value in sides["+"].items()} for kind, sides in affinity.items()}

    def __bool__(self) -> bool:
        return bool(self.genres)

    def score(self, movie: dict) -> float:
        """0 to 1: how much this title looks like what the user likes."""
        genre = _cosine({g: self.idf.get(g, 1.0) for g in _genres(movie)}, self.genres)
        year = _year(movie)
        era = 0.5 if not (year and self.year) else math.exp(-0.5 * ((year - self.year) / self.year_spread) ** 2)
        quality = 0.5
        if self.rating is not None:
            gap = max(0.0, self.rating - _rating(movie))   # better than what they like is no reason to lower it
            quality = math.exp(-0.5 * gap ** 2)
        language = self.languages.get(_language(movie), 0.0)
        base = max(0.0, genre) * (0.55 + 0.45 * (0.5 * quality + 0.25 * era + 0.25 * language))
        miss = 1.0
        for kind, names in _people(movie).items():
            for name in names:
                miss *= 1 - BONUS[kind] * self.loved[kind].get(name, 0.0)
        return base + (1 - base) * (1 - miss)


def match_scores(movies: list[dict]) -> dict[int, float]:
    """id -> 0 to 1 for every title with metadata; empty while the user has not favorited or rated anything."""
    taste = Taste(movies)
    if not taste:
        return {}
    return {m["id"]: taste.score(m) for m in movies if m["status"] == "matched" and m["genres"]}


def recommend(movies: list[dict], scores: dict[int, float]) -> list[dict]:
    """The titles still to discover (not watched, favorited or rated), best match first."""
    picks = [m for m in movies if scores.get(m["id"], 0.0) >= MIN_MATCH and not (
        m["watched"] or m["favorite"] or m.get("user_rating"))]
    picks.sort(key=lambda m: (-scores[m["id"]], m["sort_title"]))
    return picks[:LIMIT]
