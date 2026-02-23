from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_fss_events as fss_events


class F24ExplorationFssFullScanTextFixTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()
        app_state.current_system = "F24_TEXT_FIX_SYSTEM"
        fss_events.FSS_TOTAL_BODIES = 3
        fss_events.FSS_DISCOVERED = 3
        fss_events.FSS_FULL_WARNED = False

    def test_full_scan_emit_uses_correct_polish_text(self) -> None:
        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events._wire_exit_summary_to_runtime") as summary_mock,
        ):
            ok = fss_events._maybe_speak_fss_full(gui_ref=None)

        self.assertTrue(ok)
        self.assertTrue(summary_mock.called)
        self.assertEqual(emit_mock.call_count, 1)
        self.assertEqual(emit_mock.call_args.args[0], "System w pełni przeskanowany.")
        self.assertEqual(emit_mock.call_args.kwargs.get("message_id"), "MSG.SYSTEM_FULLY_SCANNED")


if __name__ == "__main__":
    unittest.main()
