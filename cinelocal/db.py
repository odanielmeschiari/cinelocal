"""SQLite access layer (no Qt). Thread-safe through a single lock."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .utils import comparable_title

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    size INTEGER DEFAULT 0,
    clean_title TEXT NOT NULL,
    year_guess INTEGER,
    tmdb_id INTEGER,
    title TEXT,
    original_title TEXT,
    year INTEGER,
    release_date TEXT,
    overview TEXT,
    tagline TEXT,
    runtime INTEGER,
    rating REAL,
    votes INTEGER,
    genres_json TEXT DEFAULT '[]',
    director TEXT,
    cast_json TEXT DEFAULT '[]',
    trailer_key TEXT,
    has_poster INTEGER DEFAULT 0,
    has_backdrop INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    watched INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    added_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_movies_status ON movies(status);

CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    clean_title TEXT NOT NULL,
    year_guess INTEGER,
    tmdb_id INTEGER,
    title TEXT,
    original_title TEXT,
    year INTEGER,
    release_date TEXT,
    overview TEXT,
    tagline TEXT,
    runtime INTEGER,
    rating REAL,
    votes INTEGER,
    genres_json TEXT DEFAULT '[]',
    director TEXT,
    cast_json TEXT DEFAULT '[]',
    trailer_key TEXT,
    has_poster INTEGER DEFAULT 0,
    has_backdrop INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    favorite INTEGER DEFAULT 0,
    watchlist INTEGER DEFAULT 0,
    added_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_movies (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    added_at REAL NOT NULL,
    PRIMARY KEY (collection_id, movie_id)
);
"""

METADATA_COLUMNS = {
    "tmdb_id", "title", "original_title", "year", "release_date", "overview", "tagline",
    "runtime", "rating", "votes", "director", "trailer_key", "has_poster", "has_backdrop",
    "status", "certification",
}
FLAG_COLUMNS = {"watched", "favorite", "watchlist"}
EPISODE_COLUMNS = {"ep_title", "ep_overview", "ep_air_date", "ep_runtime", "ep_rating"}
# Columns added after the first version, for movies and series: the user's review, the list of fields (and
# "poster") edited by hand, which a metadata update must not overwrite, and the age rating.
_REVIEW_COLUMNS = (("user_rating", "INTEGER DEFAULT 0"), ("user_comment", "TEXT DEFAULT ''"),
                   ("custom_json", "TEXT DEFAULT '[]'"), ("certification", "TEXT"))
# Series/episode columns added to databases created by earlier versions.
_MIGRATIONS = (
    ("kind", "TEXT DEFAULT 'movie'"), ("series_id", "INTEGER"), ("season", "INTEGER"),
    ("episode", "INTEGER"), ("ep_title", "TEXT"), ("ep_overview", "TEXT"),
    ("ep_air_date", "TEXT"), ("ep_runtime", "INTEGER"), ("ep_rating", "REAL"),
    ("watched_at", "REAL"),   # when it was marked as watched (the history is ordered by it)
    *_REVIEW_COLUMNS,
)


