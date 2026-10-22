"""Tests for the Watchlist (no GUI). Run with: python3 -m unittest discover -s tests"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.filters import matches, sidebar_counts


class WatchlistTests(unittest.TestCase):
    def test_old_database_is_migrated_and_flag_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.db"
            old = sqlite3.connect(path)   # database from the previous version: no watchlist column
            old.execute("CREATE TABLE movies (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE,"
                        " file_name TEXT NOT NULL, size INTEGER DEFAULT 0, clean_title TEXT NOT NULL,"
                        " year_guess INTEGER, tmdb_id INTEGER, title TEXT, original_title TEXT, year INTEGER,"
                        " release_date TEXT, overview TEXT, tagline TEXT, runtime INTEGER, rating REAL,"
                        " votes INTEGER, genres_json TEXT DEFAULT '[]', director TEXT, cast_json TEXT DEFAULT '[]',"
                        " trailer_key TEXT, has_poster INTEGER DEFAULT 0, has_backdrop INTEGER DEFAULT 0,"
                        " status TEXT NOT NULL DEFAULT 'pending', watched INTEGER DEFAULT 0,"
                        " favorite INTEGER DEFAULT 0, added_at REAL NOT NULL, updated_at REAL NOT NULL)")
            old.execute("INSERT INTO movies (path, file_name, clean_title, added_at, updated_at)"
                        " VALUES ('/a.mkv', 'a.mkv', 'A', 1, 1)")
            old.commit()
            old.close()

            db = Database(path)
            movie = db.all_movies()[0]
            self.assertFalse(movie["watchlist"])
            db.set_flag_many([movie["id"]], "watchlist", True)
            movie = db.get_movie(movie["id"])
            self.assertTrue(movie["watchlist"])
            self.assertTrue(matches(movie, ("watchlist", None), {}))
            movie.update(genres=[], year=None, year_guess=None)
            self.assertEqual(sidebar_counts([movie])["watchlist"], 1)
            db.close()
            Database(path).close()   # opening again must not fail (column already exists)


if __name__ == "__main__":
    unittest.main()
