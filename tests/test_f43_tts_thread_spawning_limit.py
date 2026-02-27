from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


class _FakeThread:
    created = 0
    started = 0

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs
        type(self).created += 1

    def start(self) -> None:
        type(self).started += 1


class F43TtsThreadSpawningLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_active = getattr(notify_module, "_TTS_THREAD_ACTIVE", False)
        self._saved_queue = getattr(notify_module, "_TTS_SPEECH_QUEUE", None)
        notify_module._TTS_THREAD_ACTIVE = False
        notify_module._TTS_SPEECH_QUEUE = notify_module.queue.Queue()
        _FakeThread.created = 0
        _FakeThread.started = 0

    def tearDown(self) -> None:
        notify_module._TTS_THREAD_ACTIVE = self._saved_active
        if self._saved_queue is not None:
            notify_module._TTS_SPEECH_QUEUE = self._saved_queue

    def test_powiedz_limits_tts_to_single_active_worker_and_queues_overlap(self) -> None:
        with (
            patch("logic.utils.notify.config.get", side_effect=lambda key, default=None: True if key == "voice_enabled" else default),
            patch("logic.utils.notify.prepare_tts", return_value="test tts."),
            patch("logic.utils.notify.threading.Thread", _FakeThread),
        ):
            notify_module.powiedz("msg-1", message_id="MSG.ROUTE_FOUND", force=True)
            notify_module.powiedz("msg-2", message_id="MSG.ROUTE_FOUND", force=True)

        self.assertEqual(_FakeThread.created, 1)
        self.assertEqual(_FakeThread.started, 1)
        self.assertTrue(bool(notify_module._TTS_THREAD_ACTIVE))
        self.assertEqual(notify_module._TTS_SPEECH_QUEUE.qsize(), 2)

    def test_watek_mowy_releases_active_slot_even_when_speak_raises(self) -> None:
        notify_module._TTS_THREAD_ACTIVE = True
        with (
            patch("logic.utils.notify._speak_tts", side_effect=RuntimeError("boom")),
            patch("logic.utils.notify._log_notify_soft_failure") as soft_log,
        ):
            notify_module._watek_mowy("test tts.")

        self.assertFalse(bool(notify_module._TTS_THREAD_ACTIVE))
        soft_log.assert_called()


if __name__ == "__main__":
    unittest.main()
