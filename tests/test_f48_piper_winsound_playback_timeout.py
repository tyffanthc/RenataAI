from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from logic.tts import piper_tts


class F48PiperWinsoundPlaybackTimeoutTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
