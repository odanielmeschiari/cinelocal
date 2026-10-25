"""Tests for packaging/fetch_libmpv.py (no network). Run with: python3 -m unittest discover -s tests"""
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("fetch_libmpv", ROOT / "packaging" / "fetch_libmpv.py")
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)

# the names a release really lists (zhongfly/mpv-winbuild)
RELEASE_HTML = """
<a href="/zhongfly/mpv-winbuild/releases/download/2026-10-25-baa3e11d42/mpv-dev-aarch64-20261025-git-baa3e11d42.7z">
<a href="/zhongfly/mpv-winbuild/releases/download/2026-10-25-baa3e11d42/mpv-dev-lgpl-aarch64-20261025-git-baa3e11d42.7z">
<a href="/zhongfly/mpv-winbuild/releases/download/2026-10-25-baa3e11d42/mpv-dev-lgpl-x86_64-v3-20261025-git-baa3e11d42.7z">
<a href="/zhongfly/mpv-winbuild/releases/download/2026-10-25-baa3e11d42/mpv-dev-lgpl-x86_64-20261025-git-baa3e11d42.7z">
<a href="/zhongfly/mpv-winbuild/releases/download/2026-10-25-baa3e11d42/mpv-dev-x86_64-20261025-git-baa3e11d42.7z">
"""
ASSET = "mpv-dev-lgpl-x86_64-20261025-git-baa3e11d42.7z"


class ParsingTests(unittest.TestCase):
    def test_picks_the_lgpl_x86_64_build_that_runs_everywhere(self):
        self.assertEqual(fl.find_asset(RELEASE_HTML), ASSET)   # not -v3 (AVX2), not aarch64, not the GPL build

    def test_no_matching_build(self):
        self.assertIsNone(fl.find_asset("mpv-dev-x86_64-20261025-git-baa3e11d42.7z"))

    def test_checksums_file(self):
        h1, h2 = "a" * 64, "B" * 64
        text = f"{h1}  {ASSET}\n{h2} *other.7z\nnot a checksum line\n"
        self.assertEqual(fl.parse_checksums(text), {ASSET: h1, "other.7z": h2.lower()})

    def test_dll_sanity_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, small, wrong = (Path(tmp) / n for n in ("good", "small", "wrong"))
            good.write_bytes(b"MZ" + b"\0" * fl.MIN_DLL_SIZE)
            small.write_bytes(b"MZ" + b"\0" * 100)
            wrong.write_bytes(b"<html>" + b"\0" * fl.MIN_DLL_SIZE)
            self.assertEqual([fl.looks_like_dll(p) for p in (good, small, wrong, Path(tmp) / "none")],
                             [True, False, False, False])


