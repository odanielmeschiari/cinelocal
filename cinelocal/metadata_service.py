"""Regras de busca e gravação de metadados de um filme (executa em threads)."""
from __future__ import annotations

from . import images
from .db import Database
from .parsing import (choose_best, needs_fallback, parse_details, parse_search_result)
from .scanner import search_attempts
from .tmdb import TMDBClient, TMDBError


def find_candidates(client: TMDBClient, title: str, year: int | None) -> list[dict]:
    """Tenta as consultas de `search_attempts` até obter resultados."""
    for query, attempt_year in search_attempts(title, year):
        results = [parse_search_result(r) for r in client.search_movie(query, attempt_year)]
        if results:
            return results
    return []


def _download_images(client: TMDBClient, movie_id: int, raw: dict) -> tuple[bool, bool]:
    has_poster = has_backdrop = False
    for path, saver, is_poster in ((raw.get("poster_path"), images.save_poster, True),
                                   (raw.get("backdrop_path"), images.save_backdrop, False)):
        if not path:
            continue
        try:
            ok = saver(client, movie_id, path)
        except TMDBError as exc:
            if exc.kind == "auth":
                raise
            ok = False
        if is_poster:
            has_poster = ok
        else:
            has_backdrop = ok
    return has_poster, has_backdrop


def process_movie(db: Database, client: TMDBClient, movie: dict, tmdb_id: int | None = None) -> str:
    """Identifica o filme (se preciso), baixa metadados e imagens e grava no banco.

    Retorna 'matched', 'ambiguous' ou 'not_found'. Erros de rede/chave viram TMDBError.
    """
    movie_id = movie["id"]
    if tmdb_id is None:
        results = find_candidates(client, movie["clean_title"], movie.get("year_guess"))
        best = choose_best(results, movie["clean_title"], movie.get("year_guess"))
        if best is None:
            outcome = "ambiguous" if results else "not_found"
            db.set_status(movie_id, outcome)
            return outcome
        tmdb_id = best["id"]

    raw = client.movie_details(tmdb_id)
    fallback = None
    if client.language != "en-US" and needs_fallback(raw):
        fallback = client.movie_details(tmdb_id, language="en-US")

    fields = parse_details(raw, fallback)
    source = {"poster_path": raw.get("poster_path") or (fallback or {}).get("poster_path"),
              "backdrop_path": raw.get("backdrop_path") or (fallback or {}).get("backdrop_path")}
    has_poster, has_backdrop = _download_images(client, movie_id, source)
    # Sem imagem nova, descarta a antiga (ex.: correspondência corrigida para outro filme).
    images.delete_images(movie_id, poster=not has_poster, backdrop=not has_backdrop)

    fields.update(tmdb_id=tmdb_id, has_poster=has_poster,
                  has_backdrop=has_backdrop, status="matched")
    db.save_metadata(movie_id, fields)
    return "matched"
