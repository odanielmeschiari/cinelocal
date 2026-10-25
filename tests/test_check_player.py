"""Tests for `CineLocal --check-player` (the smoke test the release workflow runs on the packaged build)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from cinelocal import app
    from cinelocal import mpvbackend
except ImportError:   # PySide6 is not installed
    app = None


@unittest.skipIf(app is None, "needs PySide6")
class CheckPlayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "app").mkdir()
        self.out = self.root / "check.txt"

    def run_check(self, *flags, vlc_error="", mpv_reason="", mpv_path=""):
        argv = ["CineLocal", "--check-player", str(self.out), *flags]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(sys, "_MEIPASS", str(self.root / "app"), create=True), \
                mock.patch("cinelocal.ui.player_page.load_error", return_value=vlc_error), \
                mock.patch.object(mpvbackend, "unavailable_reason", return_value=mpv_reason), \
                mock.patch.object(mpvbackend, "library_path", return_value=mpv_path):
            return app._check_player()

    def test_reports_both_players_and_exits_zero(self):
        code = self.run_check(mpv_path="/usr/lib/libmpv.so.2")
        self.assertEqual(code, 0)
        self.assertEqual(self.out.read_text(encoding="utf-8").splitlines(),
                         ["built-in player OK", "libmpv: /usr/lib/libmpv.so.2"])

    def test_libvlc_failure_is_an_error(self):
        self.assertEqual(self.run_check(vlc_error="libVLC could not be loaded"), 1)
        self.assertEqual(self.out.read_text(encoding="utf-8").splitlines()[0], "libVLC could not be loaded")

    def test_a_missing_libmpv_is_only_an_error_when_it_is_required(self):
        self.assertEqual(self.run_check(mpv_reason="OSError: no libmpv"), 0)
        self.assertEqual(self.run_check("--bundled-libmpv", mpv_reason="OSError: no libmpv"), 1)

    def test_required_libmpv_must_be_the_copy_inside_the_app(self):
        inside = self.root / "app" / "libmpv.so.2"
        inside.write_bytes(b"x")
        self.assertEqual(self.run_check("--bundled-libmpv", mpv_path=str(inside)), 0)
        self.assertEqual(self.run_check("--bundled-libmpv", mpv_path="/usr/lib/x86_64-linux-gnu/libmpv.so.2"), 1)
        self.assertIn("must be the copy bundled", self.out.read_text(encoding="utf-8"))

    def test_the_result_file_is_optional(self):
        argv = ["CineLocal", "--check-player"]
        with mock.patch.object(sys, "argv", argv), mock.patch("cinelocal.ui.player_page.load_error", return_value=""), \
                mock.patch.object(mpvbackend, "unavailable_reason", return_value=""), \
                mock.patch.object(mpvbackend, "library_path", return_value="/x/libmpv.so.2"):
            self.assertEqual(app._check_player(), 0)


if __name__ == "__main__":
    unittest.main()
