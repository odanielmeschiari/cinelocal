"""Choice of metadata source (TMDB or OMDb). No Qt."""
from __future__ import annotations

from .omdb import OMDB_OFFSET, OMDbClient
from .tmdb import TMDBClient

PROVIDERS = {"tmdb": "TMDB (themoviedb.org)", "omdb": "OMDb (omdbapi.com)"}


def make_client(provider: str, api_key: str, language: str):
    if provider == "omdb":
        return OMDbClient(api_key, language)
    return TMDBClient(api_key, language)


def same_provider(provider: str, external_id) -> bool:
    """True if the id stored in the database (tmdb_id column) came from the active provider."""
    return bool(external_id) and (external_id >= OMDB_OFFSET) == (provider == "omdb")
