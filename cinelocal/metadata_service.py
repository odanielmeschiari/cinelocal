"""Regras de busca e gravação de metadados de um filme (executa em threads)."""
from __future__ import annotations

from . import images
from .db import Database
from .parsing import (choose_best, needs_fallback, parse_details, parse_search_result,
                      parse_season)
from .scanner import search_attempts
from .tmdb import TMDBClient, TMDBError


def find_candidates(client: TMDBClient, title: str, year: int | None) -> list[dict]:
    """Tenta as consultas de `search_attempts` até obter resultados."""
    for query, attempt_year in search_attempts(title, year):
        results = [parse_search_result(r) for r in client.search_movie(query, attempt_year)]
        if results:
            return results
    return []


def find_series_candidates(client: TMDBClient, title: str, year: int | None) -> list[dict]:
    for query, attempt_year in search_attempts(title, year):
        results = [parse_search_result(r) for r in client.search_tv(query, attempt_year)]
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


def _season_data(client: TMDBClient, tmdb_id: int, number: int, language: str | None = None) -> dict:
    try:
        return parse_season(client.season(tmdb_id, number, language))
    except TMDBError as exc:
        if exc.kind == "notfound":
            return {}
        raise


def _fill_episodes(db: Database, client: TMDBClient, series_id: int, tmdb_id: int) -> None:
    """Baixa os dados de cada temporada que tem arquivo e grava nos episódios."""
    episodes = db.episodes_of(series_id)
    for number in sorted({e["season"] for e in episodes if e["season"] is not None}):
        data = _season_data(client, tmdb_id, number)
        if client.language != "en-US" and any(
                not d["ep_overview"] or not d["ep_title"] for d in data.values()):
            fallback = _season_data(client, tmdb_id, number, "en-US")   # preenche o que falta na tradução
            for n, d in data.items():
                d.update({k: v for k, v in fallback.get(n, {}).items() if d.get(k) is None})
        for e in episodes:
            if e["season"] == number:
                db.save_episode(e["id"], data.get(e["episode"], {}))


def process_series(db: Database, client: TMDBClient, series: dict, tmdb_id: int | None = None) -> str:
    """Como process_movie, para uma série. `series['id']` é negativo (id usado na interface).

    Identifica a série, baixa metadados e capa e preenche os episódios de cada temporada.
    """
    series_id = abs(series["id"])
    if tmdb_id is None:
        results = find_series_candidates(client, series["clean_title"], series.get("year_guess"))
        best = choose_best(results, series["clean_title"], series.get("year_guess"))
        if best is None:
            outcome = "ambiguous" if results else "not_found"
            db.set_status(series_id, outcome, table="series")
            return outcome
        tmdb_id = best["id"]

    raw = client.tv_details(tmdb_id)
    fallback = None
    if client.language != "en-US" and needs_fallback(raw):
        fallback = client.tv_details(tmdb_id, language="en-US")

    fields = parse_details(raw, fallback)
    source = {"poster_path": raw.get("poster_path") or (fallback or {}).get("poster_path"),
              "backdrop_path": raw.get("backdrop_path") or (fallback or {}).get("backdrop_path")}
    has_poster, has_backdrop = _download_images(client, -series_id, source)   # imagens de série: id negativo
    images.delete_images(-series_id, poster=not has_poster, backdrop=not has_backdrop)

    fields.update(tmdb_id=tmdb_id, has_poster=has_poster, has_backdrop=has_backdrop, status="matched")
    db.save_metadata(series_id, fields, table="series")
    _fill_episodes(db, client, series_id, tmdb_id)
    return "matched"


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
