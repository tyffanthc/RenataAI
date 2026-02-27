from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from logic.tts import piper_tts


class F48PiperWinsoundPlaybackTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_hung_worker = getattr(piper_tts, "_WINSOUND_HUNG_WORKER", None)
        with piper_tts._WINSOUND_PLAYBACK_GUARD_LOCK:
            piper_tts._WINSOUND_HUNG_WORKER = None

    def tearDown(self) -> None:
        with piper_tts._WINSOUND_PLAYBACK_GUARD_LOCK:
            piper_tts._WINSOUND_HUNG_WORKER = self._saved_hung_worker

    def test_play_wav_with_timeout_returns_false_and_purges_when_playback_hangs(self) -> None:
        released = threading.Event()
        calls: list[tuple[object, int]] = []

        def _play_sound(path, flags: int) -> None:
            calls.append((path, int(flags)))
            if path is None:
                released.set()
                return
            released.wait(timeout=1.0)

        fake_winsound = types.SimpleNamespace(
            PlaySound=_play_sound,
            SND_FILENAME=1,
            SND_PURGE=2,
        )

        with (
            patch.dict(sys.modules, {"winsound": fake_winsound}),
            patch("logic.tts.piper_tts.log_event_throttled") as throttled_log,
        ):
            t0 = time.monotonic()
            ok = piper_tts._play_wav_with_timeout("C:/fake/test.wav", timeout_sec=0.05)
            elapsed = time.monotonic() - t0

        self.assertFalse(ok)
        self.assertLess(elapsed, 0.5, "winsound timeout helper should return quickly on hung playback")
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0], ("C:/fake/test.wav", 1))
        self.assertEqual(calls[1], (None, 2))
        self.assertTrue(
            any(call.args[:4] == ("piper_winsound_playback_timeout", 15.0, "WARN", "piper: winsound playback timeout")
                for call in throttled_log.call_args_list),
            "Expected throttled log for winsound playback timeout",
        )

    def test_play_wav_with_timeout_skips_new_playback_while_previous_hung_worker_is_alive(self) -> None:
        release = threading.Event()
        calls: list[tuple[object, int]] = []

        def _play_sound(path, flags: int) -> None:
            calls.append((path, int(flags)))
            if path is None:
                return
            release.wait(timeout=1.0)

        fake_winsound = types.SimpleNamespace(
            PlaySound=_play_sound,
            SND_FILENAME=1,
            SND_PURGE=2,
        )

        with (
            patch.dict(sys.modules, {"winsound": fake_winsound}),
            patch("logic.tts.piper_tts.log_event_throttled") as throttled_log,
        ):
            first = piper_tts._play_wav_with_timeout("C:/fake/one.wav", timeout_sec=0.05)
            second = piper_tts._play_wav_with_timeout("C:/fake/two.wav", timeout_sec=0.05)

        self.assertFalse(first)
        self.assertFalse(second)
        filename_calls = [call for call in calls if call[1] == 1]
        self.assertEqual(len(filename_calls), 1, "Expected second playback to be skipped while first worker hangs.")
        self.assertEqual(filename_calls[0][0], "C:/fake/one.wav")
        self.assertTrue(
            any(
                call.args[:4]
                == (
                    "piper_winsound_playback_still_hung",
                    15.0,
                    "WARN",
                    "piper: skipping playback while previous winsound worker is still hung",
                )
                for call in throttled_log.call_args_list
            ),
            "Expected throttled guard log for repeated playback while worker remains hung.",
        )
        release.set()


if __name__ == "__main__":
    unittest.main()
