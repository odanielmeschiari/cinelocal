"""Tests for the automatic VLC installation (no GUI, no network).
Run with: python3 -m unittest discover -s tests"""
import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal import vlc_setup


def make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_unpacks_without_the_top_folder_and_replaces_the_old_copy(self):
        archive, target = self.tmp / "vlc.zip", self.tmp / "vlc"
        target.mkdir()
        (target / "old.txt").write_text("old")
        make_zip(archive, {"vlc-3.0.21/libvlc.dll": b"x", "vlc-3.0.21/plugins/a/b.dll": b"y"})
        vlc_setup._extract(archive, target)
        self.assertTrue((target / "libvlc.dll").is_file())
        self.assertTrue((target / "plugins" / "a" / "b.dll").is_file())
        self.assertFalse((target / "old.txt").exists())
        self.assertFalse((self.tmp / "vlc.new").exists())

    def test_rejects_paths_that_leave_the_folder_and_archives_without_libvlc(self):
        archive, target = self.tmp / "bad.zip", self.tmp / "vlc"
        make_zip(archive, {"vlc/libvlc.dll": b"x", "vlc/../../evil.txt": b"y"})
        with self.assertRaises(ValueError):
            vlc_setup._extract(archive, target)
        self.assertFalse(target.exists())
        self.assertFalse((self.tmp.parent / "evil.txt").exists())
        make_zip(archive, {"vlc/readme.txt": b"x"})
        with self.assertRaises(ValueError):
            vlc_setup._extract(archive, target)


class ChecksumTests(unittest.TestCase):
    def check(self, text, data=b"abc"):
        archive = Path(tempfile.mkdtemp()) / "f.zip"
        archive.write_bytes(data)
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = text.encode()
        with mock.patch.object(vlc_setup.urllib.request, "urlopen", return_value=response):
            vlc_setup._verify_sha256(archive, "https://example.invalid/f.sha256")

    def test_matching_and_wrong_checksum(self):
        good = hashlib.sha256(b"abc").hexdigest()
        self.check(f"{good}  vlc.zip\n")
        with self.assertRaises(ValueError):
            self.check("0" * 64 + "  vlc.zip\n")

    def test_checksum_not_published_is_accepted(self):
        error = vlc_setup.urllib.error.HTTPError("u", 404, "not found", {}, None)
        with mock.patch.object(vlc_setup.urllib.request, "urlopen", side_effect=error):
            vlc_setup._verify_sha256(Path(__file__), "https://example.invalid/f.sha256")


class InstallTests(unittest.TestCase):
    def test_linux_runs_the_package_manager_through_pkexec(self):
        which = {"apt-get": "/usr/bin/apt-get", "pkexec": "/usr/bin/pkexec"}
        with mock.patch.object(vlc_setup.shutil, "which", side_effect=which.get), \
                mock.patch.object(vlc_setup.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            vlc_setup._install_linux(lambda text: None)
        self.assertEqual(run.call_args.args[0][:2], ["pkexec", "env"])
        self.assertIn("apt-get install -y vlc", run.call_args.args[0][-1])

    def test_linux_without_pkexec_or_after_cancel_explains(self):
        with mock.patch.object(vlc_setup.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                vlc_setup._install_linux(lambda text: None)
        with mock.patch.object(vlc_setup.shutil, "which", return_value="/bin/x"), \
                mock.patch.object(vlc_setup.subprocess, "run", return_value=mock.Mock(returncode=126)):
            with self.assertRaises(RuntimeError):
                vlc_setup._install_linux(lambda text: None)

    def test_python_vlc_is_installed_with_pip_when_missing(self):
        with mock.patch.object(vlc_setup.importlib.util, "find_spec", return_value=None), \
                mock.patch.object(vlc_setup, "_pip_install") as pip, \
                mock.patch.object(vlc_setup, "_install_linux"), mock.patch.object(vlc_setup.sys, "platform", "linux"):
            vlc_setup.install()
        pip.assert_called_once()

    def test_windows_download_falls_back_to_the_second_mirror(self):
        calls = []

        def download(url, target):
            calls.append(url)
            if len(calls) == 1:
                raise OSError("offline")
            make_zip(target, {"vlc-3.0.21/libvlc.dll": b"x", "vlc-3.0.21/plugins/p.dll": b"y"})

        local = Path(tempfile.mkdtemp()) / "vlc"
        with mock.patch.object(vlc_setup, "_download", side_effect=download), \
                mock.patch.object(vlc_setup, "_verify_sha256"), mock.patch.object(vlc_setup, "LOCAL_DIR", local):
            vlc_setup._install_windows(lambda text: None)
        self.assertEqual(len(calls), 2)
        self.assertTrue((local / "libvlc.dll").is_file())


if __name__ == "__main__":
    unittest.main()