def _loads(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _row_to_movie(row: sqlite3.Row) -> dict:
    m = dict(row)
    m["genres"] = _loads(m.pop("genres_json", None), [])
    m["cast"] = _loads(m.pop("cast_json", None), [])
    m["custom"] = _loads(m.pop("custom_json", None), [])
    m["watched"] = bool(m["watched"])
    m["favorite"] = bool(m["favorite"])
    m["watchlist"] = bool(m["watchlist"])
    m["has_poster"] = bool(m["has_poster"])
    m["has_backdrop"] = bool(m["has_backdrop"])
    return m


def _row_to_series(row: sqlite3.Row) -> dict:
    s = dict(row)
    s["genres"] = _loads(s.pop("genres_json", None), [])
    s["cast"] = _loads(s.pop("cast_json", None), [])
    s["custom"] = _loads(s.pop("custom_json", None), [])
    for key in ("favorite", "watchlist", "has_poster", "has_backdrop"):
        s[key] = bool(s[key])
    return s


class Database:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            try:   # migration: databases created before the Watchlist lack the column
                self._conn.execute("ALTER TABLE movies ADD COLUMN watchlist INTEGER DEFAULT 0")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            for column, ddl in _MIGRATIONS:   # migration: series and episodes
                try:
                    self._conn.execute(f"ALTER TABLE movies ADD COLUMN {column} {ddl}")
                    self._conn.commit()
                except sqlite3.OperationalError:
                    pass
            for column, ddl in _REVIEW_COLUMNS:   # migration: the user's rating of a whole series
                try:
                    self._conn.execute(f"ALTER TABLE series ADD COLUMN {column} {ddl}")
                    self._conn.commit()
                except sqlite3.OperationalError:
                    pass
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_series ON movies(series_id)")

    # -- infra ---------------------------------------------------------------
    def _run(self, sql: str, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query(self, sql: str, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _many(self, sql: str, rows):
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- movies --------------------------------------------------------------
    def all_movies(self) -> list[dict]:
        return [_row_to_movie(r) for r in self._query("SELECT * FROM movies")]

    def get_movie(self, movie_id: int) -> dict | None:
        rows = self._query("SELECT * FROM movies WHERE id = ?", (movie_id,))
        return _row_to_movie(rows[0]) if rows else None

    def known_files(self) -> list[dict]:
        rows = self._query("SELECT id, path, file_name, size, kind FROM movies")
        return [dict(r) for r in rows]

    def add_movies(self, rows: list[dict]) -> list[int]:
        ids = []
        with self._lock:
            for r in rows:
                cur = self._conn.execute(
                    "INSERT INTO movies (path, file_name, size, clean_title, year_guess,"
                    " added_at, updated_at, kind, series_id, season, episode)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["path"], r["file_name"], r["size"], r["clean_title"],
                     r["year_guess"], r["added_at"], r["added_at"], r.get("kind", "movie"),
                     r.get("series_id"), r.get("season"), r.get("episode")),
                )
                ids.append(cur.lastrowid)
            self._conn.commit()
        return ids

    def update_path(self, movie_id: int, path: str) -> None:
        self._run("UPDATE movies SET path = ? WHERE id = ?", (path, movie_id))

    def remove_movies(self, ids: list[int]) -> None:
        if ids:
            self._many("DELETE FROM movies WHERE id = ?", [(i,) for i in ids])

    def save_metadata(self, movie_id: int, fields: dict, table: str = "movies") -> None:
        if table not in ("movies", "series"):
            raise ValueError(table)
        sets, values = [], []
        for key, value in fields.items():
            if key == "genres":
                sets.append("genres_json = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            elif key == "cast":
                sets.append("cast_json = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            elif key == "custom":
                sets.append("custom_json = ?")
                values.append(json.dumps(value))
            elif key in METADATA_COLUMNS:
                sets.append(f"{key} = ?")
                values.append(value)
        sets.append("updated_at = ?")
        values.extend([time.time(), movie_id])
        self._run(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", values)

    def set_status(self, movie_id: int, status: str, table: str = "movies") -> None:
        if table not in ("movies", "series"):
            raise ValueError(table)
        self._run(f"UPDATE {table} SET status = ?, updated_at = ? WHERE id = ?",
                  (status, time.time(), movie_id))

    def set_flag_many(self, ids: list[int], column: str, value: bool) -> None:
        if column not in FLAG_COLUMNS:
            raise ValueError(column)
        if column == "watched":
            now = time.time() if value else None
            return self._many("UPDATE movies SET watched = ?, watched_at = ? WHERE id = ?",
                              [(int(value), now, i) for i in ids])
        self._many(f"UPDATE movies SET {column} = ? WHERE id = ?",
                   [(int(value), i) for i in ids])

    def set_review(self, item_id: int, rating: int, comment: str, table: str = "movies") -> None:
        if table not in ("movies", "series"):
            raise ValueError(table)
        self._run(f"UPDATE {table} SET user_rating = ?, user_comment = ? WHERE id = ?",
                  (rating, comment, item_id))

    # -- series and episodes -----------------------------------------------------
    def ensure_series(self, title: str, year: int | None = None) -> int:
        """Id of the series with this title (created if missing). The key ignores accents and articles."""
        key = comparable_title(title) or title.lower()
        with self._lock:
            rows = self._query("SELECT id, year_guess FROM series WHERE key = ?", (key,))
            if rows:
                if year and not rows[0]["year_guess"]:
                    self._run("UPDATE series SET year_guess = ? WHERE id = ?", (year, rows[0]["id"]))
                return rows[0]["id"]
            now = time.time()
            return self._run("INSERT INTO series (key, clean_title, year_guess, added_at, updated_at)"
                             " VALUES (?, ?, ?, ?, ?)", (key, title, year, now, now)).lastrowid

    def all_series(self) -> list[dict]:
        return [_row_to_series(r) for r in self._query("SELECT * FROM series")]

    def get_series(self, series_id: int) -> dict | None:
        rows = self._query("SELECT * FROM series WHERE id = ?", (series_id,))
        return _row_to_series(rows[0]) if rows else None

    def episodes_of(self, series_id: int) -> list[dict]:
        rows = self._query("SELECT * FROM movies WHERE series_id = ? ORDER BY season, episode, path",
                           (series_id,))
        return [_row_to_movie(r) for r in rows]

    def convert_to_episode(self, movie_id: int, series_id: int, title: str,
                           year: int | None, season: int, episode: int) -> None:
        """Turns an already registered 'movie' (an episode file) into a series episode."""
        self._run(
            "UPDATE movies SET kind = 'episode', series_id = ?, season = ?, episode = ?,"
            " clean_title = ?, year_guess = ?, status = 'pending', tmdb_id = NULL, title = NULL,"
            " original_title = NULL, year = NULL, release_date = NULL, overview = NULL,"
            " tagline = NULL, runtime = NULL, rating = NULL, votes = NULL, genres_json = '[]',"
            " director = NULL, cast_json = '[]', trailer_key = NULL, has_poster = 0,"
            " has_backdrop = 0, updated_at = ? WHERE id = ?",
            (series_id, season, episode, title, year, time.time(), movie_id))

    def save_episode(self, movie_id: int, fields: dict) -> None:
        sets = [f"{k} = ?" for k in fields if k in EPISODE_COLUMNS]
        values = [v for k, v in fields.items() if k in EPISODE_COLUMNS]
        self._run(f"UPDATE movies SET {', '.join(sets + ['status = ?', 'updated_at = ?'])} WHERE id = ?",
                  values + ["matched", time.time(), movie_id])

    def set_series_flag(self, series_ids: list[int], column: str, value: bool) -> None:
        if column not in ("favorite", "watchlist"):
            raise ValueError(column)
        self._many(f"UPDATE series SET {column} = ? WHERE id = ?", [(int(value), i) for i in series_ids])

    def prune_series(self) -> list[int]:
        """Deletes series left without episodes. Returns the deleted ids."""
        rows = self._query("SELECT id FROM series WHERE id NOT IN"
                           " (SELECT series_id FROM movies WHERE series_id IS NOT NULL)")
        ids = [r["id"] for r in rows]
        if ids:
            self._many("DELETE FROM series WHERE id = ?", [(i,) for i in ids])
        return ids

    # -- restore -------------------------------------------------------------------
    def restore(self, metadata=False, history=False, favorites=False, collections=False,
                reviews=False, everything=False) -> None:
        """Erases the chosen kinds of data. `everything` also forgets the library itself (a rescan rebuilds it)."""
        with self._lock:
            run = self._conn.execute
            if everything:
                for table in ("collection_movies", "collections", "movies", "series"):
                    run(f"DELETE FROM {table}")
            if metadata and not everything:
                for table, extra in (("movies", ", ep_title = NULL, ep_overview = NULL, ep_air_date = NULL,"
                                                " ep_runtime = NULL, ep_rating = NULL"), ("series", "")):
                    run(f"UPDATE {table} SET status = 'pending', tmdb_id = NULL, title = NULL, original_title = NULL,"
                        " year = NULL, release_date = NULL, overview = NULL, tagline = NULL, runtime = NULL,"
                        " rating = NULL, votes = NULL, genres_json = '[]', director = NULL, cast_json = '[]',"
                        f" trailer_key = NULL, has_poster = 0, has_backdrop = 0, custom_json = '[]', certification = NULL, updated_at = ?{extra}", (time.time(),))
            if history and not everything:
                run("UPDATE movies SET watched = 0, watched_at = NULL")
            if favorites and not everything:
                run("UPDATE movies SET favorite = 0, watchlist = 0")
                run("UPDATE series SET favorite = 0, watchlist = 0")
            if reviews and not everything:
                for table in ("movies", "series"):
                    run(f"UPDATE {table} SET user_rating = 0, user_comment = ''")
            if collections and not everything:
                run("DELETE FROM collection_movies")
                run("DELETE FROM collections")
            self._conn.commit()

    # -- collections ------------------------------------------------------------
    def all_collections(self) -> list[dict]:
        rows = self._query("SELECT id, name FROM collections ORDER BY name COLLATE NOCASE")
        return [dict(r) for r in rows]

    def membership(self) -> dict[int, set[int]]:
        result: dict[int, set[int]] = {}
        for r in self._query("SELECT collection_id, movie_id FROM collection_movies"):
            result.setdefault(r["collection_id"], set()).add(r["movie_id"])
        return result

    def create_collection(self, name: str) -> int:
        try:
            return self._run("INSERT INTO collections (name, created_at) VALUES (?, ?)",
                             (name, time.time())).lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"A collection named “{name}” already exists.") from None

    def rename_collection(self, collection_id: int, name: str) -> None:
        try:
            self._run("UPDATE collections SET name = ? WHERE id = ?", (name, collection_id))
        except sqlite3.IntegrityError:
            raise ValueError(f"A collection named “{name}” already exists.") from None

    def delete_collection(self, collection_id: int) -> None:
        self._run("DELETE FROM collections WHERE id = ?", (collection_id,))

    def set_membership(self, collection_id: int, movie_ids: list[int], present: bool) -> None:
        if present:
            now = time.time()
            self._many("INSERT OR IGNORE INTO collection_movies"
                       " (collection_id, movie_id, added_at) VALUES (?, ?, ?)",
                       [(collection_id, i, now) for i in movie_ids])
        else:
            self._many("DELETE FROM collection_movies WHERE collection_id = ? AND movie_id = ?",
                       [(collection_id, i) for i in movie_ids])
