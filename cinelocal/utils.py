"""Pure utility functions (no Qt dependency)."""
from __future__ import annotations

import re
import unicodedata

_ARTICLES = {"the", "a", "an", "o", "os", "as", "um", "uma", "el", "la", "los", "las",
             "le", "les", "il", "der", "die", "das"}


def normalize_text(text) -> str:
    """Lowercase, without accents or punctuation (for searching and comparing)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[\W_]+", " ", t).strip()


def comparable_title(text) -> str:
    """Like normalize_text, ignoring a leading article ('The Matrix' == 'Matrix')."""
    words = normalize_text(text).split()
    if len(words) > 1 and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def format_runtime(minutes) -> str:
    if not minutes:
        return ""
    hours, mins = divmod(int(minutes), 60)
    return f"{hours}h {mins:02d}min" if hours else f"{mins}min"


def format_hours(minutes) -> str:
    """Total time for statistics: 5400 -> '90 h 00 min'."""
    hours, mins = divmod(int(minutes or 0), 60)
    return f"{hours:,} h {mins:02d} min"


def format_size(size) -> str:
    """File size: 2254857830 -> '2.1 GB'."""
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def star_text(value) -> str:
    """The user's rating as stars; a half star is shown as ½ (4.5 -> ★★★★½)."""
    return "★" * int(value) + ("½" if value % 1 else "")


def format_votes(votes) -> str:
    return f"{int(votes or 0):,}"
