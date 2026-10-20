"""Threads de trabalho: tudo que acessa disco/rede fora da interface."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal

from .db import Database
from .metadata_service import process_movie
from .tmdb import TMDBClient, TMDBError


class FuncWorker(QThread):
    """Executa uma função em segundo plano e devolve (callback, valor) pela thread da UI."""

    done = Signal(object)

    def __init__(self, fn, on_result=None, on_error=None, parent=None):
        super().__init__(parent)
        self._fn, self._on_result, self._on_error = fn, on_result, on_error

    def run(self):
        try:
            value = self._fn()
        except Exception as exc:  # noqa: BLE001 - repassado para a UI
            self.done.emit((self._on_error, exc))
            return
        self.done.emit((self._on_result, value))


class UpdateWorker(QThread):
    """Atualiza metadados de vários filmes em paralelo (4 conexões)."""

    progress = Signal(int, int, str)       # feitos, total, título atual
    movie_done = Signal(int, str)          # id do filme, resultado
    finished_all = Signal(dict)            # resumo
    failed = Signal(str)

    def __init__(self, db: Database, api_key: str, language: str,
                 movies: list[dict], forced: dict[int, int] | None = None, parent=None):
        super().__init__(parent)
        self._db, self._key, self._language = db, api_key, language
        self._movies = movies
        self._forced = forced or {}
        self._cancel = threading.Event()
        self._auth_failed = False

    def cancel(self) -> None:
        self._cancel.set()

    def _one(self, client: TMDBClient, movie: dict) -> str:
        if self._cancel.is_set():
            return "cancelled"
        return process_movie(self._db, client, movie, self._forced.get(movie["id"]))

    def run(self):
        summary = {"matched": 0, "ambiguous": 0, "not_found": 0, "failed": 0, "cancelled": False}
        total, done = len(self._movies), 0
        client = TMDBClient(self._key, self._language)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(self._one, client, m): m for m in self._movies}
            for future in as_completed(futures):
                movie = futures[future]
                try:
                    outcome = future.result()
                except TMDBError as exc:
                    outcome = "failed"
                    if exc.kind == "auth" and not self._auth_failed:
                        self._auth_failed = True
                        self._cancel.set()
                        self.failed.emit(str(exc))
                except Exception:  # noqa: BLE001
                    outcome = "failed"
                if outcome == "cancelled":
                    summary["cancelled"] = True
                    continue
                summary[outcome] += 1
                done += 1
                self.movie_done.emit(movie["id"], outcome)
                self.progress.emit(done, total, movie["clean_title"])
        self.finished_all.emit(summary)
