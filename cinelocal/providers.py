"""Escolha da fonte de metadados (TMDB ou OMDb). Sem Qt."""
from __future__ import annotations

from .omdb import OMDB_OFFSET, OMDbClient
from .tmdb import TMDBClient

PROVIDERS = {"tmdb": "TMDB (themoviedb.org)", "omdb": "OMDb (omdbapi.com)"}


def make_client(provider: str, api_key: str, language: str):
    if provider == "omdb":
        return OMDbClient(api_key, language)
    return TMDBClient(api_key, language)


def same_provider(provider: str, external_id) -> bool:
    """True se o id guardado no banco (coluna tmdb_id) veio do provedor ativo."""
    return bool(external_id) and (external_id >= OMDB_OFFSET) == (provider == "omdb")
