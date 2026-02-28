from __future__ import annotations

import queue
import unittest
from unittest.mock import patch

from app.state import app_state
from logic.utils import notify as notify_module


class F61TtsStaleSystemQueueDropTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_active = bool(getattr(notify_module, "_TTS_THREAD_ACTIVE", False))
        self._saved_queue = getattr(notify_module, "_TTS_SPEECH_QUEUE", None)
        self._saved_system = app_state.get_current_system_name()
        notify_module._TTS_THREAD_ACTIVE = True
        notify_module._TTS_SPEECH_QUEUE = queue.Queue()

    def tearDown(self) -> None:
        notify_module._TTS_THREAD_ACTIVE = self._saved_active
        if self._saved_queue is not None:
            notify_module._TTS_SPEECH_QUEUE = self._saved_queue
        app_state.set_system(self._saved_system)

    def test_drops_stale_system_scoped_fss_queue_item_after_system_change(self) -> None:
        app_state.set_system("SYS B")
        notify_module._TTS_SPEECH_QUEUE.put(
            {
                "text": "stale fss",
                "message_id": "MSG.FSS_LAST_BODY",
                "context_system": "SYS A",
            }
        )

        with patch("logic.utils.notify._speak_tts") as speak_mock:
            notify_module._tts_worker_loop()

        speak_mock.assert_not_called()

    def test_keeps_non_system_scoped_queue_item_even_when_system_differs(self) -> None:
        app_state.set_system("SYS B")
        notify_module._TTS_SPEECH_QUEUE.put(
            {
                "text": "route info",
                "message_id": "MSG.ROUTE_FOUND",
                "context_system": "SYS A",
            }
        )

        with patch("logic.utils.notify._speak_tts") as speak_mock:
            notify_module._tts_worker_loop()

        speak_mock.assert_called_once_with("route info")

    def test_keeps_system_scoped_queue_item_when_system_matches(self) -> None:
        app_state.set_system("SYS A")
        notify_module._TTS_SPEECH_QUEUE.put(
            {
                "text": "fresh fss",
                "message_id": "MSG.SYSTEM_FULLY_SCANNED",
                "context_system": "SYS A",
            }
        )

        with patch("logic.utils.notify._speak_tts") as speak_mock:
            notify_module._tts_worker_loop()

        speak_mock.assert_called_once_with("fresh fss")


if __name__ == "__main__":
    unittest.main()
