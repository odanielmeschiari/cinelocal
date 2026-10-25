"""Tests for the optional libmpv engine. Run with: python3 -m unittest discover -s tests

Most tests use a fake mpv core (no libmpv needed); the last one plays a real file and is skipped without libmpv/ffmpeg.
"""
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinelocal import mpvbackend as mb
from cinelocal.tracks import choose_track


class FakeCore:
    """The few properties of an mpv core that the engine reads; `command` records what it is told."""

    def __init__(self, **props):
        self.pause = False
        self.core_idle = False
        self.idle_active = False
        self.eof_reached = False
        self.time_pos = 12.5
        self.duration = 100.0
        self.percent_pos = 12.5
        self.frame_drop_count = 0
        self.vo_delayed_frame_count = 0
        self.osd_dimensions = {"w": 1920, "h": 1080}
        self.video_params = {"dw": 1280, "dh": 720}
        self.track_list = []
        self.aid = self.sid = 1
        self.mute = False
        self.__dict__.update(props)
        self.sent = []

    def command(self, *args):
        self.sent.append(args)

    def sets(self):
        return {a[1]: a[2] for a in self.sent if a[0] == "set"}


def make_player(**props):
    mb._learned.update(start=mb.START_TIER, ceiling=len(mb.TIERS) - 1)
    player = mb._Player()
    player._m, player._loaded = FakeCore(**props), True
    return player


class StateTests(unittest.TestCase):
    def test_state_follows_the_core(self):
        p = make_player()
        self.assertEqual(p.get_state(), mb.State.Playing)
        self.assertTrue(p.is_playing())
        p._m.core_idle = True
        self.assertEqual(p.get_state(), mb.State.Buffering)
        p._m.pause = True
        self.assertEqual(p.get_state(), mb.State.Paused)
        self.assertFalse(p.is_playing())
        p._m.eof_reached = True            # keep-open: the end is a pause on the last frame
        self.assertEqual(p.get_state(), mb.State.Ended)
        p._m.eof_reached, p._m.idle_active = False, True   # could not open the file
        self.assertEqual(p.get_state(), mb.State.Error)

    def test_stopped_before_play_and_after_stop(self):
        p = mb._Player()
        self.assertEqual(p.get_state(), mb.State.Stopped)
        self.assertEqual((p.get_time(), p.get_length(), p.get_position(), p.is_playing()), (0, 0, 0.0, False))
        p = make_player()
        p.stop()
        self.assertEqual(p.get_state(), mb.State.Stopped)

    def test_time_in_milliseconds(self):
        p = make_player()
        self.assertEqual((p.get_time(), p.get_length(), p.get_position()), (12500, 100000, 0.125))
        p.set_time(5000)
        p.set_position(0.5)
        self.assertIn(("seek", 5.0, "absolute+exact"), p._m.sent)
        self.assertIn(("seek", 50.0, "absolute-percent+exact"), p._m.sent)

    def test_calls_after_release_are_harmless(self):
        p = make_player()
        p._m.terminate = lambda: None
        p.release()
        p.release()
        p.stop()
        self.assertEqual((p.get_state(), p.get_time(), p.audio_get_track()), (mb.State.Stopped, 0, -1))
        p.set_media(mb._Media("/x.mkv"))
        self.assertEqual(p.play(), -1)   # a released player must not open a new core


class TrackTests(unittest.TestCase):
    TRACKS = [
        {"type": "video", "id": 1},
        {"type": "audio", "id": 1, "lang": "eng"},
        {"type": "audio", "id": 2, "lang": "por", "title": "Dublado"},
        {"type": "sub", "id": 1, "lang": "eng", "forced": True},
        {"type": "sub", "id": 2, "lang": "por"},
    ]

    def test_descriptions_have_vlc_shape(self):
        p = make_player(track_list=self.TRACKS)
        audio = p.audio_get_track_description()
        self.assertEqual(audio[0], (-1, b"Disable"))
        self.assertEqual([i for i, _n in audio], [-1, 1, 2])
        self.assertEqual(p.video_get_spu_description()[1][1], b"Track 1 - [eng] Forced")

    def test_languages_resolve_through_tracks_py(self):
        p = make_player(track_list=self.TRACKS)
        self.assertEqual(choose_track(p.audio_get_track_description(), "", "pt"), (2, True))
        self.assertEqual(choose_track(p.video_get_spu_description(), "", "forced", "en"), (1, True))
        self.assertEqual(choose_track(p.video_get_spu_description(), "", "off"), (-1, True))

    def test_current_and_choose(self):
        p = make_player(aid=2, sid=False)   # mpv reports "no subtitles" as False
        self.assertEqual((p.audio_get_track(), p.video_get_spu()), (2, -1))
        p._m.aid = "auto"
        self.assertEqual(p.audio_get_track(), -1)
        p.video_set_spu(-1)
        p.audio_set_track(2)
        self.assertEqual(p._m.sets(), {"sid": "no", "aid": "2"})


