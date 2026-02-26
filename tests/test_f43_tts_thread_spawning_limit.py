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
        notify_module._TTS_THREAD_ACTIVE = False
        _FakeThread.created = 0
        _FakeThread.started = 0

    def tearDown(self) -> None:
        notify_module._TTS_THREAD_ACTIVE = self._saved_active

    def test_powiedz_limits_tts_to_single_active_thread_and_drops_overlap(self) -> None:
        with (
            patch("logic.utils.notify.config.get", side_effect=lambda key, default=None: True if key == "voice_enabled" else default),
            patch("logic.utils.notify.prepare_tts", return_value="test tts."),
            patch("logic.utils.notify.threading.Thread", _FakeThread),
            patch("logic.utils.notify.log_event_throttled") as throttled_log,
        ):
            notify_module.powiedz("msg-1", message_id="MSG.ROUTE_FOUND", force=True)
            notify_module.powiedz("msg-2", message_id="MSG.ROUTE_FOUND", force=True)

        self.assertEqual(_FakeThread.created, 1)
        self.assertEqual(_FakeThread.started, 1)
        self.assertTrue(bool(notify_module._TTS_THREAD_ACTIVE))
        self.assertTrue(
            any(
                call.args[:4]
                == (
                    "tts:thread_busy_drop",
                    5000,
                    "TTS",
                    "skip starting new TTS thread while previous speech is active",
                )
                for call in throttled_log.call_args_list
            ),
            "Expected throttled drop log when second TTS thread start is blocked.",
        )

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
