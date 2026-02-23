from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_fss_events as fss_events


class F24FssAllBodiesFoundDoesNotForceFullScanTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()
        app_state.current_system = "F24_FSS_ALL_FOUND_SYSTEM"

    def tearDown(self) -> None:
        fss_events.reset_fss_progress()

    def test_all_bodies_found_does_not_promote_scan_counter_to_full(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 19
        fss_events.FSS_DISCOVERED = 17
        fss_events.FSS_FULL_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events._wire_exit_summary_to_runtime") as summary_mock,
        ):
            fss_events.handle_fss_all_bodies_found({"event": "FSSAllBodiesFound"}, gui_ref=None)

        self.assertEqual(fss_events.FSS_DISCOVERED, 17)
        self.assertFalse(bool(fss_events.FSS_FULL_WARNED))
        self.assertFalse(summary_mock.called)
        # No full-scan callout should be emitted by FSSAllBodiesFound in partial Scan progress.
        self.assertEqual(emit_mock.call_count, 0)

    def test_all_bodies_found_keeps_full_behavior_when_scan_counter_is_already_full(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 5
        fss_events.FSS_DISCOVERED = 5
        fss_events.FSS_FULL_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events._wire_exit_summary_to_runtime") as summary_mock,
        ):
            fss_events.handle_fss_all_bodies_found({"event": "FSSAllBodiesFound"}, gui_ref=None)

        self.assertTrue(summary_mock.called)
        message_ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertIn("MSG.SYSTEM_FULLY_SCANNED", message_ids)


if __name__ == "__main__":
    unittest.main()
