"""Tests for similar movies, franchises, duplicates, file info and statistics (no GUI).
Run with: python3 -m unittest discover -s tests"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal import mediainfo
from cinelocal.db import Database
from cinelocal.duplicates import find_duplicates
from cinelocal.franchises import franchise_plan
from cinelocal.parsing import parse_details
from cinelocal.similar import similar_movies
from cinelocal.stats import library_stats
from cinelocal.utils import format_hours, format_size


def movie(id, **kw):
    base = {"id": id, "kind": "movie", "genres": [], "cast": [], "director": None, "year": None,
            "year_guess": None, "rating": None, "votes": None, "runtime": None, "watched": False,
            "sort_title": str(id), "clean_title": f"m{id}", "display_title": f"M{id}", "status": "matched",
            "tmdb_id": None, "path": f"/m/{id}.mkv", "size": 0, "user_rating": 0, "franchise": None,
            "franchise_linked": 0}
    base.update(kw)
    return base


class SimilarTests(unittest.TestCase):
    def test_ranking_and_exclusions(self):
        a = movie(1, genres=["Sci-Fi", "Action"], director="Lana", year=1999, cast=[{"name": "Keanu", "character": ""}])
        sequel = movie(2, genres=["Sci-Fi", "Action"], director="Lana", year=2003, cast=[{"name": "Keanu", "character": ""}])
        genre_only = movie(3, genres=["Sci-Fi"], year=2010)
        unrelated = movie(4, genres=["Romance"])
        series = movie(-5, kind="series", genres=["Sci-Fi", "Action"])
        unknown = movie(6)   # no metadata yet
        result = similar_movies(a, [a, sequel, genre_only, unrelated, series, unknown])
        self.assertEqual([m["id"] for m in result], [2, 3])

    def test_same_franchise_links_movies_without_shared_genres(self):
        a = movie(1, franchise="Saga", genres=["Drama"])
        b = movie(2, franchise="Saga", genres=["Comedy"])
        self.assertEqual([m["id"] for m in similar_movies(a, [a, b])], [2])

    def test_genres_missing_on_both_sides_does_not_break(self):
        a, b = movie(1, director="Ana"), movie(2, director="Ana")
        self.assertEqual([m["id"] for m in similar_movies(a, [a, b])], [2])

    def test_series_are_compared_with_series(self):
        a = movie(-1, kind="series", genres=["Comedy"])
        b = movie(-2, kind="series", genres=["Comedy"])
        c = movie(3, genres=["Comedy"])
        self.assertEqual([m["id"] for m in similar_movies(a, [a, b, c])], [-2])

    def test_limit(self):
        a = movie(1, genres=["Drama"])
        others = [movie(i, genres=["Drama"]) for i in range(2, 40)]
        self.assertEqual(len(similar_movies(a, [a] + others, limit=5)), 5)


class FranchiseTests(unittest.TestCase):
    def test_parse_details_reads_the_collection(self):
        self.assertEqual(parse_details({"belongs_to_collection": {"id": 2344, "name": "The Matrix Collection"}})
                         ["franchise"], "The Matrix Collection")
        self.assertIsNone(parse_details({"belongs_to_collection": None})["franchise"])
        self.assertNotIn("franchise", parse_details({}))   # series have no such field

    def test_plan_needs_two_movies_and_skips_linked_ones(self):
        items = [movie(1, franchise="A"), movie(2, franchise="A"), movie(3, franchise="B"),
                 movie(4, franchise="C", franchise_linked=1), movie(5, franchise="C"), movie(6, franchise="C"),
                 movie(-7, kind="series")]
        self.assertEqual(franchise_plan(items), [("A", [1, 2]), ("C", [5, 6])])
        self.assertEqual(franchise_plan([movie(1, franchise="A", franchise_linked=1),
                                         movie(2, franchise="A", franchise_linked=1)]), [])


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "lib.db")
        self.ids = self.db.add_movies([dict(path=f"/m/{n}.mkv", file_name=f"{n}.mkv", size=1, clean_title=n,
                                            year_guess=2000, added_at=time.time()) for n in "ab"])

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_franchise_is_saved_and_a_change_has_to_be_linked_again(self):
        first = self.ids[0]
        self.db.save_metadata(first, {"franchise": "Saga", "status": "matched"})
        self.db.mark_franchise_linked([first])
        self.db.save_metadata(first, {"franchise": "Saga"})          # same franchise: stays linked
        self.assertEqual(self.db.get_movie(first)["franchise_linked"], 1)
        self.db.save_metadata(first, {"franchise": "Other saga"})    # a different one: link again
        movie_row = self.db.get_movie(first)
        self.assertEqual((movie_row["franchise"], movie_row["franchise_linked"]), ("Other saga", 0))
        self.db.save_metadata(first, {"franchise": None})
        self.assertIsNone(self.db.get_movie(first)["franchise"])

    def test_restoring_metadata_forgets_franchises(self):
        first = self.ids[0]
        self.db.save_metadata(first, {"franchise": "Saga"})
        self.db.mark_franchise_linked([first])
        self.db.restore(metadata=True)
        row = self.db.get_movie(first)
        self.assertEqual((row["franchise"], row["franchise_linked"]), (None, 0))

    def test_tech_info_is_stored_and_empty_means_unreadable(self):
        first, second = self.ids
        self.assertIsNone(self.db.get_movie(first)["tech"])
        self.db.save_tech(first, {"width": 1920, "height": 1080, "video": "H.264"})
        self.db.save_tech(second, {})
        self.assertEqual(self.db.get_movie(first)["tech"]["height"], 1080)
        self.assertEqual(self.db.get_movie(second)["tech"], {})


class DuplicateTests(unittest.TestCase):
    def test_movies_by_tmdb_id_or_file_title(self):
        a1 = movie(1, tmdb_id=603, display_title="The Matrix", path="/b/matrix.mkv")
        a2 = movie(2, tmdb_id=603, display_title="The Matrix", path="/a/matrix 4k.mkv")
        other = movie(3, tmdb_id=604)
        p1 = movie(4, status="pending", clean_title="The Thing", year_guess=1982)
        p2 = movie(5, status="pending", clean_title="Thing", year_guess=1982)
        p3 = movie(6, status="pending", clean_title="Thing", year_guess=2011)   # another year: another movie
        blank = [movie(7, status="pending", clean_title=""), movie(8, status="pending", clean_title="")]
        groups = find_duplicates([a1, a2, other, p1, p2, p3] + blank, {}, lambda sid: "")
        self.assertEqual([(g["title"], [f["id"] for f in g["files"]]) for g in groups],
                         [("M4", [4, 5]), ("The Matrix", [2, 1])])   # sorted by title

    def test_episodes_by_series_season_and_number(self):
        episodes = {1: [movie(10, kind="episode", season=1, episode=2, path="/x/a.mkv"),
                        movie(11, kind="episode", season=1, episode=2, path="/x/b.mkv"),
                        movie(12, kind="episode", season=1, episode=3),
                        movie(13, kind="episode", season=None, episode=None),
                        movie(14, kind="episode", season=None, episode=None)]}
        groups = find_duplicates([movie(-1, kind="series")], episodes, lambda sid: "The Office")
        self.assertEqual([(g["title"], [f["id"] for f in g["files"]]) for g in groups],
                         [("The Office S01E02", [10, 11])])


class MediaInfoTests(unittest.TestCase):
    def test_resolution_uses_the_width(self):
        label = mediainfo.resolution_label
        self.assertEqual([label(3840, 2160), label(3840, 1600), label(1920, 1080), label(1920, 800),
                          label(1440, 1080), label(1280, 720), label(1280, 536), label(720, 480), label(0, 0)],
                         ["4K", "4K", "1080p", "1080p", "1080p", "720p", "720p", "SD", ""])

    def test_codecs_and_channels(self):
        fourcc = lambda text: int.from_bytes(text.encode("latin-1"), "little")  # noqa: E731
        self.assertEqual(mediainfo.video_codec_label(fourcc("hevc")), "HEVC")
        self.assertEqual(mediainfo.video_codec_label(fourcc("zzzz")), "ZZZZ")
        self.assertEqual(mediainfo.audio_codec_label(fourcc("a52 ")), "AC3")
        self.assertEqual([mediainfo.channels_label(n) for n in (2, 6, 8, 5, 0)], ["2.0", "5.1", "7.1", "5ch", ""])

    def test_language_label(self):
        self.assertEqual([mediainfo.language_label(c) for c in (b"por", "ENG", b"pol", b"und", None)],
                         ["Portuguese", "English", "POL", "", ""])

    def test_badges(self):
        info = {"width": 1920, "height": 1080, "video": "H.264", "audio": "AAC", "channels": 2}
        self.assertEqual(mediainfo.badges(info), ["1080p", "H.264", "AAC 2.0"])
        self.assertEqual(mediainfo.badges({}), [])
        self.assertEqual(mediainfo.badges(None), [])
        self.assertEqual(mediainfo.badges({"width": 1280, "height": 720}), ["720p"])


class StatsTests(unittest.TestCase):
    def test_totals(self):
        films = [movie(1, genres=["Drama"], runtime=100, watched=True, year=1999, size=10, director="Ana, Beto",
                       cast=[{"name": "Zed", "character": ""}], user_rating=4),
                 movie(2, genres=["Drama", "Crime"], runtime=90, year=2005, size=20, user_rating=3.5),
                 movie(-3, kind="series", runtime=25, watched=False)]
        episodes = {3: [movie(10, kind="episode", series_id=3, ep_runtime=20, watched=True, size=5),
                        movie(11, kind="episode", series_id=3, ep_runtime=None, watched=True, size=5),
                        movie(12, kind="episode", series_id=3, watched=False, size=5)]}
        s = library_stats(films, episodes)
        self.assertEqual((s["movies"], s["watched_movies"], s["series"], s["episodes"], s["watched_episodes"]),
                         (2, 1, 1, 3, 2))
        self.assertEqual(s["minutes_watched"], 100 + 20 + 25)   # an episode with no length counts as the series'
        self.assertEqual((s["minutes_to_watch"], s["size"]), (90, 45))
        self.assertEqual(s["genres"][0], ("Drama", 2, 1))
        self.assertEqual(s["decades"], [(1990, 1), (2000, 1)])
        self.assertEqual((s["rated"], s["average_stars"]), (2, 3.75))
        self.assertEqual(s["stars"], [(3.5, 1), (4, 1)])
        self.assertEqual([n for n, _c in s["directors"]], ["Ana", "Beto"])

    def test_empty_library(self):
        s = library_stats([], {})
        self.assertEqual((s["movies"], s["minutes_watched"], s["average_stars"], s["genres"]), (0, 0, None, []))

    def test_formats(self):
        self.assertEqual(format_hours(5400), "90 h 00 min")
        self.assertEqual((format_size(512), format_size(2254857830), format_size(None)), ("512 B", "2.1 GB", "0 B"))


if __name__ == "__main__":
    unittest.main()
