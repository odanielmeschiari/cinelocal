import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.filters import GROUP_ID_BASE, automatic_collections, group_collections, group_of


def movie(movie_id, title, year):
    return {"id": movie_id, "sort_title": title, "year": year, "genres": ["Sci-Fi"], "display_title": title}


class GroupCollectionsTests(unittest.TestCase):
    def test_grouping(self):
        movies = [movie(1, "A New Hope", 1977), movie(2, "Alien", 1979), movie(3, "Empire", 1980)]
        result = group_collections(movies, {7: {1, 3}}, [7], lambda cid: "Star Wars")
        self.assertEqual([m["display_title"] for m in result], ["Star Wars", "Alien"])
        self.assertEqual(result[0]["poster_id"], 1)
        self.assertEqual(result[0]["genres"], ["2 movies"])
        self.assertEqual(group_of(result[0]["id"]), 7)
        self.assertIsNone(group_of(5))
        self.assertIsNone(group_of(-3))   # a series
        self.assertEqual(result[0]["id"], -(GROUP_ID_BASE + 7))

    def test_own_cover(self):
        movies = [movie(1, "A", 2000), movie(2, "B", 2001)]
        result = group_collections(movies, {7: {1, 2}}, [7], str, lambda cid: ("/x/7.jpg", 5.0))
        self.assertEqual((result[0]["cover_file"], result[0]["updated_at"], result[0]["has_poster"]),
                         ("/x/7.jpg", 5.0, True))
        self.assertNotIn("cover_file", group_collections(movies, {7: {1, 2}}, [7], str, lambda cid: None)[0])

    def test_automatic_collections(self):
        movies = [{**movie(1, "A", 2000), "franchise": "Star Wars Collection"}, movie(2, "B", 2001)]
        collections = [{"id": 1, "name": "star wars collection"}, {"id": 2, "name": "Mine"}]
        self.assertEqual(automatic_collections(movies, collections), [1])

    def test_not_grouped(self):
        movies = [movie(1, "A", 2000)]
        self.assertEqual(group_collections(movies, {7: {1}}, [], str), movies)


if __name__ == "__main__":
    unittest.main()
