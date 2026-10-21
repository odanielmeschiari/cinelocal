"""Tests for the updater (no network, no GUI). Run with: python3 -m unittest discover -s tests"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal import updater


class VersionTests(unittest.TestCase):
    def test_is_newer(self):
        self.assertTrue(updater.is_newer("v1.12.0", "1.11.0"))
        self.assertTrue(updater.is_newer("1.11", "1.2"))      # numeric, not alphabetical
        self.assertFalse(updater.is_newer("v1.11", "1.11.0"))
        self.assertFalse(updater.is_newer("1.0.0", "1.11.0"))


class ReleaseTests(unittest.TestCase):
    DATA = {"tag_name": "v1.12.0", "html_url": "https://github.com/o/r/releases/tag/v1.12.0",
            "assets": [{"name": "CineLocal-linux-x86_64", "browser_download_url": "https://x/linux",
                        "digest": "sha256:abc"},
                       {"name": "CineLocal-windows-x86_64.exe", "browser_download_url": "https://x/win"}]}

    def test_picks_the_platform_asset(self):
        linux = updater.parse_release(self.DATA, "linux")
        self.assertEqual((linux.version, linux.url, linux.sha256), ("1.12.0", "https://x/linux", "abc"))
        windows = updater.parse_release(self.DATA, "win32")
        self.assertEqual((windows.url, windows.sha256), ("https://x/win", ""))

    def test_no_asset_for_platform(self):
        self.assertEqual(updater.parse_release(self.DATA, "darwin").url, "")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.exe = self.tmp / "CineLocal"
        self.exe.write_bytes(b"old")
        self.payload = self.tmp / "payload"
        self.payload.write_bytes(b"new version")
        self._exe = updater._exe
        updater._exe = lambda: self.exe

    def tearDown(self):
        updater._exe = self._exe

    def release(self, sha256):
        return updater.Release("2.0", "", self.payload.as_uri(), sha256)

    def test_replaces_the_executable(self):
        updater.install(self.release(hashlib.sha256(b"new version").hexdigest()))
        self.assertEqual(self.exe.read_bytes(), b"new version")
        self.assertFalse((self.tmp / "CineLocal.new").exists())

    def test_bad_checksum_keeps_the_old_one(self):
        with self.assertRaises(OSError):
            updater.install(self.release("0" * 64))
        self.assertEqual(self.exe.read_bytes(), b"old")
        self.assertFalse((self.tmp / "CineLocal.new").exists())


if __name__ == "__main__":
    unittest.main()
