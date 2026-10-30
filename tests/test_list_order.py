"""Tests for the manual order of the lists. Run with: python3 -m unittest discover -s tests"""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.db import Database
from cinelocal.filters import SORT_OPTIONS, sort_by_order
from cinelocal.service import LibraryService


def add(db, n):
    return db.add_movies([dict(path=f"/m/{i}.mkv", file_name=f"{i}.mkv", size=1, clean_title=f"M{i}",
                               year_guess=2000, added_at=time.time()) for i in range(n)])


class ListOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lib.db"
        self.db = Database(self.path)
        self.a, self.b, self.c, self.d = add(self.db, 4)
        self.list = self.db.create_collection("First movies I watched", "list")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_starts_in_the_order_of_inclusion(self):
        self.db.set_membership(self.list, [self.c, self.a], True)
        self.db.set_membership(self.list, [self.d], True)
        self.assertEqual(self.db.collection_order(self.list), [self.c, self.a, self.d])

    def test_order_can_be_set_and_new_movies_go_last(self):
        self.db.set_membership(self.list, [self.a, self.b, self.c], True)
        self.db.set_collection_order(self.list, [self.c, self.a, self.b])
        self.db.set_membership(self.list, [self.d], True)
        self.assertEqual(self.db.collection_order(self.list), [self.c, self.a, self.b, self.d])
        self.db.set_membership(self.list, [self.a], False)
        self.assertEqual(self.db.collection_order(self.list), [self.c, self.b, self.d])

    def test_move_in_collection(self):
        service = LibraryService(self.db, None)
        self.db.set_membership(self.list, [self.a, self.b, self.c, self.d], True)
        service.move_in_collection(self.list, self.a, self.c)   # down: takes the place of the target
        self.assertEqual(service.collection_order(self.list), [self.b, self.c, self.a, self.d])
        service.move_in_collection(self.list, self.d, self.b)   # up
        self.assertEqual(service.collection_order(self.list), [self.d, self.b, self.c, self.a])
        service.move_in_collection(self.list, self.d, self.d)   # onto itself: nothing
        service.move_in_collection(self.list, self.d, 999)      # not in the list: nothing
        self.assertEqual(service.collection_order(self.list), [self.d, self.b, self.c, self.a])

    def test_old_databases_keep_the_order_of_inclusion(self):
        self.db.set_membership(self.list, [self.a, self.b, self.c], True)
        self.db.close()
        conn = sqlite3.connect(self.path)   # a database from before the manual order
        conn.executescript("""
            CREATE TABLE old AS SELECT collection_id, movie_id, added_at FROM collection_movies;
            DROP TABLE collection_movies;
            CREATE TABLE collection_movies (collection_id INTEGER NOT NULL, movie_id INTEGER NOT NULL,
                added_at REAL NOT NULL, PRIMARY KEY (collection_id, movie_id));
            DELETE FROM old;""")
        conn.executemany("INSERT INTO collection_movies VALUES (?, ?, ?)",
                         [(self.list, self.c, 1.0), (self.list, self.a, 2.0), (self.list, self.b, 3.0)])
        conn.commit()
        conn.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.collection_order(self.list), [self.c, self.a, self.b])

    def test_sort_by_order(self):
        movies = [{"id": i} for i in (1, 2, 3, 4)]
        self.assertEqual([m["id"] for m in sort_by_order(movies, [3, 1, 2])], [3, 1, 2, 4])
        self.assertIn("manual", [option[0] for option in SORT_OPTIONS])


if __name__ == "__main__":
    unittest.main()
