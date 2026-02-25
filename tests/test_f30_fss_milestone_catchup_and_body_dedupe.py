from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_fss_events as fss_events


class F30FssMilestoneCatchupAndBodyDedupeTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()
        app_state.current_system = "F30_FSS_TEST_SYSTEM"

    def tearDown(self) -> None:
        fss_events.reset_fss_progress()

    def test_threshold_catchup_emits_only_highest_reached_milestone(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 6
        fss_events.FSS_DISCOVERED = 4  # 66% -> crosses 25% and 50% at once in catch-up scenario
        fss_events.FSS_25_WARNED = False
        fss_events.FSS_50_WARNED = False
        fss_events.FSS_75_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
        ):
            fss_events._check_fss_thresholds(gui_ref=None)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertEqual(str(emit_mock.call_args.kwargs.get("message_id") or ""), "MSG.FSS_PROGRESS_50")
        self.assertTrue(fss_events.FSS_25_WARNED)
        self.assertTrue(fss_events.FSS_50_WARNED)
        self.assertFalse(fss_events.FSS_75_WARNED)

    def test_handle_scan_dedupes_same_body_across_bodyid_and_bodyname_payload_variants(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 10

        with (
            patch("logic.events.exploration_fss_events._check_fss_thresholds"),
            patch("logic.events.exploration_fss_events.check_high_value_planet"),
            patch("logic.events.exploration_fss_events._maybe_speak_fss_full"),
            patch("logic.events.exploration_fss_events.emit_insight"),
        ):
            fss_events.handle_scan({"event": "Scan", "BodyName": "F30 A 1", "BodyID": 7}, gui_ref=None)
            fss_events.handle_scan({"event": "Scan", "BodyID": 7}, gui_ref=None)
            fss_events.handle_scan({"event": "Scan", "BodyName": "F30 A 1"}, gui_ref=None)

        self.assertEqual(int(fss_events.FSS_DISCOVERED or 0), 1)


if __name__ == "__main__":
    unittest.main()

