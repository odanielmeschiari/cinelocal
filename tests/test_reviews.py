"""Tests for the user's rating/comment, the filters built on it and the audio/subtitle track choice.

Run with: python3 -m unittest discover -s tests"""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.filters import filter_movies, sidebar_counts, sort_movies
from cinelocal.movie_fields import decorate
from cinelocal.tracks import choose_track, is_forced, matches_language

OLD_SCHEMA = """
CREATE TABLE movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE, file_name TEXT NOT NULL,
    size INTEGER DEFAULT 0, clean_title TEXT NOT NULL, year_guess INTEGER, tmdb_id INTEGER, title TEXT,
    original_title TEXT, year INTEGER, release_date TEXT, overview TEXT, tagline TEXT, runtime INTEGER,
    rating REAL, votes INTEGER, genres_json TEXT DEFAULT '[]', director TEXT, cast_json TEXT DEFAULT '[]',
    trailer_key TEXT, has_poster INTEGER DEFAULT 0, has_backdrop INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending', watched INTEGER DEFAULT 0, favorite INTEGER DEFAULT 0,
    added_at REAL NOT NULL, updated_at REAL NOT NULL);
INSERT INTO movies (path, file_name, clean_title, added_at, updated_at) VALUES ('p', 'f', 'Old', 1, 1);
"""


def _movie(name: str) -> dict:
    return dict(path=f"/m/{name}.mkv", file_name=f"{name}.mkv", size=1, clean_title=name,
                year_guess=2000, added_at=time.time())


class ReviewDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lib.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_movie_is_unrated(self):
        db = Database(self.path)
        (movie_id,) = db.add_movies([_movie("A")])
        movie = db.get_movie(movie_id)
        self.assertEqual((movie["user_rating"], movie["user_comment"]), (0, ""))
        db.close()

    def test_review_round_trip(self):
        db = Database(self.path)
        (movie_id,) = db.add_movies([_movie("A")])
        db.set_review(movie_id, 4, "Ótimo filme")
        movie = db.get_movie(movie_id)
        self.assertEqual((movie["user_rating"], movie["user_comment"]), (4, "Ótimo filme"))
        db.close()

    def test_metadata_refresh_keeps_review(self):
        db = Database(self.path)
        (movie_id,) = db.add_movies([_movie("A")])
        db.set_review(movie_id, 5, "ótimo")
        db.save_metadata(movie_id, {"title": "A", "rating": 7.5, "status": "matched"})
        self.assertEqual(db.get_movie(movie_id)["user_rating"], 5)
        db.close()

    def test_database_from_an_older_version_is_migrated(self):
        conn = sqlite3.connect(self.path)
        conn.executescript(OLD_SCHEMA)
        conn.commit()
        conn.close()
        db = Database(self.path)
        movie = db.get_movie(1)
        self.assertEqual((movie["user_rating"], movie["user_comment"]), (0, ""))
        db.set_review(1, 3, "ok")
        self.assertEqual(db.get_movie(1)["user_rating"], 3)
        db.close()


class RatingFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Database(Path(self.tmp.name) / "lib.db")
        ids = db.add_movies([_movie(n) for n in "ABCD"])
        for movie_id, stars in zip(ids, (3, 5, 0, 5)):
            db.set_review(movie_id, stars, "")
        self.movies = [decorate(m) for m in db.all_movies()]
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def titles(self, movies):
        return [m["display_title"] for m in movies]

    def test_sort_by_my_rating(self):
        self.assertEqual(self.titles(sort_movies(self.movies, "myrating_desc")), ["B", "D", "A", "C"])
        self.assertEqual(self.titles(sort_movies(self.movies, "myrating_asc")), ["A", "B", "D", "C"])

    def test_filter_by_stars(self):
        self.assertEqual(self.titles(filter_movies(self.movies, ("stars", 5), {})), ["B", "D"])
        self.assertEqual(self.titles(filter_movies(self.movies, ("stars", 1), {})), [])

    def test_sidebar_counts_stars(self):
        self.assertEqual(sidebar_counts(self.movies)["stars"], [(5, 2), (3, 1)])

    def test_series_entries_without_rating_are_fine(self):
        series = dict(self.movies[0])
        series.pop("user_rating")
        self.assertFalse(filter_movies([series], ("stars", 3), {}))
        self.assertEqual(len(sort_movies([series], "myrating_desc")), 1)
        self.assertEqual(sidebar_counts([series])["stars"], [])


class TrackChoiceTests(unittest.TestCase):
    AUDIO = [(-1, b"Disable"), (1, b"Track 1 - [Japanese]"), (2, b"Track 2 - [Portuguese]")]
    SUBS = [(-1, b"Disable"), (3, b"Track 1 - [English]"), (4, b"Track 2 - [Portuguese] - Forced"),
            (5, b"Track 3 - [Portuguese]")]

    def test_language_names(self):
        self.assertTrue(matches_language("pt", "Track 2 - [Portuguese]"))
        self.assertTrue(matches_language("ja", "Track 1 - [日本語]"))
        self.assertFalse(matches_language("en", "Track 1 - [Portuguese]"))
        self.assertFalse(matches_language("pt", "Track 1 - [Japanese]"))

    def test_forced_names(self):
        self.assertTrue(is_forced("Track 2 - [Portuguese] - Forced"))
        self.assertTrue(is_forced("Forçada"))
        self.assertFalse(is_forced("Track 3 - [Portuguese]"))

    def test_audio_language(self):
        self.assertEqual(choose_track(self.AUDIO, language="pt"), (2, True))
        self.assertEqual(choose_track(self.AUDIO, language="ja"), (1, True))

    def test_missing_language_keeps_looking(self):
        self.assertEqual(choose_track(self.AUDIO, language="de"), (None, False))

    def test_tracks_not_listed_yet(self):
        self.assertEqual(choose_track([], language="pt"), (None, False))
        self.assertEqual(choose_track([(-1, b"Disable")], language="off"), (None, False))

    def test_no_preference_changes_nothing(self):
        self.assertEqual(choose_track(self.AUDIO), (None, True))

    def test_subtitles_off(self):
        self.assertEqual(choose_track(self.SUBS, language="off"), (-1, True))

    def test_subtitle_language_prefers_full_track_over_forced(self):
        self.assertEqual(choose_track(self.SUBS, language="pt"), (5, True))

    def test_forced_only(self):
        self.assertEqual(choose_track(self.SUBS, language="forced"), (4, True))
        no_forced = [self.SUBS[0], self.SUBS[1]]
        self.assertEqual(choose_track(no_forced, language="forced"), (-1, True))

    def test_forced_only_prefers_audio_language(self):
        subs = self.SUBS + [(6, b"Track 4 - [English] - Forced")]
        self.assertEqual(choose_track(subs, language="forced", prefer_language="en"), (6, True))
        self.assertEqual(choose_track(subs, language="forced", prefer_language="pt"), (4, True))

    def test_saved_choice_wins_over_language(self):
        self.assertEqual(choose_track(self.AUDIO, saved="Track 1 - [Japanese]", language="pt"), (1, True))
        self.assertEqual(choose_track(self.SUBS, saved="Disable", language="pt"), (-1, True))

    def test_saved_choice_that_no_longer_exists_falls_back(self):
        self.assertEqual(choose_track(self.AUDIO, saved="Gone", language="pt"), (2, True))
        self.assertEqual(choose_track(self.AUDIO, saved="Gone"), (None, True))


if __name__ == "__main__":
    unittest.main()
