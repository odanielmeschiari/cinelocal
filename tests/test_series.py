"""Testes de séries: reconhecimento de episódios, agrupamento no banco e dados da API (sem Qt)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.library import sync_library
from cinelocal.parsing import parse_details, parse_season
from cinelocal.scanner import parse_episode
from cinelocal.tmdb import _tv_as_movie

ROOT = "/media/filmes"


class ParseEpisodeTests(unittest.TestCase):
    def check(self, rel, expected):
        self.assertEqual(parse_episode(f"{ROOT}/{rel}", ROOT), expected, rel)

    def test_common_patterns(self):
        self.check("Breaking.Bad.S01E02.720p.BluRay.x264.mkv", ("Breaking Bad", None, 1, 2))
        self.check("Friends - 3x07 - The One.avi", ("Friends", None, 3, 7))
        self.check("Série X Temporada 1 Episódio 3.mp4", ("Série X", None, 1, 3))

    def test_folders_give_title_and_season(self):
        self.check("Dark/S01E01 - Segredos.mkv", ("Dark", None, 1, 1))
        self.check("Show (2019)/Temporada 2/E05.mkv", ("Show", 2019, 2, 5))
        self.check("Show (2019)/Season 2/05 - Título.mkv", ("Show", 2019, 2, 5))

    def test_movies_are_not_episodes(self):
        for name in ("The.Matrix.1999.1080p.mkv", "Movie.1920x1080.mkv", "1917.mkv", "S01E01.mkv"):
            self.assertIsNone(parse_episode(f"{ROOT}/{name}", ROOT), name)


class SeriesLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "filmes"
        self.root.mkdir()
        self.db = Database(Path(self.tmp.name) / "lib.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def touch(self, rel):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 10)
        return path

    def test_episodes_are_grouped_in_one_series(self):
        self.touch("Breaking.Bad.S01E01.mkv")
        self.touch("Breaking Bad/Season 2/Breaking Bad S02E03.mkv")
        self.touch("Matrix 1999.mkv")
        sync_library(self.db, str(self.root))
        series = self.db.all_series()
        self.assertEqual([s["clean_title"] for s in series], ["Breaking Bad"])
        episodes = self.db.episodes_of(series[0]["id"])
        self.assertEqual([(e["season"], e["episode"]) for e in episodes], [(1, 1), (2, 3)])
        movies = [m for m in self.db.all_movies() if m["kind"] == "movie"]
        self.assertEqual([m["clean_title"] for m in movies], ["Matrix"])

    def test_old_movie_row_becomes_episode_and_empty_series_is_removed(self):
        path = self.touch("Dark.S01E01.mkv")
        self.db.add_movies([{"path": str(path), "file_name": path.name, "size": 10,
                             "clean_title": "Dark S01E01", "year_guess": None, "added_at": 1.0}])
        self.assertEqual(self.db.all_series(), [])
        sync_library(self.db, str(self.root))
        self.assertEqual(self.db.all_movies()[0]["kind"], "episode")
        self.assertEqual(len(self.db.all_series()), 1)
        path.unlink()
        sync_library(self.db, str(self.root))
        self.assertEqual(self.db.all_series(), [])

    def test_save_episode_and_series_metadata(self):
        self.touch("Dark.S01E01.mkv")
        sync_library(self.db, str(self.root))
        series_id = self.db.all_series()[0]["id"]
        self.db.save_metadata(series_id, {"title": "Dark", "genres": ["Drama"], "status": "matched"},
                              table="series")
        episode = self.db.episodes_of(series_id)[0]
        self.assertEqual(episode["status"], "pending")
        self.db.save_episode(episode["id"], {"ep_title": "Segredos", "ep_rating": 8.5})
        episode = self.db.episodes_of(series_id)[0]
        self.assertEqual((episode["ep_title"], episode["status"]), ("Segredos", "matched"))
        self.assertEqual(self.db.get_series(series_id)["genres"], ["Drama"])
        self.db.set_series_flag([series_id], "favorite", True)
        self.assertTrue(self.db.get_series(series_id)["favorite"])


class ApiShapeTests(unittest.TestCase):
    def test_tv_looks_like_a_movie(self):
        raw = {"name": "Dark", "original_name": "Dark", "first_air_date": "2017-12-01",
               "episode_run_time": [60], "overview": "x", "created_by": [{"name": "Baran bo Odar"}],
               "genres": [{"name": "Drama"}], "credits": {"cast": [{"name": "A", "character": "B"}]}}
        out = parse_details(_tv_as_movie(raw))
        self.assertEqual((out["title"], out["year"], out["runtime"]), ("Dark", 2017, 60))
        self.assertEqual(out["director"], "Baran bo Odar")

    def test_parse_season(self):
        raw = {"episodes": [{"episode_number": 1, "name": "Segredos", "overview": "",
                             "air_date": "2017-12-01", "runtime": 52, "vote_average": 8.4}]}
        self.assertEqual(parse_season(raw)[1], {"ep_title": "Segredos", "ep_overview": None,
                                                "ep_air_date": "2017-12-01", "ep_runtime": 52,
                                                "ep_rating": 8.4})


if __name__ == "__main__":
    unittest.main()
