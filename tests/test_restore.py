"""Tests for "Restore app" (Database.restore). Run with: python3 -m unittest discover -s tests"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "lib.db")
        (self.movie,) = self.db.add_movies([dict(
            path="/m/a.mkv", file_name="a.mkv", size=1, clean_title="A", year_guess=2000, added_at=time.time())])
        self.db.save_metadata(self.movie, {"tmdb_id": 5, "title": "A", "overview": "x", "has_poster": True,
                                           "status": "matched", "genres": ["Drama"],
                                           "extra": {"budget": 1200}})
        self.db.set_flag_many([self.movie], "watched", True)
        self.db.set_flag_many([self.movie], "favorite", True)
        self.db.set_review(self.movie, 4, "good")
        self.db.set_membership(self.db.create_collection("C"), [self.movie], True)
        self.tag_id = self.db.create_tag("Classic")
        self.db.set_movie_tag(self.movie, self.tag_id, True)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_metadata_only(self):
        self.db.restore(metadata=True)
        m = self.db.get_movie(self.movie)
        self.assertEqual((m["status"], m["tmdb_id"], m["title"], m["has_poster"], m["genres"]),
                         ("pending", None, None, False, []))
        self.assertEqual((m["watched"], m["favorite"], m["user_rating"]), (True, True, 4))
        self.assertEqual(len(self.db.all_collections()), 1)
        self.assertEqual(m["extra"], {})
        self.assertEqual(len(self.db.all_tags()), 1)
        self.assertEqual(self.db.tag_membership(), {self.movie: {self.tag_id}})

    def test_history_favorites_reviews_collections(self):
        self.db.restore(history=True, favorites=True, reviews=True, collections=True)
        m = self.db.get_movie(self.movie)
        self.assertEqual((m["watched"], m["favorite"], m["user_rating"], m["user_comment"]), (False, False, 0, ""))
        self.assertEqual((m["status"], m["title"]), ("matched", "A"))
        self.assertEqual(self.db.all_collections(), [])

    def test_everything_forgets_the_library(self):
        self.db.restore(everything=True)
        self.assertEqual((self.db.all_movies(), self.db.all_series(), self.db.all_collections()), ([], [], []))
        self.assertEqual(self.db.all_tags(), [])

    def test_tags_can_be_restored_independently(self):
        self.db.restore(tags=True)
        self.assertEqual(self.db.all_tags(), [])
        self.assertEqual(self.db.tag_membership(), {})
        self.assertEqual(len(self.db.all_movies()), 1)
        self.assertEqual(self.db.get_movie(self.movie)["title"], "A")


if __name__ == "__main__":
    unittest.main()
