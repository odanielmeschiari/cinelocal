"""Camada de acesso ao SQLite (sem Qt). Thread-safe via lock único."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

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
    "status",
}
FLAG_COLUMNS = {"watched", "favorite"}


def _loads(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _row_to_movie(row: sqlite3.Row) -> dict:
    m = dict(row)
    m["genres"] = _loads(m.pop("genres_json", None), [])
    m["cast"] = _loads(m.pop("cast_json", None), [])
    m["watched"] = bool(m["watched"])
    m["favorite"] = bool(m["favorite"])
    m["has_poster"] = bool(m["has_poster"])
    m["has_backdrop"] = bool(m["has_backdrop"])
    return m


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

    # -- filmes --------------------------------------------------------------
    def all_movies(self) -> list[dict]:
        return [_row_to_movie(r) for r in self._query("SELECT * FROM movies")]

    def get_movie(self, movie_id: int) -> dict | None:
        rows = self._query("SELECT * FROM movies WHERE id = ?", (movie_id,))
        return _row_to_movie(rows[0]) if rows else None

    def known_files(self) -> list[dict]:
        rows = self._query("SELECT id, path, file_name, size FROM movies")
        return [dict(r) for r in rows]

    def add_movies(self, rows: list[dict]) -> list[int]:
        ids = []
        with self._lock:
            for r in rows:
                cur = self._conn.execute(
                    "INSERT INTO movies (path, file_name, size, clean_title, year_guess,"
                    " added_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (r["path"], r["file_name"], r["size"], r["clean_title"],
                     r["year_guess"], r["added_at"], r["added_at"]),
                )
                ids.append(cur.lastrowid)
            self._conn.commit()
        return ids

    def update_path(self, movie_id: int, path: str) -> None:
        self._run("UPDATE movies SET path = ? WHERE id = ?", (path, movie_id))

    def remove_movies(self, ids: list[int]) -> None:
        if ids:
            self._many("DELETE FROM movies WHERE id = ?", [(i,) for i in ids])

    def save_metadata(self, movie_id: int, fields: dict) -> None:
        sets, values = [], []
        for key, value in fields.items():
            if key == "genres":
                sets.append("genres_json = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            elif key == "cast":
                sets.append("cast_json = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            elif key in METADATA_COLUMNS:
                sets.append(f"{key} = ?")
                values.append(value)
        sets.append("updated_at = ?")
        values.extend([time.time(), movie_id])
        self._run(f"UPDATE movies SET {', '.join(sets)} WHERE id = ?", values)

    def set_status(self, movie_id: int, status: str) -> None:
        self._run("UPDATE movies SET status = ?, updated_at = ? WHERE id = ?",
                  (status, time.time(), movie_id))

    def set_flag_many(self, ids: list[int], column: str, value: bool) -> None:
        if column not in FLAG_COLUMNS:
            raise ValueError(column)
        self._many(f"UPDATE movies SET {column} = ? WHERE id = ?",
                   [(int(value), i) for i in ids])

    # -- coleções ------------------------------------------------------------
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
            raise ValueError(f"Já existe uma coleção chamada “{name}”.") from None

    def rename_collection(self, collection_id: int, name: str) -> None:
        try:
            self._run("UPDATE collections SET name = ? WHERE id = ?", (name, collection_id))
        except sqlite3.IntegrityError:
            raise ValueError(f"Já existe uma coleção chamada “{name}”.") from None

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
