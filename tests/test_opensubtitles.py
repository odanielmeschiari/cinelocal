"""Tests for the automatic subtitle download (no network, no GUI window).

Run with: python3 -m unittest discover -s tests"""
import importlib.util
import io
import os
import struct
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal import opensubtitles as osub
from cinelocal.opensubtitles import (OpenSubtitlesClient, OpenSubtitlesError, best_subtitle, fetch_subtitle,
                                     has_subtitle, movie_hash)


def _result(file_id, language="en", downloads=0, **flags):
    return {"attributes": {"language": language, "download_count": downloads,
                           "files": [{"file_id": file_id}], **flags}}


def _reference_hash(path):
    """The hash as published in the OpenSubtitles documentation, byte by byte."""
    size = os.path.getsize(path)
    total = size
    with open(path, "rb") as f:
        for _ in range(65536 // 8):
            total = (total + struct.unpack("<q", f.read(8))[0]) & 0xFFFFFFFFFFFFFFFF
        f.seek(max(0, size - 65536))
        for _ in range(65536 // 8):
            total = (total + struct.unpack("<q", f.read(8))[0]) & 0xFFFFFFFFFFFFFFFF
    return f"{total:016x}"


class FakeClient:
    """Answers searches from `hash_results` (moviehash=...) and `query_results` (query=...)."""

    def __init__(self, hash_results=(), query_results=(), content=b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"):
        self.hash_results, self.query_results, self.content = list(hash_results), list(query_results), content
        self.searches, self.downloads = [], []

    def search(self, **params):
        self.searches.append(params)
        return self.hash_results if "moviehash" in params else self.query_results

    def download(self, file_id):
        self.downloads.append(file_id)
        return self.content


class HashTests(unittest.TestCase):
    def test_matches_the_reference_algorithm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.mkv")
            with open(path, "wb") as f:
                f.write(os.urandom(300_000))
            self.assertEqual(movie_hash(path), _reference_hash(path))

    def test_tiny_files_have_no_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.mkv")
            Path(path).write_bytes(b"x" * 1000)
            self.assertIsNone(movie_hash(path))


class BestSubtitleTests(unittest.TestCase):
    def test_exact_file_match_beats_popularity(self):
        best = best_subtitle([_result(1, downloads=9000), _result(2, downloads=5, moviehash_match=True)])
        self.assertEqual(best["files"][0]["file_id"], 2)

    def test_human_translation_beats_machine_translation(self):
        best = best_subtitle([_result(1, downloads=9000, ai_translated=True), _result(2, downloads=5)])
        self.assertEqual(best["files"][0]["file_id"], 2)

    def test_most_downloaded_wins_otherwise(self):
        best = best_subtitle([_result(1, downloads=3), _result(2, downloads=30), _result(3, downloads=7)])
        self.assertEqual(best["files"][0]["file_id"], 2)

    def test_forced_only_and_fileless_results_are_ignored(self):
        self.assertIsNone(best_subtitle([_result(1, foreign_parts_only=True), {"attributes": {"files": []}}, {}]))
        self.assertIsNone(best_subtitle([]))


class FetchSubtitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "The.Matrix.1999.mkv")
        Path(self.path).write_bytes(os.urandom(200_000))

    def tearDown(self):
        self.tmp.cleanup()

    def test_saves_next_to_the_video_with_the_language_of_the_result(self):
        client = FakeClient(hash_results=[_result(7, "pt-BR", moviehash_match=True)])
        saved = fetch_subtitle(client, self.path, "The Matrix", 1999, "pt-br,pt-pt")
        self.assertEqual(saved, os.path.join(self.tmp.name, "The.Matrix.1999.pt-BR.srt"))
        self.assertEqual(Path(saved).read_bytes(), client.content)
        self.assertEqual(client.downloads, [7])
        self.assertEqual(len(client.searches), 1)   # the file hash was enough
        self.assertEqual(client.searches[0]["moviehash"], movie_hash(self.path))
        self.assertFalse(os.path.exists(saved + ".part"))

    def test_falls_back_to_title_and_year(self):
        client = FakeClient(query_results=[_result(3, "en", 10)])
        saved = fetch_subtitle(client, self.path, "The Matrix", 1999, "en")
        self.assertTrue(saved.endswith("The.Matrix.1999.en.srt"))
        self.assertEqual(client.searches[-1], {"query": "The Matrix", "languages": "en", "type": "movie", "year": 1999})

    def test_hash_search_results_that_do_not_match_the_file_are_not_trusted(self):
        client = FakeClient(hash_results=[_result(1, downloads=1)], query_results=[_result(2, downloads=1)])
        fetch_subtitle(client, self.path, "The Matrix", 1999, "en")
        self.assertEqual(client.downloads, [2])

    def test_episodes_are_searched_by_season_and_episode(self):
        client = FakeClient(query_results=[_result(3, "en")])
        fetch_subtitle(client, self.path, "Breaking Bad", None, "en", season=1, episode=2)
        self.assertEqual(client.searches[-1], {"query": "Breaking Bad", "languages": "en", "type": "episode",
                                               "season_number": 1, "episode_number": 2})

    def test_nothing_found_saves_nothing(self):
        client = FakeClient()
        self.assertIsNone(fetch_subtitle(client, self.path, "The Matrix", 1999, "en"))
        self.assertEqual(client.downloads, [])
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["The.Matrix.1999.mkv"])

    def test_a_video_that_already_has_a_subtitle_is_left_alone(self):
        for existing in ("The.Matrix.1999.srt", "The.Matrix.1999.pt-BR.srt", "the.matrix.1999.EN.SRT"):
            with self.subTest(existing=existing):
                sub = os.path.join(self.tmp.name, existing)
                Path(sub).write_text("x")
                client = FakeClient(query_results=[_result(3)])
                self.assertTrue(has_subtitle(self.path))
                self.assertIsNone(fetch_subtitle(client, self.path, "The Matrix", 1999, "en"))
                self.assertEqual(client.searches, [])
                os.remove(sub)
        self.assertFalse(has_subtitle(self.path))

    def test_another_movie_subtitle_in_the_same_folder_does_not_count(self):
        Path(self.tmp.name, "The.Matrix.Reloaded.2003.srt").write_text("x")
        self.assertFalse(has_subtitle(self.path))

    def test_missing_video_is_ignored(self):
        self.assertIsNone(fetch_subtitle(FakeClient(), self.path + ".gone", "X", None, "en"))


class ClientTests(unittest.TestCase):
    @staticmethod
    def _http_error(code):
        return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(b"{}"))

    def test_http_errors_become_typed_errors(self):
        client = OpenSubtitlesClient("key")
        for code, kind in ((401, "auth"), (403, "auth"), (406, "limit"), (404, "other")):
            with self.subTest(code=code), mock.patch.object(osub.urllib.request, "urlopen",
                                                            side_effect=self._http_error(code)):
                with self.assertRaises(OpenSubtitlesError) as ctx:
                    client.search(query="x")
                self.assertEqual(ctx.exception.kind, kind)

    def test_server_trouble_is_retried_then_reported(self):
        client = OpenSubtitlesClient("key")
        with mock.patch.object(osub.urllib.request, "urlopen", side_effect=self._http_error(503)) as opener, \
                mock.patch.object(osub.time, "sleep"):
            with self.assertRaises(OpenSubtitlesError) as ctx:
                client.search(query="x")
        self.assertEqual((ctx.exception.kind, opener.call_count), ("limit", 3))

    def test_connection_failure_is_a_network_error(self):
        client = OpenSubtitlesClient("key")
        with mock.patch.object(osub.urllib.request, "urlopen", side_effect=urllib.error.URLError("down")), \
                mock.patch.object(osub.time, "sleep"):
            with self.assertRaises(OpenSubtitlesError) as ctx:
                client.search(query="x")
        self.assertEqual(ctx.exception.kind, "network")

    def test_no_key_never_reaches_the_network(self):
        with mock.patch.object(osub.urllib.request, "urlopen") as opener:
            with self.assertRaises(OpenSubtitlesError) as ctx:
                OpenSubtitlesClient("  ").search(query="x")
        self.assertEqual(ctx.exception.kind, "auth")
        opener.assert_not_called()

    def test_search_sends_lowercase_sorted_parameters_and_the_key(self):
        client = OpenSubtitlesClient("secret")
        client._request = mock.Mock(return_value=b'{"data": [{"id": "1"}]}')
        self.assertEqual(client.search(year=1999, query="The Matrix", languages="PT-BR", type="movie", extra=None),
                         [{"id": "1"}])
        url = client._request.call_args[0][0]
        self.assertTrue(url.endswith("/subtitles?languages=pt-br&query=the+matrix&type=movie&year=1999"), url)

    def test_download_fetches_the_link_without_sending_the_key(self):
        client = OpenSubtitlesClient("secret")
        client._request = mock.Mock(side_effect=[b'{"link": "https://dl.example/file.srt"}', b"subtitle"])
        self.assertEqual(client.download(42), b"subtitle")
        first, second = client._request.call_args_list
        self.assertEqual(first.args[1], {"file_id": 42, "sub_format": "srt"})
        self.assertEqual((second.args[0], second.kwargs), ("https://dl.example/file.srt", {"send_key": False}))

    def test_download_without_link_is_an_error(self):
        client = OpenSubtitlesClient("secret")
        client._request = mock.Mock(return_value=b'{"message": "nope"}')
        with self.assertRaises(OpenSubtitlesError):
            client.download(1)

    def test_the_key_is_sent_in_the_header_but_not_to_the_file_host(self):
        client = OpenSubtitlesClient("secret")
        seen = []

        def fake_urlopen(request, timeout):
            seen.append(request)
            return io.BytesIO(b"{}")

        with mock.patch.object(osub.urllib.request, "urlopen", fake_urlopen):
            client._request("https://api.example/x")
            client._request("https://dl.example/y", send_key=False)
        self.assertEqual(seen[0].get_header("Api-key"), "secret")
        self.assertIsNone(seen[1].get_header("Api-key"))
        self.assertTrue(seen[0].get_header("User-agent").startswith("CineLocal v"))


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "needs PySide6 (the service is a QObject)")
class ServiceQueueTests(unittest.TestCase):
    def setUp(self):
        from cinelocal.config import Settings
        from cinelocal.db import Database
        from cinelocal.service import LibraryService

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = Database(root / "lib.db")
        self.settings = Settings(root / "settings.json")
        self.service = LibraryService(self.db, self.settings)
        self.service.run_async = lambda fn, ok=None, err=None: ok(fn())   # runs the job right here
        self.messages, self.errors = [], []
        self.service.message.connect(self.messages.append)
        self.service.error.connect(self.errors.append)
        self.settings.update(opensubtitles_api_key="key", language="en-US")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def add(self, *names, episode=None):
        rows = []
        for name in names:
            row = dict(path=f"/m/{name}.mkv", file_name=f"{name}.mkv", size=1, clean_title=name,
                       year_guess=2000, added_at=time.time())
            if episode:
                row.update(kind="episode", season=episode[0], episode=episode[1],
                           series_id=self.db.ensure_series(name, None))
            rows.append(row)
        ids = self.db.add_movies(rows)
        self.service.reload()
        return ids

    def run_with(self, fake, ids):
        with mock.patch("cinelocal.service.fetch_subtitle", fake):
            self.service.download_subtitles(ids)

    def test_new_movies_are_downloaded_in_the_metadata_language(self):
        calls = []
        ids = self.add("A", "B")
        self.run_with(lambda client, path, title, year, langs, season, episode:
                      calls.append((path, title, year, langs, season, episode)) or path, ids)
        self.assertEqual(calls, [("/m/A.mkv", "A", 2000, "en", None, None),
                                 ("/m/B.mkv", "B", 2000, "en", None, None)])
        self.assertEqual(self.settings.get("subtitle_queue"), [])
        self.assertEqual(self.messages, ["2 subtitle(s) downloaded."])

    def test_subtitle_language_setting_wins_and_portuguese_covers_both_variants(self):
        langs = []
        self.settings.update(subtitle_language="pt")
        self.run_with(lambda client, path, title, year, l, season, episode: langs.append(l), self.add("A"))
        self.assertEqual(langs, ["pt-br,pt-pt"])

    def test_episodes_send_season_and_episode(self):
        calls = []
        self.run_with(lambda client, path, title, year, langs, season, episode:
                      calls.append((title, season, episode)), self.add("Show", episode=(2, 5)))
        self.assertEqual(calls, [("Show", 2, 5)])

    def test_nothing_happens_without_a_key_or_with_subtitles_turned_off(self):
        calls = []
        ids = self.add("A")
        self.settings.update(opensubtitles_api_key="")
        self.run_with(lambda *a: calls.append(a), ids)
        self.settings.update(opensubtitles_api_key="key", subtitle_language="off")
        self.run_with(lambda *a: calls.append(a), ids)
        self.settings.update(subtitle_language="forced")
        self.run_with(lambda *a: calls.append(a), ids)
        self.assertEqual((calls, self.settings.get("subtitle_queue")), ([], []))

    def test_the_daily_limit_keeps_the_rest_for_the_next_scan(self):
        ids = self.add("A", "B", "C")

        def limited(client, path, *rest):
            if path.endswith("B.mkv"):
                raise OpenSubtitlesError("OpenSubtitles daily download limit reached.", "limit")
            return path

        self.run_with(limited, ids)
        self.assertEqual(self.settings.get("subtitle_queue"), ["/m/B.mkv", "/m/C.mkv"])
        self.assertIn("limit reached", self.messages[0])
        self.assertIn("1 subtitle(s) downloaded.", self.messages[0])

        calls = []   # next scan: nothing new was added, the leftovers are tried again
        self.run_with(lambda client, path, *rest: calls.append(path), [])
        self.assertEqual(calls, ["/m/B.mkv", "/m/C.mkv"])
        self.assertEqual(self.settings.get("subtitle_queue"), [])

    def test_a_rejected_key_is_reported_and_nothing_is_lost(self):
        def rejected(*args):
            raise OpenSubtitlesError("OpenSubtitles rejected the API key.", "auth")

        self.run_with(rejected, self.add("A"))
        self.assertEqual(self.errors, ["OpenSubtitles rejected the API key."])
        self.assertEqual(self.settings.get("subtitle_queue"), ["/m/A.mkv"])

    def test_a_problem_with_one_movie_does_not_stop_the_others(self):
        calls = []

        def flaky(client, path, *rest):
            calls.append(path)
            if path.endswith("A.mkv"):
                raise OpenSubtitlesError("HTTP error 500", "other")
            if path.endswith("B.mkv"):
                raise PermissionError("read-only")
            return path

        self.run_with(flaky, self.add("A", "B", "C"))
        self.assertEqual(calls, ["/m/A.mkv", "/m/B.mkv", "/m/C.mkv"])
        self.assertEqual(self.settings.get("subtitle_queue"), [])
        self.assertIn("1 subtitle(s) downloaded.", self.messages[0])
        self.assertIn("1 could not be saved", self.messages[0])

    def test_files_that_left_the_library_are_dropped_from_the_queue(self):
        self.settings.update(subtitle_queue=["/m/gone.mkv"])
        calls = []
        self.run_with(lambda client, path, *rest: calls.append(path), self.add("A"))
        self.assertEqual(calls, ["/m/A.mkv"])
        self.assertEqual(self.settings.get("subtitle_queue"), [])

    def test_shutdown_stops_a_download_in_progress(self):
        ids = self.add("A", "B")
        calls = []

        def first_then_quit(client, path, *rest):
            calls.append(path)
            self.service.shutdown()

        self.run_with(first_then_quit, ids)
        self.assertEqual(calls, ["/m/A.mkv"])
        self.assertEqual(self.settings.get("subtitle_queue"), ["/m/B.mkv"])


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "needs PySide6 (the service is a QObject)")
class ManualSearchTests(unittest.TestCase):
    """The 'Search on OpenSubtitles' button of the player's subtitle menu."""

    def setUp(self):
        from cinelocal.config import Settings
        from cinelocal.db import Database
        from cinelocal.service import LibraryService

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.video = str(root / "The.Matrix.1999.mkv")
        Path(self.video).write_bytes(b"x")
        self.db = Database(root / "lib.db")
        self.db.add_movies([dict(path=self.video, file_name="The.Matrix.1999.mkv", size=1,
                                 clean_title="The Matrix", year_guess=1999, added_at=time.time())])
        self.settings = Settings(root / "settings.json")
        self.settings.update(opensubtitles_api_key="key", language="pt-BR")
        self.service = LibraryService(self.db, self.settings)
        self.service.reload()
        self.service.run_async = lambda fn, ok=None, err=None: self._run(fn, ok, err)
        self.messages, self.errors, self.saved = [], [], []
        self.service.message.connect(self.messages.append)
        self.service.error.connect(self.errors.append)

    def _run(self, fn, ok, err):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - what the worker thread does
            return err(exc)
        ok(result)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def search(self, fake, path=None):
        with mock.patch("cinelocal.service.fetch_subtitle", fake):
            self.service.search_subtitle(path or self.video, self.saved.append)

    def test_downloads_and_hands_the_file_to_the_player(self):
        calls = []
        self.search(lambda client, path, title, year, langs, season, episode:
                    calls.append((title, year, langs, season, episode)) or path + ".pt-BR.srt")
        self.assertEqual(calls, [("The Matrix", 1999, "pt-br,pt-pt", None, None)])
        self.assertEqual(self.saved, [self.video + ".pt-BR.srt"])
        self.assertEqual(self.messages[-1], "Subtitle downloaded from OpenSubtitles.")

    def test_works_even_when_subtitles_are_turned_off_in_settings(self):
        self.settings.update(subtitle_language="off")
        langs = []
        self.search(lambda client, path, title, year, l, season, episode: langs.append(l) or "x.srt")
        self.assertEqual(langs, ["pt-br,pt-pt"])   # falls back to the metadata language (pt-BR)
        self.assertEqual(self.saved, ["x.srt"])

    def test_nothing_found_is_reported(self):
        self.search(lambda *a: None)
        self.assertEqual((self.saved, self.messages[-1]), ([], "No subtitle found on OpenSubtitles for this movie."))

    def test_an_existing_subtitle_is_not_replaced(self):
        Path(self.tmp.name, "The.Matrix.1999.en.srt").write_text("mine")
        calls = []
        self.search(lambda *a: calls.append(a))
        self.assertEqual((calls, self.saved), ([], []))
        self.assertIn("already has a subtitle", self.messages[-1])

    def test_without_a_key_it_asks_for_one(self):
        self.settings.update(opensubtitles_api_key="")
        calls = []
        self.search(lambda *a: calls.append(a))
        self.assertEqual((calls, self.saved, len(self.errors)), ([], [], 1))

    def test_errors_are_reported(self):
        def rejected(*args):
            raise OpenSubtitlesError("OpenSubtitles rejected the API key.", "auth")

        def limit(*args):
            raise OpenSubtitlesError("OpenSubtitles daily download limit reached.", "limit")

        def read_only(*args):
            raise PermissionError("read-only")

        self.search(rejected)
        self.assertEqual(self.errors, ["OpenSubtitles rejected the API key."])
        self.search(limit)
        self.assertEqual(self.messages[-1], "OpenSubtitles daily download limit reached.")
        self.search(read_only)
        self.assertIn("writable", self.messages[-1])
        self.assertEqual(self.saved, [])

    def test_a_video_outside_the_library_is_ignored(self):
        calls = []
        self.search(lambda *a: calls.append(a), path="/somewhere/else.mkv")
        self.assertEqual((calls, self.messages, self.errors), ([], [], []))


if __name__ == "__main__":
    unittest.main()
