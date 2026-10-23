"""Tests for the advanced search filters and age ratings. Run with: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.filters import advanced_options, filter_movies, matches_advanced, sort_movies
from cinelocal.parsing import parse_details
from cinelocal.tmdb import _certification


def movie(id, **kw):
    base = {"id": id, "kind": "movie", "genres": [], "cast": [], "director": None, "year": None,
            "year_guess": None, "rating": None, "votes": None, "runtime": None, "certification": None,
            "watched": False, "favorite": False, "watchlist": False, "user_rating": 0,
            "added_at": 0, "sort_title": str(id), "search_text": "", "extra": {}, "tags": []}
    base.update(kw)
    return base


class AdvancedFilterTests(unittest.TestCase):
    def setUp(self):
        self.a = movie(1, genres=["Drama", "Crime"], director="Ana, Beto", year=1999, rating=8.1, votes=5000,
                       runtime=120, certification="R", cast=[{"name": "Zed", "character": ""}], favorite=True)
        self.b = movie(2, genres=["Drama"], director="Carl", year=2010, rating=6.0, votes=100, runtime=90,
                       certification="PG", watched=True, user_rating=4)
        self.s = movie(-3, kind="series", genres=["Crime"], year=2015, rating=9.0, votes=900)
        self.all = [self.a, self.b, self.s]
        self.members = {7: {2}}

    def ids(self, adv):
        return [m["id"] for m in filter_movies(self.all, ("all", None), self.members, advanced=adv)]

    def test_empty_matches_everything(self):
        self.assertEqual(self.ids({}), [1, 2, -3])

    def test_kind_genres_and_year(self):
        self.assertEqual(self.ids({"kind": "series"}), [-3])
        self.assertEqual(self.ids({"genres": ["Drama", "Crime"]}), [1, 2, -3])
        self.assertEqual(self.ids({"genres": ["Drama", "Crime"], "genres_all": True}), [1])
        self.assertEqual(self.ids({"year_min": 2000, "year_max": 2012}), [2])
        self.assertEqual(self.ids({"year_min": 1999, "year_max": 1999}), [1])

    def test_ranges_exclude_unknown_values(self):
        self.assertEqual(self.ids({"rating_min": 7}), [1, -3])
        self.assertEqual(self.ids({"votes_max": 1000}), [2, -3])
        self.assertEqual(self.ids({"runtime_min": 100}), [1, -3])   # a series is not held to the movie runtime
        self.assertEqual(self.ids({"runtime_max": 60}), [-3])
        self.assertEqual(self.ids({"kind": "series", "runtime_max": 30}), [-3])

    def test_people_age_and_library(self):
        self.assertEqual(self.ids({"directors": ["Beto"]}), [1])
        self.assertEqual(self.ids({"cast": ["Zed"]}), [1])
        self.assertEqual(self.ids({"certifications": ["PG"]}), [2])
        self.assertEqual(self.ids({"watched": False, "favorite": True}), [1])
        self.assertEqual(self.ids({"collections": [7]}), [2])
        self.assertEqual(self.ids({"stars": [0]}), [1, -3])
        self.assertEqual(self.ids({"stars": [4]}), [2])

    def test_tag_sidebar_filter_matches_tagged_movies(self):
        self.a["tags"] = [{"id": 4, "name": "Favorites", "color": "#e57373"}]
        self.assertEqual(self.ids({"tags": [4]}), [1])
        self.assertEqual(
            [m["id"] for m in filter_movies(self.all, ("tag", 4), self.members)],
            [1],
        )

    def test_added_days(self):
        self.a["added_at"] = 1_000_000
        self.assertTrue(matches_advanced(self.a, {"added_days": 1}, {}, now=1_000_000 + 3600))
        self.assertFalse(matches_advanced(self.a, {"added_days": 1}, {}, now=1_000_000 + 3 * 86400))

    def test_options(self):
        opts = advanced_options(self.all)
        self.assertEqual(opts["genres"], [("Crime", 2), ("Drama", 2)])
        self.assertEqual(dict(opts["directors"]), {"Ana": 1, "Beto": 1, "Carl": 1})
        self.assertEqual(opts["years"], (1999, 2015))

    def test_countries_languages_tags_and_popularity_filters(self):
        self.a["extra"] = {"production_countries": ["Brazil", "United States"],
                           "spoken_languages": ["Portuguese", "English"],
                           "original_language_name": "Portuguese", "popularity": 8.5}
        self.a["tags"] = [{"id": 11, "name": "Favorites", "color": "#e57373"}]
        self.b["extra"] = {"production_countries": ["France"], "spoken_languages": ["French"],
                           "original_language_name": "French", "popularity": 2.1}
        self.b["tags"] = [{"id": 12, "name": "Watch later", "color": "#64b5f6"}]
        self.assertEqual(self.ids({"countries": ["Brazil"]}), [1])
        self.assertEqual(self.ids({"languages": ["French"]}), [2])
        self.assertEqual(self.ids({"tags": [11]}), [1])
        self.assertEqual([m["id"] for m in sort_movies(self.all, "popularity_desc")], [1, 2, -3])
        self.assertEqual([m["id"] for m in sort_movies(self.all, "runtime_asc")], [2, 1, -3])
        options = advanced_options(self.all)
        self.assertEqual(options["countries"], [("Brazil", 1), ("France", 1), ("United States", 1)])
        self.assertEqual(options["languages"], [("English", 1), ("French", 1), ("Portuguese", 1)])
        self.assertEqual(options["tags"], [(11, "Favorites  (1)"), (12, "Watch later  (1)")])


class CertificationTests(unittest.TestCase):
    def test_movie_release_dates(self):
        raw = {"release_dates": {"results": [
            {"iso_3166_1": "US", "release_dates": [{"certification": ""}, {"certification": "PG-13"}]},
            {"iso_3166_1": "BR", "release_dates": [{"certification": "14"}]}]}}
        self.assertEqual(_certification(raw, "BR"), "14")
        self.assertEqual(_certification(raw, "FR"), "PG-13")   # falls back to the US

    def test_tv_content_ratings_and_missing(self):
        raw = {"content_ratings": {"results": [{"iso_3166_1": "US", "rating": "TV-MA"}]}}
        self.assertEqual(_certification(raw, "US"), "TV-MA")
        self.assertIsNone(_certification({}, "US"))

    def test_parse_details_keeps_certification(self):
        out = parse_details({"title": "x", "certification": "R"})
        self.assertEqual(out["certification"], "R")

    def test_parse_details_extracts_additional_information(self):
        out = parse_details({
            "title": "x", "budget": 1200000, "revenue": 2400000, "popularity": 9.3,
            "production_countries": [{"name": "Brazil"}],
            "production_companies": [{"name": "Studio"}],
            "spoken_languages": [{"iso_639_1": "pt", "english_name": "Portuguese", "name": "Português"}],
            "original_language": "pt",
            "belongs_to_collection": {"name": "X Collection"},
        })
        self.assertEqual(out["franchise"], "X Collection")
        self.assertEqual(out["extra"]["production_countries"], ["Brazil"])
        self.assertEqual(out["extra"]["production_companies"], ["Studio"])
        self.assertEqual(out["extra"]["original_language_name"], "Portuguese")
        self.assertEqual(out["extra"]["budget"], 1200000)


if __name__ == "__main__":
    unittest.main()
