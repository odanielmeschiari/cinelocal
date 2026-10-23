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
            uninstall_entry = (Path(home) / ".local/share/applications/cinelocal-uninstall.desktop").read_text()
            self.assertIn(f'Exec="{dest}" --uninstall', uninstall_entry)

    def test_reinstall_replaces_the_executable(self):
        with tempfile.TemporaryDirectory() as home:
            src = Path(home) / "new"
            with mock.patch.dict(os.environ, {"HOME": home}), mock.patch("subprocess.run"):
                src.write_bytes(b"v1")
                selfinstall.install(src)
                src.write_bytes(b"v2")
                dest = selfinstall.install(src)
            self.assertEqual(dest.read_bytes(), b"v2")

    def _install_with_data(self, home):
        src = Path(home) / "download" / "CineLocal-linux-x86_64"
        src.parent.mkdir()
        src.write_bytes(b"binary")
        with mock.patch.dict(os.environ, {"HOME": home}), mock.patch("subprocess.run"):
            dest = selfinstall.install(src)
        dirs = [Path(home) / name for name in ("config", "data", "cache")]
        for d in dirs:
            d.mkdir()
            (d / "x").write_text("data")
        return dest, dirs

    def _uninstall(self, home, dirs, purge):
        with mock.patch.dict(os.environ, {"HOME": home}), \
                mock.patch.multiple(selfinstall, CONFIG_DIR=dirs[0], DATA_DIR=dirs[1], CACHE_DIR=dirs[2]):
            selfinstall.uninstall(purge)

    def test_uninstall_keeps_the_data(self):
        with tempfile.TemporaryDirectory() as home:
            dest, dirs = self._install_with_data(home)
            self._uninstall(home, dirs, purge=False)
            self.assertFalse(dest.parent.exists())
            self.assertFalse((Path(home) / ".local/share/applications/cinelocal.desktop").exists())
            self.assertFalse((Path(home) / ".local/share/applications/cinelocal-uninstall.desktop").exists())
            self.assertFalse((Path(home) / ".local/share/icons/hicolor/scalable/apps/cinelocal.svg").exists())
            self.assertTrue(all(d.exists() for d in dirs))

    def test_uninstall_with_purge_deletes_the_data(self):
        with tempfile.TemporaryDirectory() as home:
            dest, dirs = self._install_with_data(home)
            self._uninstall(home, dirs, purge=True)
            self.assertFalse(dest.parent.exists())
            self.assertFalse(any(d.exists() for d in dirs))


if __name__ == "__main__":
    unittest.main()
