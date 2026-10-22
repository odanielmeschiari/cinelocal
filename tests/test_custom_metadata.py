"""Tests for metadata edited by hand: it is stored apart and survives metadata updates.

Run with: python3 -m unittest discover -s tests"""
import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database


def _movie(name: str) -> dict:
    return dict(path=f"/m/{name}.mkv", file_name=f"{name}.mkv", size=1, clean_title=name,
                year_guess=2000, added_at=time.time())


class CustomDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "lib.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_movie_starts_without_custom_fields(self):
        (movie_id,) = self.db.add_movies([_movie("A")])
        self.assertEqual(self.db.get_movie(movie_id)["custom"], [])

    def test_custom_fields_are_saved_for_movies_and_series(self):
        (movie_id,) = self.db.add_movies([_movie("A")])
        self.db.save_metadata(movie_id, {"overview": "Mine", "custom": ["overview", "poster"]})
        movie = self.db.get_movie(movie_id)
        self.assertEqual((movie["overview"], movie["custom"]), ("Mine", ["overview", "poster"]))

        series_id = self.db.ensure_series("Show")
        self.db.save_metadata(series_id, {"tagline": "Hi", "custom": ["tagline"]}, table="series")
        self.assertEqual(self.db.get_series(series_id)["custom"], ["tagline"])

    def test_restoring_metadata_forgets_the_edits(self):
        (movie_id,) = self.db.add_movies([_movie("A")])
        self.db.save_metadata(movie_id, {"overview": "Mine", "custom": ["overview"]})
        self.db.restore(metadata=True)
        movie = self.db.get_movie(movie_id)
        self.assertEqual((movie["overview"], movie["custom"]), (None, []))


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "needs PySide6 (the image cache uses Qt)")
class UpdateKeepsEditsTests(unittest.TestCase):
    def test_update_does_not_overwrite_what_the_user_edited(self):
        from cinelocal import images
        from cinelocal.metadata_service import process_movie

        class Client:
            language = "en-US"

            def movie_details(self, tmdb_id, language=None):
                return {"title": "API title", "overview": "API overview", "tagline": "API tagline",
                        "release_date": "1999-05-01", "poster_path": "/p.jpg", "videos": {"results": []}}

            def download_image(self, size, path):
                raise AssertionError("the poster must not be downloaded")

        with tempfile.TemporaryDirectory() as tmp:
            images._ROOT = Path(tmp) / "images"
            db = Database(Path(tmp) / "lib.db")
            (movie_id,) = db.add_movies([_movie("A")])
            images.poster_file(movie_id).parent.mkdir(parents=True)
            images.poster_file(movie_id).write_bytes(b"mine")
            db.save_metadata(movie_id, {"overview": "Mine", "has_poster": True,
                                        "custom": ["overview", "poster"]})
            movie = db.get_movie(movie_id)
            self.assertEqual(process_movie(db, Client(), movie, tmdb_id=1), "matched")
            movie = db.get_movie(movie_id)
            self.assertEqual((movie["overview"], movie["title"], movie["tagline"]),
                             ("Mine", "API title", "API tagline"))
            self.assertTrue(movie["has_poster"])
            self.assertEqual(images.poster_file(movie_id).read_bytes(), b"mine")
            db.close()


if __name__ == "__main__":
    unittest.main()
