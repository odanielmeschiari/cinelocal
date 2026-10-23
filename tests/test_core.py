"""Tests for the non-GUI parts. Run with: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.filters import filter_movies, sort_movies
from cinelocal.library import sync_library
from cinelocal.parsing import choose_best, parse_details
from cinelocal.scanner import clean_filename, search_attempts
from cinelocal.utils import comparable_title, normalize_text


class CleanFilenameTests(unittest.TestCase):
    def check(self, name, title, year):
        self.assertEqual(clean_filename(name), (title, year), name)

    def test_release_names(self):
        self.check("The.Matrix.1999.1080p.BluRay.x264-YTS.mkv", "The Matrix", 1999)
        self.check("Inception (2010) [1080p] [YTS].mp4", "Inception", 2010)
        self.check("Parasite.2019.2160p.WEB-DL.DDP5.1.HEVC.mkv", "Parasite", 2019)

    def test_title_only(self):
        self.check("O Poderoso Chefão.mkv", "O Poderoso Chefão", None)
        self.check("Matrix 1999.mkv", "Matrix", 1999)

    def test_numbers_in_titles(self):
        self.check("1917.mkv", "1917", None)
        self.check("2001 A Space Odyssey (1968).mkv", "2001 A Space Odyssey", 1968)
        self.check("Blade Runner 2049.mkv", "Blade Runner 2049", None)

    def test_year_like_title_gets_extra_attempt(self):
        title, year = clean_filename("Wonder Woman 1984.mkv")
        self.assertEqual((title, year), ("Wonder Woman", 1984))
        self.assertIn(("Wonder Woman 1984", None), search_attempts(title, year))


class MatchingTests(unittest.TestCase):
    def r(self, id, title, year, pop=1, votes=1, original=None):
        return {"id": id, "title": title, "original_title": original or title, "year": year,
                "overview": "", "poster_path": None, "popularity": pop, "vote_count": votes}

    def test_articles_ignored(self):
        self.assertEqual(comparable_title("The Matrix"), comparable_title("matrix"))
        self.assertEqual(normalize_text("Ação & Aventura!"), "acao aventura")

    def test_exact_with_year(self):
        results = [self.r(1, "Dune", 1984), self.r(2, "Dune", 2021)]
        self.assertEqual(choose_best(results, "Dune", 2021)["id"], 2)

    def test_remakes_without_year_need_review(self):
        results = [self.r(1, "Dune", 1984, votes=3000), self.r(2, "Dune", 2021, votes=11000)]
        self.assertIsNone(choose_best(results, "Dune", None))

    def test_clear_winner_without_year(self):
        results = [self.r(1, "Heat", 1995, votes=9000), self.r(2, "Heat", 1986, votes=100)]
        self.assertEqual(choose_best(results, "Heat", None)["id"], 1)

    def test_unrelated_results_need_review(self):
        results = [self.r(1, "Foo Bar", 2000), self.r(2, "Foo Baz", 2001)]
        self.assertIsNone(choose_best(results, "Foo", None))

    def test_parse_details_uses_english_fallback(self):
        pt = {"title": "Filme", "overview": "", "tagline": "", "release_date": "2020-05-01",
              "genres": [{"name": "Ação"}], "credits": {"crew": [{"job": "Director", "name": "Ana"}], "cast": []},
              "videos": {"results": []}}
        en = {"overview": "Plot", "tagline": "Tag",
              "videos": {"results": [{"site": "YouTube", "key": "abc", "type": "Trailer"}]}}
        out = parse_details(pt, en)
        self.assertEqual((out["overview"], out["tagline"], out["trailer_key"]), ("Plot", "Tag", "abc"))
        self.assertEqual((out["year"], out["director"], out["genres"]), (2020, "Ana", ["Ação"]))


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "filmes"
        self.root.mkdir()
        self.db = Database(Path(self.tmp.name) / "lib.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def touch(self, rel, size=10):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        return path

    def test_sync_add_remove_and_move(self):
        a = self.touch("Matrix 1999.mkv", 11)
        self.touch("sub/Alien.mp4", 22)
        self.touch("notas.txt")
        added, removed = sync_library(self.db, str(self.root))
        self.assertEqual((len(added), len(removed)), (2, 0))

        movie_id = next(m["id"] for m in self.db.all_movies() if m["clean_title"] == "Matrix")
        self.db.set_flag_many([movie_id], "favorite", True)
        cid = self.db.create_collection("Clássicos")
        self.db.set_membership(cid, [movie_id], True)

        # moving the file preserves flags and collections
        new_path = self.root / "novo" / a.name
        new_path.parent.mkdir()
        a.rename(new_path)
        added, removed = sync_library(self.db, str(self.root))
        self.assertEqual((added, removed), ([], []))
        moved = self.db.get_movie(movie_id)
        self.assertTrue(moved["favorite"])
        self.assertEqual(moved["path"], str(new_path))
        self.assertIn(movie_id, self.db.membership()[cid])

        # a deleted file disappears, along with its collection memberships
        new_path.unlink()
        _, removed = sync_library(self.db, str(self.root))
        self.assertEqual(removed, [movie_id])
        self.assertEqual(self.db.membership().get(cid, set()), set())

    def test_missing_root_does_not_wipe_library(self):
        self.touch("A.mkv")
        sync_library(self.db, str(self.root))
        with self.assertRaises(FileNotFoundError):
            sync_library(self.db, str(self.root / "desmontada"))
        self.assertEqual(len(self.db.all_movies()), 1)

    def test_duplicate_collection_name(self):
        self.db.create_collection("Terror")
        with self.assertRaises(ValueError):
            self.db.create_collection("terror")

    def test_tags_and_additional_metadata_persist(self):
        self.touch("A.mkv")
        sync_library(self.db, str(self.root))
        (movie_id,) = [movie["id"] for movie in self.db.all_movies()]
        tag_id = self.db.create_tag("Cult")
        self.db.set_movie_tag(movie_id, tag_id, True)
        self.db.set_tag_color(tag_id, "#123456")
        extra = {"budget": 1234, "production_countries": ["Brazil"]}
        self.db.save_metadata(movie_id, {"extra": extra})

        self.assertEqual(self.db.get_movie(movie_id)["extra"], extra)
        self.assertEqual(self.db.all_tags(), [{"id": tag_id, "name": "Cult", "color": "#123456"}])
        self.assertEqual(self.db.tag_membership(), {movie_id: {tag_id}})
        with self.assertRaises(ValueError):
            self.db.create_tag("cult")

    def test_filter_and_sort(self):
        for name in ("B 2001.mkv", "A 1999.mkv", "C.mkv"):
            self.touch(name)
        sync_library(self.db, str(self.root))
        from cinelocal.movie_fields import decorate
        movies = [decorate(m) for m in self.db.all_movies()]
        titles = lambda ms: [m["display_title"] for m in ms]
        self.assertEqual(titles(sort_movies(movies, "title_asc")), ["A", "B", "C"])
        self.assertEqual(titles(sort_movies(movies, "year_desc")), ["B", "A", "C"])
        self.assertEqual(titles(filter_movies(movies, ("all", None), {}, "b")), ["B"])


if __name__ == "__main__":
    unittest.main()
