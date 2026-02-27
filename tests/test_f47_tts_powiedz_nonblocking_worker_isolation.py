from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


class F47TtsPowiedzNonBlockingWorkerIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_active = bool(getattr(notify_module, "_TTS_THREAD_ACTIVE", False))
        self._saved_queue = getattr(notify_module, "_TTS_SPEECH_QUEUE", None)
        notify_module._TTS_THREAD_ACTIVE = False
        notify_module._TTS_SPEECH_QUEUE = notify_module.queue.Queue()

    def tearDown(self) -> None:
        # Best effort cleanup in case a test fails before releasing the worker.
        deadline = time.monotonic() + 1.0
        while bool(getattr(notify_module, "_TTS_THREAD_ACTIVE", False)) and time.monotonic() < deadline:
            time.sleep(0.01)
        notify_module._TTS_THREAD_ACTIVE = self._saved_active
        if self._saved_queue is not None:
            notify_module._TTS_SPEECH_QUEUE = self._saved_queue

    def test_powiedz_returns_while_tts_worker_is_blocked(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def _blocking_speak(_text: str) -> None:
            started.set()
            release.wait(timeout=2.0)

        with (
            patch(
                "logic.utils.notify.config.get",
                side_effect=lambda key, default=None: True if key == "voice_enabled" else default,
            ),
            patch("logic.utils.notify.prepare_tts", return_value="test tts."),
            patch("logic.utils.notify._speak_tts", side_effect=_blocking_speak),
            patch("builtins.print"),
        ):
            t0 = time.monotonic()
            notify_module.powiedz("msg", message_id="MSG.ROUTE_FOUND", force=True)
            elapsed = time.monotonic() - t0

            self.assertTrue(started.wait(timeout=1.0), "Expected TTS worker thread to start.")
            self.assertLess(elapsed, 0.25, "powiedz() should not block on TTS worker playback.")
            self.assertTrue(bool(notify_module._TTS_THREAD_ACTIVE), "TTS slot should remain active while worker runs.")

            release.set()

            deadline = time.monotonic() + 1.0
            while bool(notify_module._TTS_THREAD_ACTIVE) and time.monotonic() < deadline:
                time.sleep(0.01)

        self.assertFalse(bool(notify_module._TTS_THREAD_ACTIVE), "TTS slot should be released after worker exit.")


if __name__ == "__main__":
    unittest.main()
