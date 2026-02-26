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

    def test_all_bodies_found_does_not_promote_scan_counter_to_full_at_17_of_18(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 18
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
        self.assertEqual(emit_mock.call_count, 0)

    def test_alias_duplicate_does_not_turn_18_of_19_into_false_full_scan(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 19
        fss_events.FSS_DISCOVERED = 0
        fss_events.FSS_SCANNED_BODIES = set()
        fss_events.FSS_FULL_WARNED = False

        with (
            patch("logic.events.exploration_fss_events._check_fss_thresholds"),
            patch("logic.events.exploration_fss_events.check_high_value_planet"),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events._wire_exit_summary_to_runtime") as summary_mock,
        ):
            for idx in range(1, 19):
                fss_events.handle_scan(
                    {"event": "Scan", "BodyName": f"F24 BODY {idx}", "BodyID": idx},
                    gui_ref=None,
                )

            # Same body as above, alternate payload form (id-only) should be deduped.
            fss_events.handle_scan({"event": "Scan", "BodyID": 18}, gui_ref=None)

        self.assertEqual(int(fss_events.FSS_DISCOVERED or 0), 18)
        self.assertFalse(bool(fss_events.FSS_FULL_WARNED))
        self.assertFalse(summary_mock.called)
        message_ids = [str(call.kwargs.get("message_id") or "") for call in emit_mock.call_args_list]
        self.assertNotIn("MSG.SYSTEM_FULLY_SCANNED", message_ids)

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
