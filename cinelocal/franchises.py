"""Automatic collections from TMDB franchises (no Qt)."""
from __future__ import annotations


def franchise_plan(movies: list[dict]) -> list[tuple[str, list[int]]]:
    """[(franchise name, ids of its movies not linked yet)] for every franchise with 2+ movies in the library.

    A movie is only linked once (`franchise_linked`), so taking it out of the collection by hand is respected.
    """
    groups: dict[str, list[dict]] = {}
    for m in movies:
        if m.get("kind") != "series" and m.get("franchise"):
            groups.setdefault(m["franchise"], []).append(m)
    plan = []
    for name, members in sorted(groups.items()):
        fresh = [m["id"] for m in members if not m.get("franchise_linked")]
        if len(members) >= 2 and fresh:
            plan.append((name, fresh))
    return plan
