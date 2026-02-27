from __future__ import annotations

import queue
import threading
import time
import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


class F51TtsFifoWorkerQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_active = bool(getattr(notify_module, "_TTS_THREAD_ACTIVE", False))
        self._saved_queue = getattr(notify_module, "_TTS_SPEECH_QUEUE", None)
        notify_module._TTS_THREAD_ACTIVE = False
        notify_module._TTS_SPEECH_QUEUE = queue.Queue()

    def tearDown(self) -> None:
        deadline = time.monotonic() + 2.0
        while bool(getattr(notify_module, "_TTS_THREAD_ACTIVE", False)) and time.monotonic() < deadline:
            time.sleep(0.01)
        notify_module._TTS_THREAD_ACTIVE = self._saved_active
        if self._saved_queue is not None:
            notify_module._TTS_SPEECH_QUEUE = self._saved_queue

    def test_powiedz_queues_messages_in_fifo_order_without_drop(self) -> None:
        spoken: list[str] = []
        release = threading.Event()

        def _fake_speak(text: str) -> None:
            spoken.append(text)
            if len(spoken) == 1:
                release.wait(timeout=1.0)

        with (
            patch(
                "logic.utils.notify.config.get",
                side_effect=lambda key, default=None: True if key == "voice_enabled" else default,
            ),
            patch("logic.utils.notify.prepare_tts", side_effect=["tts-1", "tts-2", "tts-3"]),
            patch("logic.utils.notify._speak_tts", side_effect=_fake_speak),
            patch("builtins.print"),
        ):
            notify_module.powiedz("m1", message_id="MSG.ROUTE_FOUND", force=True)
            notify_module.powiedz("m2", message_id="MSG.ROUTE_FOUND", force=True)
            notify_module.powiedz("m3", message_id="MSG.ROUTE_FOUND", force=True)
            self.assertTrue(bool(notify_module._TTS_THREAD_ACTIVE))
            release.set()
            deadline = time.monotonic() + 2.0
            while bool(notify_module._TTS_THREAD_ACTIVE) and time.monotonic() < deadline:
                time.sleep(0.01)

        self.assertFalse(bool(notify_module._TTS_THREAD_ACTIVE))
        self.assertEqual(spoken, ["tts-1", "tts-2", "tts-3"])


if __name__ == "__main__":
    unittest.main()
