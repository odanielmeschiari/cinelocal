"""Testes do provedor OMDb e da Watchlist (sem interface). Rode com: python3 -m unittest discover -s tests"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.filters import matches, sidebar_counts
from cinelocal.omdb import OMDB_OFFSET, OMDbClient
from cinelocal.parsing import choose_best, parse_details, parse_search_result
from cinelocal.providers import make_client, same_provider
from cinelocal.tmdb import TMDBClient

MATRIX = {"Response": "True", "Title": "The Matrix", "Year": "1999", "Released": "31 Mar 1999",
          "Runtime": "136 min", "Genre": "Action, Sci-Fi", "Director": "Lana Wachowski, Lilly Wachowski",
          "Actors": "Keanu Reeves, Carrie-Anne Moss", "Plot": "Um hacker descobre a verdade.",
          "Poster": "https://example.com/p.jpg", "imdbRating": "8.7", "imdbVotes": "2,100,000"}


class OMDbTests(unittest.TestCase):
    def client(self, payload):
        client = OMDbClient("key")
        client._get_json = lambda **params: payload
        return client

    def test_details_use_the_tmdb_shape(self):
        fields = parse_details(self.client(MATRIX).movie_details(OMDB_OFFSET + 133093))
        self.assertEqual((fields["title"], fields["year"], fields["runtime"]), ("The Matrix", 1999, 136))
        self.assertEqual((fields["rating"], fields["votes"]), (8.7, 2100000))
        self.assertEqual(fields["genres"], ["Action", "Sci-Fi"])
        self.assertEqual(fields["director"], "Lana Wachowski, Lilly Wachowski")
        self.assertEqual(fields["cast"][0], {"name": "Keanu Reeves", "character": ""})

    def test_missing_values_become_none(self):
        raw = self.client({"Response": "True", "Title": "X", "Year": "2001", "Runtime": "N/A",
                           "imdbRating": "N/A", "imdbVotes": "N/A", "Poster": "N/A"}).movie_details(OMDB_OFFSET + 1)
        self.assertEqual((raw["release_date"], raw["runtime"], raw["vote_average"], raw["poster_path"]),
                         ("2001", None, None, None))

    def test_search_results_work_with_choose_best(self):
        payload = {"Search": [{"Title": "The Matrix", "Year": "1999", "imdbID": "tt0133093"},
                              {"Title": "The Matrix Reloaded", "Year": "2003", "imdbID": "tt0234215"}]}
        results = [parse_search_result(r) for r in self.client(payload).search_movie("The Matrix", 1999)]
        self.assertEqual(results[0]["id"], OMDB_OFFSET + 133093)
        self.assertEqual(choose_best(results, "The Matrix", 1999)["id"], OMDB_OFFSET + 133093)

    def test_provider_of_stored_ids(self):
        self.assertTrue(same_provider("tmdb", 603))
        self.assertFalse(same_provider("tmdb", OMDB_OFFSET + 133093))
        self.assertTrue(same_provider("omdb", OMDB_OFFSET + 133093))
        self.assertFalse(same_provider("omdb", 603))
        self.assertFalse(same_provider("tmdb", None))
        self.assertIsInstance(make_client("omdb", "k", "pt-BR"), OMDbClient)
        self.assertIsInstance(make_client("tmdb", "k", "pt-BR"), TMDBClient)


class WatchlistTests(unittest.TestCase):
    def test_old_database_is_migrated_and_flag_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.db"
            old = sqlite3.connect(path)   # banco da versão anterior: sem a coluna watchlist
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
            Database(path).close()   # abrir de novo não pode falhar (coluna já existe)


if __name__ == "__main__":
    unittest.main()
