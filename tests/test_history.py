"""Tests for the watch history and the home screen settings. Run with: python3 -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.filters import filter_movies, sidebar_counts


def row(path, title):
    return {"path": path, "file_name": path, "size": 1, "clean_title": title, "year_guess": None,
            "added_at": 1.0}


class WatchedDateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "lib.db")
        self.a, self.b = self.db.add_movies([row("/a.mkv", "A"), row("/b.mkv", "B")])

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def stamp(self, movie_id):
        return self.db.get_movie(movie_id)["watched_at"]

    def test_marking_records_the_date_and_unmarking_clears_it(self):
        self.assertIsNone(self.stamp(self.a))
        self.db.set_flag_many([self.a], "watched", True)
        self.assertGreater(self.stamp(self.a), 0)
        self.assertIsNone(self.stamp(self.b))
        self.db.set_flag_many([self.a], "watched", False)
        self.assertIsNone(self.stamp(self.a))

    def test_other_flags_do_not_touch_the_date(self):
        self.db.set_flag_many([self.a], "favorite", True)
        self.assertIsNone(self.stamp(self.a))

    def test_restoring_history_clears_dates(self):
        self.db.set_flag_many([self.a], "watched", True)
        self.db.restore(history=True)
        movie = self.db.get_movie(self.a)
        self.assertFalse(movie["watched"])
        self.assertIsNone(movie["watched_at"])


class HistoryFilterTests(unittest.TestCase):
    def test_history_uses_the_given_function(self):
        movies = [{"id": i, "genres": [], "favorite": False, "watchlist": False, "watched": False,
                   "status": "matched", "user_rating": 0, "search_text": ""} for i in (1, 2, 3)]
        stamps = {1: 0, 2: 5, 3: 1}.get
        found = filter_movies(movies, ("history", None), {}, history=lambda m: stamps(m["id"]))
        self.assertEqual([m["id"] for m in found], [2, 3])
        counts = sidebar_counts(movies, history=lambda m: stamps(m["id"]))
        self.assertEqual(counts["history"], 2)
        self.assertEqual(sidebar_counts(movies)["history"], 0)


if __name__ == "__main__":
    unittest.main()
