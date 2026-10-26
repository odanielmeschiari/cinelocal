"""Tests for "For you" (recommend.py) and its sorting. Run with: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.filters import sort_movies
from cinelocal.recommend import MIN_MATCH, Taste, match_scores, recommend, signal


def movie(id, genres, year=2000, rating=7.5, votes=5000, director="", cast=(), franchise=None,
          language="English", **flags):
    return {"id": id, "status": "matched", "genres": list(genres), "year": year, "year_guess": None,
            "rating": rating, "votes": votes, "director": director, "cast": [{"name": c} for c in cast],
            "franchise": franchise, "extra": {"original_language_name": language}, "watched": False,
            "favorite": False, "watchlist": False, "user_rating": 0, "sort_title": f"m{id:03d}", **flags}


class SignalTests(unittest.TestCase):
    def test_stars_favorite_and_clamping(self):
        self.assertEqual(signal(movie(1, ["Drama"])), 0)
        self.assertEqual(signal(movie(1, ["Drama"], user_rating=5)), 1.0)
        self.assertLess(signal(movie(1, ["Drama"], user_rating=1.5)), 0)   # low stars are a negative signal
        self.assertGreater(signal(movie(1, ["Drama"], user_rating=3.5)), signal(movie(1, ["Drama"], user_rating=3)))
        self.assertEqual(signal(movie(1, ["Drama"], user_rating=5, favorite=True)), 1.0)
        self.assertGreater(signal(movie(1, ["Drama"], favorite=True)), signal(movie(1, ["Drama"], watched=True)))


class RecommendTests(unittest.TestCase):
    def setUp(self):
        self.movies = [
            movie(1, ["Science Fiction", "Thriller"], 2010, favorite=True, watched=True, director="Nolan"),
            movie(2, ["Science Fiction", "Action"], 2014, user_rating=5, watched=True),
            movie(3, ["Romance", "Drama"], 2005, user_rating=1, watched=True),
            movie(4, ["Science Fiction", "Thriller"], 2012),              # looks like the favorites
            movie(5, ["Science Fiction", "Thriller"], 2011, director="Nolan"),   # ...and has the favorite director
            movie(6, ["Romance", "Drama"], 2005),                          # looks like the 1-star movie
            movie(7, ["Documentary"], 1970, language="French", rating=5.0, votes=40),
            movie(8, ["Science Fiction"], 2013, watched=True),             # already seen: never recommended
            {**movie(9, ["Science Fiction"]), "status": "pending"},        # no metadata yet
        ]

    def test_no_taste_no_recommendations(self):
        blank = [movie(i, ["Drama"]) for i in range(3)]
        self.assertEqual(match_scores(blank), {})
        self.assertEqual(recommend(blank, {}), [])

    def test_ranking(self):
        scores = match_scores(self.movies)
        self.assertGreater(scores[5], scores[4])      # same genres, plus a director the user loves
        self.assertGreater(scores[4], scores[6])
        self.assertGreater(scores[4], scores[7])
        self.assertLess(scores[6], MIN_MATCH)         # resembles what the user rated 1 star
        self.assertNotIn(9, scores)
        for value in scores.values():
            self.assertTrue(0 <= value <= 1)
        self.assertEqual([m["id"] for m in recommend(self.movies, scores)], [5, 4])

    def test_exact_copy_of_the_taste_is_near_100(self):
        library = [movie(1, ["Horror"], 1990, user_rating=5, director="D", cast=("A",), franchise="F"),
                   movie(2, ["Horror"], 1990, director="D", cast=("A",), franchise="F")]
        self.assertGreater(match_scores(library)[2], 0.95)

    def test_series_genres_and_half_star_ratings(self):
        library = [movie(1, ["Science Fiction"], user_rating=4.5),
                   movie(2, ["Sci-Fi & Fantasy"], kind="series")]
        self.assertGreater(match_scores(library)[2], MIN_MATCH)
        self.assertTrue(Taste(library))

    def test_best_match_sort(self):
        scores = match_scores(self.movies)
        ids = [m["id"] for m in sort_movies([m for m in self.movies if m["id"] in (4, 5, 7)], "match_desc", scores)]
        self.assertEqual(ids, [5, 4, 7])
        self.assertEqual([m["id"] for m in sort_movies(self.movies[3:5], "match_desc")], [4, 5])   # no scores: by title


if __name__ == "__main__":
    unittest.main()
