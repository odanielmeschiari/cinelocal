"""Tests for "Surprise me". Run with: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.filters import surprise_pick


class SurpriseTests(unittest.TestCase):
    def test_prefers_what_is_not_watched(self):
        movies = [{"id": 1, "watched": True}, {"id": 2, "watched": False}, {"id": 3, "watched": True}]
        for _ in range(20):
            self.assertEqual(surprise_pick(movies)["id"], 2)

    def test_watched_ones_when_nothing_else(self):
        movies = [{"id": 1, "watched": True}, {"id": 2, "watched": True}]
        self.assertIn(surprise_pick(movies)["id"], (1, 2))

    def test_not_the_same_twice(self):
        movies = [{"id": 1, "watched": False}, {"id": 2, "watched": False}]
        for _ in range(20):
            self.assertEqual(surprise_pick(movies, avoid=1)["id"], 2)
        self.assertEqual(surprise_pick([movies[0]], avoid=1)["id"], 1)   # the only one: no choice

    def test_nothing_to_pick(self):
        self.assertIsNone(surprise_pick([]))


if __name__ == "__main__":
    unittest.main()