class InstallTests(unittest.TestCase):
    """install() with the network and the unpacking replaced by fakes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "libmpv"
        self.payload = b"fake archive"
        self.good_sum = hashlib.sha256(self.payload).hexdigest()

    def run_install(self, checksums, html=RELEASE_HTML, payload=None, dll=True):
        def fake_text(url):
            return checksums if url.endswith("sha256.txt") else html

        def fake_download(url, dest):
            dest.write_bytes(self.payload if payload is None else payload)

        def fake_extract(archive, workdir):
            if not dll:
                return None
            path = workdir / "libmpv-2.dll"
            path.write_bytes(b"MZ-fake-dll")
            return path

        with mock.patch.object(fl, "latest_tag", return_value="2026-10-25-x"), \
                mock.patch.object(fl, "fetch_text", fake_text), mock.patch.object(fl, "download", fake_download), \
                mock.patch.object(fl, "extract_dll", fake_extract), mock.patch.object(fl, "say"):
            fl.install(self.dest, latest=True)

    def test_good_download_is_installed_without_leftovers(self):
        self.run_install(f"{self.good_sum}  {ASSET}\n")
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["libmpv-2.dll"])

    def test_wrong_checksum_is_refused_and_nothing_is_unpacked(self):
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.run_install(f"{'0' * 64}  {ASSET}\n")
        self.assertFalse(self.dest.exists())

    def test_release_without_checksum_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "unverified"):
            self.run_install("")
        self.assertFalse(self.dest.exists())

    def test_release_without_the_build(self):
        with self.assertRaisesRegex(RuntimeError, "no libmpv build"):
            self.run_install("", html="mpv-dev-x86_64-20261025-git-baa3e11d42.7z")

    def test_unpack_failure(self):
        with self.assertRaisesRegex(RuntimeError, "could not unpack"):
            self.run_install(f"{self.good_sum}  {ASSET}\n", dll=False)
        self.assertFalse(self.dest.exists())


class PinnedInstallTests(unittest.TestCase):
    """The default: the build pinned in packaging/libmpv-windows.lock.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "libmpv"
        self.payload = b"pinned archive"
        self.lock = {"repo": "https://example.invalid/releases", "tag": "t1", "asset": ASSET,
                     "sha256": hashlib.sha256(self.payload).hexdigest()}
        self.urls = []

    def run_install(self, lock=None, payload=None, error=None):
        def fake_download(url, dest):
            self.urls.append(url)
            if error:
                raise error
            dest.write_bytes(self.payload if payload is None else payload)

        def fake_extract(archive, workdir):
            path = workdir / "libmpv-2.dll"
            path.write_bytes(b"MZ-fake-dll")
            return path

        with mock.patch.object(fl, "load_lock", return_value=lock or self.lock), \
                mock.patch.object(fl, "download", fake_download), mock.patch.object(fl, "extract_dll", fake_extract), \
                mock.patch.object(fl, "say"):
            fl.install(self.dest)

    def test_the_lock_file_of_the_repository_is_valid(self):
        lock = fl.load_lock()
        self.assertRegex(lock["asset"], fl.ASSET.pattern)
        self.assertIn(lock["tag"].split("-")[-1], lock["asset"])      # the tag's commit is the asset's commit
        self.assertRegex(lock["sha256"], r"^[0-9a-f]{64}$")

    def test_installs_exactly_the_pinned_file_without_asking_for_the_latest(self):
        with mock.patch.object(fl, "latest_tag", side_effect=AssertionError("must not look for the latest")):
            self.run_install()
        self.assertEqual(self.urls, [f"https://example.invalid/releases/download/t1/{ASSET}"])
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["libmpv-2.dll"])

    def test_a_different_file_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.run_install(payload=b"something else")
        self.assertFalse(self.dest.exists())

    def test_a_release_that_was_removed_says_how_to_update_the_pin(self):
        gone = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO())
        with self.assertRaisesRegex(RuntimeError, "--print-lock"):
            self.run_install(error=gone)
        self.assertFalse(self.dest.exists())

    def test_an_invalid_lock_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "lock.json"
            bad.write_text(json.dumps({"repo": "r", "tag": "t", "asset": "a", "sha256": "not-a-hash"}))
            with self.assertRaisesRegex(RuntimeError, "not a valid lock"):
                fl.load_lock(bad)

    def print_lock(self, published_sha256):
        newest = {"repo": "https://example.invalid/releases", "tag": "t2", "asset": ASSET, "sha256": published_sha256}

        def fake_download(url, dest):
            dest.write_bytes(self.payload)

        out = io.StringIO()
        with mock.patch.object(fl, "resolve_latest", return_value=dict(newest)), \
                mock.patch.object(fl, "download", fake_download), mock.patch.object(fl, "say"), \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
            return fl.main(["--print-lock"]), out.getvalue()

    def test_print_lock_prints_the_hash_it_computed_from_the_download(self):
        code, text = self.print_lock(self.lock["sha256"])
        self.assertEqual(code, 0)
        printed = json.loads(text)
        self.assertEqual((printed["tag"], printed["sha256"]), ("t2", self.lock["sha256"]))

    def test_print_lock_refuses_a_download_that_differs_from_the_published_hash(self):
        code, text = self.print_lock("0" * 64)
        self.assertEqual((code, text), (1, ""))


class MainTests(unittest.TestCase):
    def test_default_is_the_pinned_build_and_latest_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fl, "install") as install:
            fl.main([tmp])
            fl.main([tmp, "--latest"])
        self.assertEqual([c.kwargs for c in install.call_args_list], [{"latest": False}, {"latest": True}])

    def test_already_installed_does_not_touch_the_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / fl.DLL).write_bytes(b"x")
            with mock.patch.object(fl, "install", side_effect=AssertionError("must not run")), \
                    mock.patch.object(fl, "say"):
                self.assertEqual(fl.main([tmp]), 0)

    def test_failure_is_an_exit_code_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fl, "install", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stderr"):
            self.assertEqual(fl.main([tmp]), 1)
            self.assertEqual(fl.main([]), 2)


@unittest.skipUnless(os.name == "posix", "uses small shell scripts as fake extractors")
class ExtractTests(unittest.TestCase):
    def script(self, directory: Path, name: str, body: str) -> str:
        path = directory / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return str(path)

    def test_tries_the_next_extractor_when_one_fails_or_writes_garbage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fails = self.script(tmp, "fails", "exit 1\n")
            garbage = self.script(tmp, "garbage", 'echo junk > "$4/libmpv-2.dll"\n')   # 7z-style: -oDIR is "$3"
            works = self.script(tmp, "works", f'out="$4"; {{ printf MZ; head -c {fl.MIN_DLL_SIZE} /dev/zero; }} > "$out/libmpv-2.dll"\n')
            archive = tmp / "a.7z"
            archive.write_bytes(b"x")
            with mock.patch.object(fl, "_seven_zip_programs", return_value=[]), \
                    mock.patch.object(fl, "_tar_programs", return_value=[fails, garbage, works]):
                dll = fl.extract_dll(archive, tmp)
            self.assertIsNotNone(dll)
            self.assertTrue(fl.looks_like_dll(dll))

    def test_nothing_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            archive = tmp / "a.7z"
            archive.write_bytes(b"x")
            with mock.patch.object(fl, "_seven_zip_programs", return_value=[self.script(tmp, "f", "exit 1\n")]), \
                    mock.patch.object(fl, "_tar_programs", return_value=[]):
                self.assertIsNone(fl.extract_dll(archive, tmp))


if __name__ == "__main__":
    unittest.main()
