"""Collection look (stack / own cover / separate), and the quality read from file names.

Run with: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal.filters import collection_group_ids, collection_mode, set_collection_mode
from cinelocal.mediainfo import name_quality
from cinelocal.ui.detail_widgets import _tech_rows


class CollectionLookTests(unittest.TestCase):
    def test_group_ids_skip_separate_and_repeats(self):
        self.assertEqual(collection_group_ids([3, 1], [1], [1, 2, 3]), [3, 2])
        self.assertEqual(collection_group_ids([], [], []), [])

    def test_mode_of_a_collection(self):
        self.assertEqual(collection_mode([1, 2], {"2": "cover"}, 1), "stack")
        self.assertEqual(collection_mode([1, 2], {"2": "cover"}, 2), "cover")
        self.assertEqual(collection_mode([1, 2], {"2": "cover"}, 9), "separate")

    def test_choosing_a_mode(self):
        values = set_collection_mode([1], [2], {"1": "cover"}, 1, "separate")
        self.assertEqual(values, {"grouped_collections": [], "separate_collections": [2, 1], "collection_covers": {}})
        values = set_collection_mode([], [5], {}, 5, "cover")   # separate -> own cover
        self.assertEqual(values, {"grouped_collections": [5], "separate_collections": [],
                                  "collection_covers": {"5": "cover"}})
        values = set_collection_mode([5], [], {"5": "cover"}, 5, "stack")
        self.assertEqual(values, {"grouped_collections": [5], "separate_collections": [], "collection_covers": {}})

    def test_automatic_collection_can_be_made_separate(self):
        group_ids = collection_group_ids([], [], [7])   # grouped only because of the franchise option
        self.assertEqual(collection_mode(group_ids, {}, 7), "stack")
        values = set_collection_mode([], [], {}, 7, "separate")
        group_ids = collection_group_ids(values["grouped_collections"], values["separate_collections"], [7])
        self.assertEqual(collection_mode(group_ids, {}, 7), "separate")


class NameQualityTests(unittest.TestCase):
    def test_file_name(self):
        self.assertEqual(name_quality("/m/Movie.2010.1080p.BluRay.x264.mkv"), "1080p")
        self.assertEqual(name_quality("/m/Movie (2010) [720p].mp4"), "720p")
        self.assertEqual(name_quality("/m/Movie.2160p.HDR.mkv"), "4K")
        self.assertEqual(name_quality("/m/Movie.UHD.mkv"), "4K")
        self.assertEqual(name_quality("/m/Movie.DVDRip.avi"), "SD")

    def test_folder_name_and_nothing(self):
        self.assertEqual(name_quality("/m/Movie [1080p]/movie.mkv"), "1080p")
        self.assertEqual(name_quality("/m/Movie/movie.mkv"), "")
        self.assertEqual(name_quality("/m/Movie.10800.mkv"), "")   # not a resolution
        self.assertEqual(name_quality(None), "")

    def test_more_info_quality_row(self):
        quality = lambda tech, path=None: dict(_tech_rows(tech, path))["Quality"]
        self.assertEqual(quality({"width": 1920, "height": 800}, "/m/x.720p.mkv"), "1080p")   # the real one wins
        self.assertEqual(quality({}, "/m/x.720p.mkv"), "720p (from the file name)")
        self.assertIsNone(quality({}, "/m/x.mkv"))


if __name__ == "__main__":
    unittest.main()
