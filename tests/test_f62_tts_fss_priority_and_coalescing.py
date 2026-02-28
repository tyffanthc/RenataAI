from __future__ import annotations

import queue
import unittest

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


if __name__ == "__main__":
    unittest.main()
