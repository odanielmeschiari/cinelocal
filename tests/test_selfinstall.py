"""Tests for installing the downloaded executable. Run with: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal import selfinstall


@unittest.skipIf(sys.platform == "win32", "Linux menu entry")
class LinuxInstallTests(unittest.TestCase):
    def test_install_creates_executable_and_menu_entry(self):
        with tempfile.TemporaryDirectory() as home:
            src = Path(home) / "download" / "CineLocal-linux-x86_64"
            src.parent.mkdir()
            src.write_bytes(b"binary")
            with mock.patch.dict(os.environ, {"HOME": home}), mock.patch("subprocess.run"):
                dest = selfinstall.install(src)
            self.assertEqual(dest, Path(home) / ".local/opt/cinelocal/CineLocal")
            self.assertEqual(dest.read_bytes(), b"binary")
            self.assertTrue(os.access(dest, os.X_OK))
            entry = (Path(home) / ".local/share/applications/cinelocal.desktop").read_text()
            self.assertIn(f'Exec="{dest}"', entry)
            self.assertTrue((Path(home) / ".local/share/icons/hicolor/scalable/apps/cinelocal.svg").exists())

    def test_reinstall_replaces_the_executable(self):
        with tempfile.TemporaryDirectory() as home:
            src = Path(home) / "new"
            with mock.patch.dict(os.environ, {"HOME": home}), mock.patch("subprocess.run"):
                src.write_bytes(b"v1")
                selfinstall.install(src)
                src.write_bytes(b"v2")
                dest = selfinstall.install(src)
            self.assertEqual(dest.read_bytes(), b"v2")


if __name__ == "__main__":
    unittest.main()
