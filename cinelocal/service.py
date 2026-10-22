"""Central service: in-memory library state plus the operations used by the interface."""
from __future__ import annotations

import copy
import os
import threading
import time
import traceback

from PySide6.QtCore import QObject, Signal

from . import images, player
from .config import DEFAULT_SETTINGS, TRACK_LANGUAGES, Settings
from .db import Database
from .library import sync_library
from .metadata_service import find_candidates, find_series_candidates, process_movie, process_series
from .providers import make_client, same_provider
from .movie_fields import decorate
from .opensubtitles import OpenSubtitlesClient, OpenSubtitlesError, fetch_subtitle
from .workers import FuncWorker, UpdateWorker


class LibraryService(QObject):
    library_changed = Signal()          # list, collections or order changed
    movie_changed = Signal(int)         # a movie changed (metadata or flags)
    progress = Signal(int, int, str)    # done, total, title
    busy_changed = Signal(bool, str)    # busy?, description
    scan_finished = Signal(int, int)    # adicionados, removidos
    update_finished = Signal(dict)      # update summary
    message = Signal(str)               # short notice for the status bar
    error = Signal(str)

    def __init__(self, db: Database, settings: Settings, parent=None):
        super().__init__(parent)
        self.db, self.settings = db, settings
        self.movies: list[dict] = []        # movies and series (series have negative ids)
        self.episodes: dict[int, list[dict]] = {}   # series id (positive) -> episodes in order
        self.by_id: dict[int, dict] = {}
        self.collections: list[dict] = []
        self.membership: dict[int, set[int]] = {}
        self._update_worker: UpdateWorker | None = None
        self._jobs: set[FuncWorker] = set()
        self._scanning = False
        self._subtitling = False            # subtitles being downloaded in the background
        self._subtitle_stop = threading.Event()

    # -- estado ----------------------------------------------------------------
    @property
    def has_key(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def provider(self) -> str:
        return self.settings.get("provider")

    @property
    def api_key(self) -> str:
        return self.settings.get("omdb_api_key" if self.provider == "omdb" else "tmdb_api_key")

    @property
    def language(self) -> str:
        return self.settings.get("language")

    @property
    def updating(self) -> bool:
        return self._update_worker is not None

    def reload(self) -> None:
        movies, self.episodes = [], {}
        for m in map(decorate, self.db.all_movies()):
            if m.get("kind") == "episode":
                self.episodes.setdefault(m["series_id"], []).append(m)
            else:
                movies.append(m)
        for items in self.episodes.values():
            items.sort(key=lambda e: (e["season"] or 0, e["episode"] or 0, e["path"]))
        self.movies = movies + [self._series_entry(s) for s in self.db.all_series()]
        self.by_id = {m["id"]: m for m in self.movies}
        for items in self.episodes.values():
            self.by_id.update({e["id"]: e for e in items})
        self.collections = self.db.all_collections()
        self.membership = self.db.membership()

    def _series_entry(self, row: dict) -> dict:
        """Series in the same format as a movie, for the grid, filters and search (id = -series id)."""
        eps = self.episodes.get(row["id"], [])
        entry = dict(row)
        entry.update(id=-row["id"], series_id=row["id"], kind="series", path="",
                     file_name=row["clean_title"], size=0,
                     watched=bool(eps) and all(e["watched"] for e in eps),
                     season_count=len({e["season"] for e in eps}), episode_count=len(eps))
        return decorate(entry)

    def _refresh_series(self, series_id: int) -> None:
        row = self.db.get_series(series_id)
        if row is None:
            return
        old = {e["id"]: e for e in self.episodes.get(series_id, [])}
        fresh_eps = []
        for fresh in self.db.episodes_of(series_id):
            episode = old.get(fresh["id"], {})
            episode.clear()
            episode.update(decorate(fresh))
            self.by_id[episode["id"]] = episode
            fresh_eps.append(episode)
        self.episodes[series_id] = fresh_eps
        entry, current = self._series_entry(row), self.by_id.get(-series_id)
        if current is None:
            self.movies.append(entry)
            self.by_id[entry["id"]] = entry
        else:
            current.clear()
            current.update(entry)
        self.movie_changed.emit(-series_id)

    def next_episode(self, series_id: int) -> int | None:
        """Episode for 'Watch' on a series: the first unwatched one (or the first of all)."""
        eps = self.episodes.get(series_id, [])
        pick = next((e for e in eps if not e["watched"]), eps[0] if eps else None)
        return pick["id"] if pick else None

    def _pending(self) -> list[dict]:
        """Items that need metadata: new ones, and series with new episodes."""
        return [m for m in self.movies if m["status"] == "pending"
                or (m.get("kind") == "series" and m["status"] == "matched"
                    and any(e["status"] == "pending" for e in self.episodes.get(-m["id"], ())))]

    def _refresh_movie(self, movie_id: int) -> None:
        if movie_id < 0:
            return self._refresh_series(-movie_id)
        fresh = self.db.get_movie(movie_id)
        current = self.by_id.get(movie_id)
        if fresh is None or current is None:
            return
        current.clear()
        current.update(decorate(fresh))   # update in place: the grid model sees the change
        self.movie_changed.emit(movie_id)

    def _client(self):
        return make_client(self.provider, self.api_key, self.language)

    # -- asynchronous execution -----------------------------------------------------
    def run_async(self, fn, on_result=None, on_error=None) -> None:
        worker = FuncWorker(fn, on_result, on_error, self)
        self._jobs.add(worker)
        worker.done.connect(self._dispatch)
        worker.finished.connect(lambda w=worker: self._jobs.discard(w))
        worker.start()

    def _dispatch(self, payload) -> None:
        callback, value = payload
        if callback is None:
            return
        try:
            callback(value)
        except RuntimeError:
            pass  # target widget was already destroyed
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    def _report(self, exc: Exception) -> None:
        self.error.emit(str(exc))

    # -- varredura ---------------------------------------------------------------
    def start_scan(self) -> None:
        root = self.settings.get("library_path")
        if not root:
            return
        if not os.path.isdir(root):
            self.error.emit(f"The movies folder is not accessible:\n{root}")
            return
        if self._scanning:
            return
        self._scanning = True
        self.busy_changed.emit(True, "Scanning the folder for movies…")
        self.run_async(lambda: sync_library(self.db, root), self._on_scan_done, self._on_scan_error)

    def _on_scan_done(self, result) -> None:
        added, removed = result
        for movie_id in removed:
            images.delete_images(movie_id)
        old_series = {i for i in self.by_id if i < 0}
        self._scanning = False
        self.reload()
        for series_id in old_series - set(self.by_id):   # series without episodes: delete the poster
            images.delete_images(series_id)
        self.library_changed.emit()
        self.scan_finished.emit(len(added), len(removed))
        self.download_subtitles(added)
        if not self.updating:
            self.busy_changed.emit(False, "")
        if self.has_key and self._pending():
            self.start_update("pending")

    def _on_scan_error(self, exc: Exception) -> None:
        self._scanning = False
        self.busy_changed.emit(False, "")
        self._report(exc)

    # -- subtitles (OpenSubtitles) --------------------------------------------------------
    def _subtitle_languages(self) -> str:
        """OpenSubtitles language(s) to download ('' = none): the subtitle language of the settings or, while it's
        left on "file default", the metadata language."""
        choice = self.settings.get("subtitle_language")
        if choice in ("off", "forced"):
            return ""
        code = choice if choice in TRACK_LANGUAGES else self.language[:2].lower()
        return "pt-br,pt-pt" if code == "pt" else code

    def download_subtitles(self, added: list[int]) -> None:
        """Queues the new files and downloads their subtitles in the background (only with an OpenSubtitles key).
        They are saved next to the videos, so they load every time a movie is played. The queue is kept in the
        settings: what is left when the daily download limit is hit is tried again on the next scan."""
        key = (self.settings.get("opensubtitles_api_key") or "").strip()
        languages = self._subtitle_languages()
        if not key or not languages:
            return
        queue = list(self.settings.get("subtitle_queue") or [])
        for movie_id in added:
            path = (self.by_id.get(movie_id) or {}).get("path")
            if path and path not in queue:
                queue.append(path)
        entries = [(path, self.by_path(path)) for path in queue]
        entries = [(path, m) for path, m in entries if m is not None]   # files that left the library are dropped
        self.settings.update(subtitle_queue=[path for path, _m in entries])
        if not entries or self._subtitling:
            return
        jobs = [(path, m["clean_title"], m["year_guess"],
                 m["season"] if m.get("kind") == "episode" else None,
                 m["episode"] if m.get("kind") == "episode" else None) for path, m in entries]
        client = OpenSubtitlesClient(key)
        self._subtitling = True
        self._subtitle_stop.clear()

        def job():
            handled, saved, failed, problem = [], 0, 0, None
            for path, title, year, season, episode in jobs:
                if self._subtitle_stop.is_set():
                    break
                try:
                    saved += bool(fetch_subtitle(client, path, title, year, languages, season, episode))
                except OpenSubtitlesError as exc:
                    if exc.kind != "other":   # key rejected, limit reached or offline: the rest waits
                        problem = exc
                        break
                except OSError:   # unreadable video or folder that cannot be written to
                    failed += 1
                handled.append(path)
            return handled, saved, failed, problem

        def done(result):
            handled, saved, failed, problem = result
            self._subtitling = False
            handled = set(handled)
            self.settings.update(subtitle_queue=[p for p in self.settings.get("subtitle_queue") or []
                                                 if p not in handled])
            notes = [f"{saved} subtitle(s) downloaded."] if saved else []
            if failed:
                notes.append(f"{failed} could not be saved (is the movies folder writable?).")
            if problem is not None and problem.kind == "auth":
                self.error.emit(str(problem))
            elif problem is not None:
                notes.append(f"{problem} The rest will be tried on the next scan.")
            if notes:
                self.message.emit(" ".join(notes))

        def failed_job(exc):
            self._subtitling = False
            self._report(exc)

        self.run_async(job, done, failed_job)

    # -- metadata update ----------------------------------------------------
    def start_update(self, mode: str = "pending", ids: list[int] | None = None) -> bool:
        """mode: 'pending' (new only), 'all' (force all) or 'ids'."""
        if self.updating:
            self.message.emit("An update is already in progress.")
            return False
        if not self.has_key:
            self.error.emit("Set your API key in Settings to download metadata.")
            return False
        if mode == "pending":
            targets = self._pending()
        elif mode == "ids":
            targets = [self.by_id[i] for i in (ids or []) if i in self.by_id]
        else:
            targets = list(self.movies)
        if not targets:
            self.message.emit("No movies to update.")
            return False

        # Movies already identified keep their match (including manual corrections).
        forced = {m["id"]: m["tmdb_id"] for m in targets
                  if m["status"] == "matched" and same_provider(self.provider, m["tmdb_id"])}
        snapshot = [{k: m[k] for k in ("id", "clean_title", "year_guess", "tmdb_id", "status", "kind")}
                    for m in targets]
        worker = UpdateWorker(self.db, self.api_key, self.language,
                              snapshot, forced, self, provider=self.provider)
        worker.progress.connect(self.progress)
        worker.movie_done.connect(self._on_movie_done)
        worker.finished_all.connect(self._on_update_done)
        worker.failed.connect(self.error)
        worker.finished.connect(self._on_worker_finished)
        self._update_worker = worker
        self.busy_changed.emit(True, "Fetching metadata…")
        self.progress.emit(0, len(snapshot), "")
        worker.start()
        return True

    def cancel_update(self) -> None:
        if self._update_worker:
            self._update_worker.cancel()

    def _on_movie_done(self, movie_id: int, _outcome: str) -> None:
        self._refresh_movie(movie_id)

    def _on_update_done(self, summary: dict) -> None:
        self.library_changed.emit()
        self.update_finished.emit(summary)

    def _on_worker_finished(self) -> None:
        worker, self._update_worker = self._update_worker, None
        if worker:
            worker.deleteLater()
        self.busy_changed.emit(False, "")

    # -- actions on a movie ------------------------------------------------------------
    def apply_match(self, movie_id: int, tmdb_id: int | None = None) -> None:
        """Sets (or updates) a movie's match with TMDB."""
        if not self.has_key:
            self.error.emit("Set your API key in Settings.")
            return
        movie = self.by_id.get(movie_id)
        if movie is None:
            return
        if tmdb_id is None and movie["status"] == "matched" and same_provider(self.provider, movie["tmdb_id"]):
            tmdb_id = movie["tmdb_id"]
        snapshot = {k: movie[k] for k in ("id", "clean_title", "year_guess", "tmdb_id", "status", "kind")}
        process = process_series if movie_id < 0 else process_movie

        def job():
            return process(self.db, self._client(), snapshot, tmdb_id)

        def done(outcome):
            self._refresh_movie(movie_id)
            self.library_changed.emit()
            if outcome != "matched":
                self.message.emit("No confident match; use “Fix match”.")

        self.message.emit(f"Updating “{movie['display_title']}”…")
        self.run_async(job, done, self._report)

    def edit_metadata(self, movie_id: int, fields: dict, poster_path: str = "") -> None:
        """Saves metadata typed by the user for a movie or series, and a cover picked from a file. What was edited
        is remembered (`custom`), so later metadata updates do not overwrite it. Raises ValueError/OSError if the
        cover cannot be read."""
        item = self.by_id.get(movie_id)
        if item is None:
            return
        custom = set(item.get("custom", [])) | set(fields)
        if poster_path:
            with open(poster_path, "rb") as f:
                if not images.store_poster(movie_id, f.read()):
                    raise ValueError("The chosen file is not a valid image.")
            custom.add("poster")
            fields = {**fields, "has_poster": True}
        table = "series" if movie_id < 0 else "movies"
        self.db.save_metadata(abs(movie_id), {**fields, "custom": sorted(custom)}, table)
        self._refresh_movie(movie_id)
        self.library_changed.emit()

    def reset_edits(self, movie_id: int) -> None:
        """Forgets the user's edits of a movie or series and downloads its metadata again."""
        if not self.has_key:
            self.error.emit("Set your API key in Settings.")
            return
        self.db.save_metadata(abs(movie_id), {"custom": []}, "series" if movie_id < 0 else "movies")
        self.apply_match(movie_id)

    def search_tmdb(self, query: str, year: int | None, on_result, on_error, series: bool = False) -> None:
        find = find_series_candidates if series else find_candidates
        self.run_async(lambda: find(self._client(), query, year), on_result, on_error)

    def test_key(self, key: str, on_result, on_error, provider: str | None = None) -> None:
        def job():
            make_client(provider or self.provider, key, self.language).test_key()
            return True
        self.run_async(job, on_result, on_error)

    def set_flag(self, movie_ids: list[int], column: str, value: bool) -> None:
        series_ids = [-i for i in movie_ids if i < 0]
        movie_ids = [i for i in movie_ids if i > 0]
        if series_ids and column == "watched":   # watched series = all episodes watched
            movie_ids += [e["id"] for s in series_ids for e in self.episodes.get(s, [])]
        elif series_ids:
            self.db.set_series_flag(series_ids, column, value)
            for series_id in series_ids:
                if -series_id in self.by_id:
                    self.by_id[-series_id][column] = value
                    self.movie_changed.emit(-series_id)
        self.db.set_flag_many(movie_ids, column, value)
        touched = set()
        for movie_id in movie_ids:
            if movie_id in self.by_id:
                self.by_id[movie_id][column] = value
                if column == "watched":
                    self.by_id[movie_id]["watched_at"] = time.time() if value else None
                if self.by_id[movie_id].get("kind") == "episode":
                    touched.add(self.by_id[movie_id]["series_id"])
                else:
                    self.movie_changed.emit(movie_id)
        for series_id in touched:   # the series' "watched" state comes from its episodes
            entry = self.by_id.get(-series_id)
            if entry is not None and column == "watched":
                eps = self.episodes.get(series_id, [])
                entry["watched"] = bool(eps) and all(e["watched"] for e in eps)
            self.movie_changed.emit(-series_id)

    def set_review(self, movie_id: int, rating: int, comment: str) -> None:
        """Saves the user's own rating (0 = none, 0.5-5 stars) and comment for a movie or a whole series."""
        if movie_id < 0:
            self.db.set_review(-movie_id, rating, comment, "series")
        else:
            self.db.set_review(movie_id, rating, comment)
        if movie_id in self.by_id:
            self.by_id[movie_id].update(user_rating=rating, user_comment=comment)
            self.movie_changed.emit(movie_id)

    def restore(self, kinds: set[str]) -> bool:
        """Erases data. kinds: 'metadata' (and covers), 'history', 'favorites', 'collections', 'reviews',
        'settings' or 'everything' (the library too, back to a first run). False if busy."""
        if self.updating or self._scanning:
            self.error.emit("Wait for the scan or metadata update in progress to finish.")
            return False
        everything = "everything" in kinds
        if everything or "metadata" in kinds:
            images.delete_all_images()
        self.db.restore(metadata="metadata" in kinds, history="history" in kinds,
                        favorites="favorites" in kinds, collections="collections" in kinds,
                        reviews="reviews" in kinds, everything=everything)
        reset = {}
        if everything or "history" in kinds:
            reset["resume"] = DEFAULT_SETTINGS["resume"]
        if everything or "settings" in kinds:   # the sort order and the install offer are not touched
            reset.update({k: v for k, v in DEFAULT_SETTINGS.items()
                          if k not in ("resume", "sort_id", "skip_install_prompt")})
        self.settings.update(**copy.deepcopy(reset))
        self.reload()
        self.library_changed.emit()
        if self.has_key and self._pending():   # erased metadata is downloaded again, as after any scan
            self.start_update("pending")
        return True

    def remember_tracks(self, path: str, choices: dict) -> None:
        """Keeps the audio/subtitle tracks picked by hand for this file (used the next time it plays)."""
        saved = dict(self.settings.get("track_choices") or {})
        saved[path] = choices
        self.settings.update(track_choices=saved)

    # -- continuar assistindo -----------------------------------------------------------
    def resume_info(self, path: str) -> tuple[int, int, int]:
        """(position ms, duration ms, when it was saved) of a file; zeros if none."""
        value = (self.settings.get("resume") or {}).get(path)
        if isinstance(value, (int, float)):   # old format: position only
            return int(value), 0, 0
        if isinstance(value, list) and len(value) >= 3:
            return int(value[0]), int(value[1]), int(value[2])
        return 0, 0, 0

    def _resume_path(self, movie: dict) -> str:
        """File whose position applies to this item: the movie itself or, for a series, the episode
        in progress (the last one watched)."""
        if movie.get("kind") != "series":
            return movie.get("path") or ""
        best, best_when = "", -1
        for episode in self.episodes.get(-movie["id"], []):
            position, _, when = self.resume_info(episode["path"])
            if position > 0 and when >= best_when:
                best, best_when = episode["path"], when
        return best

    def progress_of(self, movie: dict) -> float:
        """Fraction already watched (0 to 1) of a movie (or of a series' episode in progress)."""
        position, length, _ = self.resume_info(self._resume_path(movie))
        return min(1.0, position / length) if position > 0 and length > 0 else 0.0

    def last_played(self, movie: dict) -> int:
        return self.resume_info(self._resume_path(movie))[2]

    def history_stamp(self, movie: dict) -> float:
        """When the movie (or any episode of the series) was last watched, even if only in part. 0 = it is
        not in the history; 1 = it is, but nobody knows when (watched before dates were recorded)."""
        if movie.get("kind") == "series":
            return max((self.history_stamp(e) for e in self.episodes.get(-movie["id"], [])), default=0)
        position, _, saved = self.resume_info(movie.get("path") or "")
        if not (movie["watched"] or position > 0):
            return 0
        return max(movie.get("watched_at") or 0, saved, 1)

    def restart(self, movie: dict) -> None:
        """Forgets where the movie stopped, to watch from the start."""
        path = self._resume_path(movie)
        if path:
            self.save_progress(path, 0, 0)

    def by_path(self, path: str) -> dict | None:
        return next((m for m in self.by_id.values()
                     if m.get("path") == path and m.get("kind") != "series"), None)

    def mark_finished(self, path: str) -> None:
        """Reached the end (95%+): marks as watched."""
        movie = self.by_path(path)
        if movie is not None and not movie["watched"]:
            self.set_flag([movie["id"]], "watched", True)

    def episode_after(self, episode: dict) -> dict | None:
        episodes = self.episodes.get(episode.get("series_id"), [])
        for i, e in enumerate(episodes):
            if e["id"] == episode["id"]:
                return episodes[i + 1] if i + 1 < len(episodes) else None
        return None

    def save_progress(self, path: str, position: int, length: int) -> None:
        """Stores where the movie stopped (position 0, or very early, deletes the record)."""
        resume = dict(self.settings.get("resume") or {})
        had = path in resume
        if position >= 10000:
            resume[path] = [int(position), int(length), int(time.time())]
        elif had:
            del resume[path]
        else:
            return
        self.settings.update(resume=resume)
        if had != (path in resume):   # entered or left "Continue watching"
            for movie in self.by_id.values():
                if movie.get("path") == path:
                    self.movie_changed.emit(movie["id"])
                    if movie.get("kind") == "episode":   # the series poster shows the episode in progress
                        self.movie_changed.emit(-movie["series_id"])
                    break

    def play(self, movie_id: int) -> None:
        player.play(self.by_id[movie_id]["path"], self.settings.get("player_command"))

    def show_in_folder(self, movie_id: int) -> None:
        player.show_in_folder(self.by_id[movie_id]["path"])

    # -- collections ------------------------------------------------------------------
    def create_collection(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Enter a name for the collection.")
        collection_id = self.db.create_collection(name)
        self._reload_collections()
        return collection_id

    def rename_collection(self, collection_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Enter a name for the collection.")
        self.db.rename_collection(collection_id, name)
        self._reload_collections()

    def delete_collection(self, collection_id: int) -> None:
        self.db.delete_collection(collection_id)
        self._reload_collections()

    def collection_name(self, collection_id: int) -> str:
        return next((c["name"] for c in self.collections if c["id"] == collection_id), "")

    def set_in_collection(self, collection_id: int, movie_ids: list[int], present: bool) -> None:
        self.db.set_membership(collection_id, movie_ids, present)
        members = self.membership.setdefault(collection_id, set())
        if present:
            members.update(movie_ids)
        else:
            members.difference_update(movie_ids)
        self.library_changed.emit()

    def _reload_collections(self) -> None:
        self.collections = self.db.all_collections()
        self.membership = self.db.membership()
        self.library_changed.emit()

    # -- encerramento ----------------------------------------------------------------------
    def shutdown(self) -> None:
        self._subtitle_stop.set()
        if self._update_worker:
            self._update_worker.cancel()
            self._update_worker.wait(5000)
        for job in list(self._jobs):
            job.wait(3000)
