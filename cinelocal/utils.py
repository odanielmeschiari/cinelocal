"""Funções utilitárias puras (sem dependência de Qt)."""
from __future__ import annotations

import re
import unicodedata

_ARTICLES = {"the", "a", "an", "o", "os", "as", "um", "uma", "el", "la", "los", "las",
             "le", "les", "il", "der", "die", "das"}


def normalize_text(text) -> str:
    """Minúsculas, sem acentos e sem pontuação (para busca e comparação)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[\W_]+", " ", t).strip()


def comparable_title(text) -> str:
    """Como normalize_text, ignorando artigo inicial ('The Matrix' == 'Matrix')."""
    words = normalize_text(text).split()
    if len(words) > 1 and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def format_runtime(minutes) -> str:
    if not minutes:
        return ""
    hours, mins = divmod(int(minutes), 60)
    return f"{hours}h {mins:02d}min" if hours else f"{mins}min"


def format_votes(votes) -> str:
    return f"{int(votes or 0):,}".replace(",", ".")
