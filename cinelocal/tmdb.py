"""Cliente mínimo da API do TMDB (sem Qt, só biblioteca padrão)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"
USER_AGENT = "CineLocal/1.0"


class TMDBError(Exception):
    """kind: 'auth' | 'network' | 'notfound' | 'other'"""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


class TMDBClient:
    def __init__(self, api_key: str, language: str = "pt-BR", timeout: int = 15):
        self.api_key = (api_key or "").strip()
        self.language = language
        self.timeout = timeout
        # Chave v3 tem 32 caracteres; o token de leitura v4 é um JWT bem mais longo.
        self._use_bearer = len(self.api_key) > 40

    def _request(self, url: str, retries: int = 2) -> bytes:
        if not self.api_key:
            raise TMDBError("Chave da API do TMDB não configurada.", "auth")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._use_bearer:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(url, headers=headers)
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise TMDBError("Chave da API inválida ou sem permissão.", "auth") from None
                if exc.code == 404:
                    raise TMDBError("Item não encontrado no TMDB.", "notfound") from None
                if exc.code in (429, 500, 502, 503) and attempt < retries:
                    try:
                        wait = float(exc.headers.get("Retry-After", 1 + attempt))
                    except (TypeError, ValueError):
                        wait = 1 + attempt
                    time.sleep(min(wait, 5))
                    continue
                raise TMDBError(f"Erro HTTP {exc.code} do TMDB.", "other") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise TMDBError("Sem conexão com o TMDB.", "network") from None
        raise TMDBError("Falha ao consultar o TMDB.", "other")

    def _get_json(self, path: str, **params) -> dict:
        query = {k: v for k, v in params.items() if v is not None}
        if not self._use_bearer:
            query["api_key"] = self.api_key
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(query)}"
        try:
            return json.loads(self._request(url))
        except ValueError:
            raise TMDBError("Resposta inválida do TMDB.", "other") from None

    # -- endpoints -----------------------------------------------------------
    def test_key(self) -> None:
        self._get_json("/configuration")

    def search_movie(self, query: str, year: int | None = None) -> list[dict]:
        data = self._get_json("/search/movie", query=query, year=year,
                              language=self.language, include_adult="false")
        return data.get("results", [])

    def movie_details(self, tmdb_id: int, language: str | None = None) -> dict:
        lang = language or self.language
        return self._get_json(
            f"/movie/{tmdb_id}",
            language=lang,
            append_to_response="credits,videos",
            include_video_language=f"{lang[:2]},en,null",
        )

    def download_image(self, size: str, file_path: str) -> bytes:
        return self._request(f"{IMAGE_BASE}/{size}{file_path}")
