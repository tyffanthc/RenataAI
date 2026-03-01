from __future__ import annotations

import queue
import time
import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


def _drain_message_ids(q: queue.Queue) -> list[str]:
    out: list[str] = []
    while not q.empty():
        item = q.get_nowait()
        if isinstance(item, dict):
            out.append(str(item.get("message_id") or ""))
        else:
            out.append("")
    return out


class F62TtsFssPriorityAndCoalescingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_active = bool(getattr(notify_module, "_TTS_THREAD_ACTIVE", False))
        self._saved_queue = getattr(notify_module, "_TTS_SPEECH_QUEUE", None)
        notify_module._TTS_THREAD_ACTIVE = True
        notify_module._TTS_SPEECH_QUEUE = queue.Queue()

    def tearDown(self) -> None:
        notify_module._TTS_THREAD_ACTIVE = self._saved_active
        if self._saved_queue is not None:
            notify_module._TTS_SPEECH_QUEUE = self._saved_queue

    def test_fss_priority_item_moves_ahead_of_normal_pending_items(self) -> None:
        notify_module._start_tts_thread("route", message_id="MSG.ROUTE_FOUND", context={"system": "SYS A"})
        notify_module._start_tts_thread("fss", message_id="MSG.FSS_PROGRESS_25", context={"system": "SYS A"})

        order = _drain_message_ids(notify_module._TTS_SPEECH_QUEUE)
        self.assertEqual(order, ["MSG.FSS_PROGRESS_25", "MSG.ROUTE_FOUND"])

    def test_fss_coalescing_keeps_only_highest_pending_milestone_for_same_system(self) -> None:
        notify_module._start_tts_thread("p25", message_id="MSG.FSS_PROGRESS_25", context={"system": "SYS A"})
        notify_module._start_tts_thread("p50", message_id="MSG.FSS_PROGRESS_50", context={"system": "SYS A"})
        notify_module._start_tts_thread("p75", message_id="MSG.FSS_PROGRESS_75", context={"system": "SYS A"})

        order = _drain_message_ids(notify_module._TTS_SPEECH_QUEUE)
        self.assertEqual(order, ["MSG.FSS_PROGRESS_75"])

    def test_fss_coalescing_ignores_lower_pending_milestone_when_higher_exists(self) -> None:
        notify_module._start_tts_thread("p75", message_id="MSG.FSS_PROGRESS_75", context={"system": "SYS A"})
        notify_module._start_tts_thread("p50", message_id="MSG.FSS_PROGRESS_50", context={"system": "SYS A"})

        order = _drain_message_ids(notify_module._TTS_SPEECH_QUEUE)
        self.assertEqual(order, ["MSG.FSS_PROGRESS_75"])

    def test_fss_coalescing_isolated_per_system(self) -> None:
        notify_module._start_tts_thread("a75", message_id="MSG.FSS_PROGRESS_75", context={"system": "SYS A"})
        notify_module._start_tts_thread("b50", message_id="MSG.FSS_PROGRESS_50", context={"system": "SYS B"})

        order = _drain_message_ids(notify_module._TTS_SPEECH_QUEUE)
        self.assertEqual(order, ["MSG.FSS_PROGRESS_75", "MSG.FSS_PROGRESS_50"])

    def test_worker_drops_tts_item_when_queue_ttl_expired(self) -> None:
        notify_module._TTS_SPEECH_QUEUE.put(
            {
                "text": "stale milestone",
                "message_id": "MSG.FSS_PROGRESS_25",
                "context_system": "SYS A",
                "enqueued_monotonic": float(time.monotonic() - 30.0),
                "max_queue_age_sec": 20.0,
            }
        )
        with patch("logic.utils.notify._speak_tts") as speak_mock:
            notify_module._tts_worker_loop()
        speak_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