class SettingsTests(unittest.TestCase):
    def test_picture_adjustments_are_converted(self):
        p = make_player()
        opt = mb.VideoAdjustOption
        p.video_set_adjust_int(opt.Enable, 1)
        p.video_set_adjust_float(opt.Brightness, 1.0)
        p.video_set_adjust_float(opt.Contrast, 1.5)
        p.video_set_adjust_float(opt.Saturation, 3.0)   # VLC goes to 300%, mpv stops at +100
        p.video_set_adjust_float(opt.Contrast, 0.0)
        self.assertEqual(p._m.sets(), {"brightness": "0", "contrast": "-100", "saturation": "100"})

    def test_settings_made_before_the_core_exists_are_kept(self):
        mb._learned.update(start=mb.START_TIER, ceiling=len(mb.TIERS) - 1)
        p = mb._Player()                       # the page sets volume and picture before the first play()
        p.audio_set_volume(70)
        p.set_rate(1.5)
        p.video_set_spu_delay(250_000)
        fake = FakeCore()
        with mock.patch.object(mb, "_new_core", return_value=fake):
            p.set_media(mb._Media("/m/a.mkv"))
            p.set_xwindow(1234)
            self.assertEqual(p.play(), 0)
        self.assertEqual(fake.sets()["volume"], "70")
        self.assertEqual(fake.sets()["speed"], "1.5")
        self.assertEqual(fake.sets()["sub-delay"], "0.25")
        self.assertIn(("loadfile", "/m/a.mkv", "replace"), fake.sent)

    def test_sharpness_option_becomes_mpv_sharpen(self):
        p = make_player()
        media = mb._Media("/m/a.mkv")
        media.add_option(":video-filter=sharpen")
        media.add_option(":sharpen-sigma=1.10")
        p.set_media(media)
        self.assertEqual(p._m.sets()["sharpen"], "0.5")
        p.set_media(mb._Media("/m/a.mkv"))
        self.assertEqual(p._m.sets()["sharpen"], "0")

    def test_subtitle_uri_becomes_a_path(self):
        p = make_player()
        p.add_slave(mb.MediaSlaveType.subtitle, Path("/m/My Movie.srt").as_uri(), True)
        self.assertIn(("sub-add", "/m/My Movie.srt", "select"), p._m.sent)


class AdaptiveUpscalingTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        patcher = mock.patch.object(mb.time, "monotonic", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def step(self, p, seconds=mb.ADAPT_EVERY, late=0):
        self.now += seconds
        p._m.frame_drop_count += late
        p.get_state()

    def test_starts_cheap_and_applies_the_tier(self):
        p = make_player()
        p._apply_tier()
        self.assertEqual(p._tier, mb.START_TIER)
        self.assertEqual(p._m.sets()["scale"], mb.TIERS[mb.START_TIER][0])

    def test_climbs_while_playback_is_clean(self):
        p = make_player()
        for _ in range(int(mb.CLIMB_AFTER * 3 / mb.ADAPT_EVERY) + 4):
            self.step(p)
        self.assertEqual(p._tier, len(mb.TIERS) - 1)   # reached the best tier and stays there
        self.assertEqual(mb._learned["start"], len(mb.TIERS) - 1)

    def test_drops_a_tier_and_never_retries_it(self):
        p = make_player()
        self.step(p)                                   # baseline sample
        self.step(p, late=mb.DROP_LIMIT)
        self.assertEqual(p._tier, mb.START_TIER - 1)
        self.assertEqual(mb._learned["ceiling"], mb.START_TIER - 1)
        for _ in range(int(mb.CLIMB_AFTER * 3 / mb.ADAPT_EVERY)):   # a long clean stretch does not climb again
            self.step(p)
        self.assertEqual(p._tier, mb.START_TIER - 1)
        self.assertEqual(mb._learned["start"], mb.START_TIER - 1)   # the next movie starts there

    def test_never_goes_below_the_lightest_tier(self):
        p = make_player()
        for _ in range(8):
            self.step(p, late=50)
        self.assertEqual(p._tier, 0)

    def test_ignores_everything_when_nothing_is_being_enlarged(self):
        p = make_player(osd_dimensions={"w": 1280, "h": 720})   # video already fills the picture
        for _ in range(6):
            self.step(p, late=50)
        self.assertEqual(p._tier, mb.START_TIER)

    def test_ignores_paused_and_seeking(self):
        p = make_player()
        self.step(p)
        p._m.pause = True
        self.step(p, late=50)
        p._m.pause, p._m.core_idle = False, True           # buffering after a seek
        self.step(p, late=50)
        p._m.core_idle = False
        self.step(p)                                        # first sample after: only a new baseline
        self.assertEqual(p._tier, mb.START_TIER)

    def test_state_polling_between_samples_does_nothing(self):
        p = make_player()
        self.step(p)
        before = list(p._m.sent)
        for _ in range(10):
            p.get_state()
        self.assertEqual(p._m.sent, before)


class ProfileTests(unittest.TestCase):
    """Settings > Upscaling: Economy, Balanced (\"auto\") and High quality limit or pre-set the tier."""

    def setUp(self):
        self.now = 1000.0
        patcher = mock.patch.object(mb.time, "monotonic", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, mb, "_profile", mb._profile)

    def player(self, profile):
        mb._learned.update(start=mb.START_TIER, ceiling=len(mb.TIERS) - 1)
        p = mb._Player(profile=profile)
        p._m, p._loaded = FakeCore(), True
        return p

    def clean_seconds(self, p, seconds):
        for _ in range(int(seconds / mb.ADAPT_EVERY) + 1):
            self.now += mb.ADAPT_EVERY
            p.get_state()

    def test_economy_never_leaves_the_light_scaler(self):
        p = self.player("economy")
        self.clean_seconds(p, mb.CLIMB_AFTER * 6)
        self.assertEqual(p._tier, 1)
        self.assertEqual(mb.TIERS[p._tier][0], "spline36")

    def test_balanced_is_the_original_behaviour(self):
        p = self.player("auto")
        self.assertEqual(p._tier, mb.START_TIER)
        self.clean_seconds(p, mb.CLIMB_AFTER * 6)
        self.assertEqual(p._tier, len(mb.TIERS) - 1)

    def test_high_starts_on_the_best_tier_without_changing_where_others_start(self):
        p = self.player("high")
        p._apply_tier()
        self.assertEqual(p._tier, len(mb.TIERS) - 1)
        self.assertEqual(p._m.sets()["scale"], mb.TIERS[-1][0])
        self.assertEqual(mb._learned["start"], mb.START_TIER)

    def test_high_still_steps_back_and_remembers_the_ceiling(self):
        p = self.player("high")
        self.now += mb.ADAPT_EVERY
        p.get_state()                                   # baseline sample
        self.now += mb.ADAPT_EVERY
        p._m.frame_drop_count += mb.DROP_LIMIT
        p.get_state()
        self.assertEqual(p._tier, len(mb.TIERS) - 2)
        self.assertEqual(mb._learned["ceiling"], len(mb.TIERS) - 2)

    def test_what_the_gpu_learned_limits_any_profile(self):
        mb._learned.update(start=0, ceiling=0)
        p = mb._Player(profile="high")
        self.assertEqual(p._tier, 0)

    def test_set_profile_reaches_the_players_and_ignores_unknown_names(self):
        mb.set_profile("economy")
        self.assertEqual(mb._Engine().media_player_new()._max_tier, 1)
        mb.set_profile("whatever")
        self.assertEqual(mb._profile, "auto")
        mb.set_profile("off")                           # handled by the page (it does not use libmpv at all)
        self.assertEqual(mb._profile, "auto")


class DiagnosticsLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "player.log"

    def sample(self, env):
        with mock.patch.dict(mb.os.environ, env, clear=False):
            p = make_player(mpv_version="mpv 0.37.0", current_vo="gpu", hwdec_current="vaapi")
            p._counted = 0
            p._adapt()
        return p

    def test_nothing_is_written_when_the_variable_is_not_set(self):
        with mock.patch.dict(mb.os.environ):
            mb.os.environ.pop(mb.DIAG_ENV, None)
            make_player()._log_diagnostics(0)
        self.assertFalse(self.log.exists())

    def test_one_line_with_the_renderer_decoder_and_counters(self):
        self.sample({mb.DIAG_ENV: str(self.log)})
        line = self.log.read_text(encoding="utf-8").strip()
        for part in ("mpv=mpv-0.37.0", "vo=gpu", "hwdec=vaapi", "tier=1:spline36", "video=1280x720",
                     "window=1920x1080", "late_in_sample=0", "dropped=0"):
            self.assertIn(part, line)

    def test_an_unwritable_log_does_not_disturb_playback(self):
        p = self.sample({mb.DIAG_ENV: str(Path(self.tmp.name) / "missing-folder" / "player.log")})
        self.assertEqual(p.get_state(), mb.State.Playing)


class WindowsDllLookupTests(unittest.TestCase):
    """_use_bundled_mpv() with a pretend Windows: where it looks for the DLL and what it changes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Path(self.tmp.name) / "app"
        (self.app / "cinelocal").mkdir(parents=True)
        self.added = []
        for patcher in (mock.patch.object(mb.sys, "platform", "win32"),
                        mock.patch.object(mb.os, "add_dll_directory", self.added.append, create=True),
                        mock.patch.object(mb, "__file__", str(self.app / "cinelocal" / "mpvbackend.py")),
                        mock.patch.dict(mb.os.environ, {"PATH": "/usr/bin"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_dll_downloaded_next_to_the_app(self):
        (self.app / "libmpv").mkdir()
        (self.app / "libmpv" / "libmpv-2.dll").write_bytes(b"x")
        mb._use_bundled_mpv()
        self.assertEqual(self.added, [str(self.app / "libmpv")])
        self.assertTrue(mb.os.environ["PATH"].startswith(str(self.app / "libmpv")))

    def test_dll_bundled_in_the_packaged_build(self):
        bundle = Path(self.tmp.name) / "_internal"
        bundle.mkdir()
        (bundle / "libmpv-2.dll").write_bytes(b"x")
        with mock.patch.object(mb.sys, "frozen", True, create=True), \
                mock.patch.object(mb.sys, "_MEIPASS", str(bundle), create=True):
            mb._use_bundled_mpv()
        self.assertEqual(self.added, [str(bundle)])

    def test_no_dll_changes_nothing(self):
        mb._use_bundled_mpv()
        self.assertEqual((self.added, mb.os.environ["PATH"]), ([], "/usr/bin"))

    def test_other_platforms_are_left_alone(self):
        (self.app / "libmpv").mkdir()
        (self.app / "libmpv" / "libmpv-2.dll").write_bytes(b"x")
        with mock.patch.object(mb.sys, "platform", "linux"):
            mb._use_bundled_mpv()
        self.assertEqual(self.added, [])


class LoadTests(unittest.TestCase):
    def setUp(self):
        saved = mb._engine, mb._failed
        self.addCleanup(lambda: (setattr(mb, "_engine", saved[0]), setattr(mb, "_failed", saved[1])))
        mb._engine, mb._failed = None, False

    def test_returns_none_without_python_mpv(self):
        with mock.patch.dict(sys.modules, {"mpv": None}):   # `import mpv` raises ImportError
            self.assertIsNone(mb.load())
        self.assertTrue(mb._failed)
        self.assertIsNone(mb.load())                        # remembered: does not try again

    def test_unavailable_reason_says_why(self):
        with mock.patch.object(mb, "_new_core", side_effect=OSError("Cannot find libmpv in the usual places.\nmore")):
            self.assertEqual(mb.unavailable_reason(), "OSError: Cannot find libmpv in the usual places.")
        mb._engine, mb._failed = None, False
        with mock.patch.object(mb, "_new_core", return_value=FakeCore()) as new_core:
            new_core.return_value.terminate = lambda: None
            self.assertEqual(mb.unavailable_reason(), "")

    def test_returns_none_when_libmpv_rejects_the_options(self):
        with mock.patch.object(mb, "_new_core", side_effect=TypeError("unknown option")):
            self.assertIsNone(mb.load())

    def test_engine_mimics_the_vlc_pair(self):
        with mock.patch.object(mb, "_new_core", return_value=FakeCore()) as new_core:
            new_core.return_value.terminate = lambda: None
            module, instance = mb.load()
        self.assertIs(module, instance)
        self.assertEqual(module.State.Ended, mb.State.Ended)
        self.assertIsInstance(instance.media_player_new(), mb._Player)
        self.assertEqual(instance.media_new("/m/a.mkv").path, "/m/a.mkv")


def libmpv_works() -> bool:
    saved = mb._engine, mb._failed
    mb._engine, mb._failed = None, False
    try:
        return mb.load() is not None
    finally:
        mb._engine, mb._failed = saved


@unittest.skipUnless(shutil.which("ffmpeg") and libmpv_works(), "needs ffmpeg and libmpv")
class RealLibmpvTests(unittest.TestCase):
    def test_plays_a_file_headless(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "t.mkv"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=3",
                            "-f", "lavfi", "-i", "sine=duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-metadata:s:a:0", "language=por", str(video)], check=True)
            p = mb._Player(extra={"vo": "null", "ao": "null"})
            p.set_media(mb._Media(str(video)))
            self.assertEqual(p.play(), 0)
            try:
                deadline = time.time() + 10
                while p.get_state() != mb.State.Playing and time.time() < deadline:
                    time.sleep(0.1)
                self.assertEqual(p.get_state(), mb.State.Playing)
                self.assertTrue(2900 < p.get_length() < 3200)
                self.assertEqual(choose_track(p.audio_get_track_description(), "", "pt"), (1, True))
                p.set_time(2800)
                deadline = time.time() + 10
                while p.get_state() != mb.State.Ended and time.time() < deadline:
                    time.sleep(0.1)
                self.assertEqual(p.get_state(), mb.State.Ended)
            finally:
                p.stop()
                p.release()


if __name__ == "__main__":
    unittest.main()
