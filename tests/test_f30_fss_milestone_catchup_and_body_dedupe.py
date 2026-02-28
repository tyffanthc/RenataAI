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

    def test_late_bodycount_syncs_milestone_flags_without_retro_callouts(self) -> None:
        # Simulate partial scan progress collected before FSSDiscoveryScan delivered BodyCount.
        fss_events.FSS_TOTAL_BODIES = 0
        fss_events.FSS_DISCOVERED = 4
        fss_events.FSS_SCANNED_BODIES = {"body:1", "body:2", "body:3", "body:4"}
        fss_events.FSS_25_WARNED = False
        fss_events.FSS_50_WARNED = False
        fss_events.FSS_75_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight"),
            patch("logic.events.exploration_fss_events.utils.MSG_QUEUE.put"),
        ):
            fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 7}, gui_ref=None)

        self.assertEqual(int(fss_events.FSS_TOTAL_BODIES or 0), 7)
        # 4/7 ~= 57%, so 25 and 50 should be marked as already crossed.
        self.assertTrue(fss_events.FSS_25_WARNED)
        self.assertTrue(fss_events.FSS_50_WARNED)
        self.assertFalse(fss_events.FSS_75_WARNED)

        # Next threshold check at the same progress should not emit retro 25/50 callouts.
        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
        ):
            fss_events._check_fss_thresholds(gui_ref=None)

        emit_ids = [str(c.kwargs.get("message_id") or "") for c in emit_mock.call_args_list]
        self.assertNotIn("MSG.FSS_PROGRESS_25", emit_ids)
        self.assertNotIn("MSG.FSS_PROGRESS_50", emit_ids)

    def test_late_bodycount_at_n_minus_1_emits_last_planet_callout(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 0
        fss_events.FSS_DISCOVERED = 8
        fss_events.FSS_SCANNED_BODIES = {f"id:{i}" for i in range(1, 9)}
        fss_events.FSS_LAST_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events.utils.MSG_QUEUE.put"),
        ):
            fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 9}, gui_ref=None)

        emit_ids = [str(c.kwargs.get("message_id") or "") for c in emit_mock.call_args_list]
        self.assertIn("MSG.FSS_LAST_BODY", emit_ids)
        self.assertTrue(bool(fss_events.FSS_LAST_WARNED))

    def test_late_bodycount_emits_current_progress_callout(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 0
        fss_events.FSS_DISCOVERED = 5
        fss_events.FSS_SCANNED_BODIES = {f"id:{i}" for i in range(1, 6)}
        fss_events.FSS_25_WARNED = False
        fss_events.FSS_50_WARNED = False
        fss_events.FSS_75_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events.utils.MSG_QUEUE.put"),
        ):
            fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 8}, gui_ref=None)

        emit_ids = [str(c.kwargs.get("message_id") or "") for c in emit_mock.call_args_list]
        self.assertIn("MSG.FSS_PROGRESS_50", emit_ids)
        self.assertNotIn("MSG.FSS_PROGRESS_25", emit_ids)
        self.assertNotIn("MSG.FSS_PROGRESS_75", emit_ids)

    def test_handle_scan_prioritizes_fss_progress_before_first_discovery_callouts(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 4
        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
        ):
            fss_events.handle_scan(
                {
                    "event": "Scan",
                    "StarSystem": "F30_FSS_TEST_SYSTEM",
                    "BodyName": "F30_FSS_TEST_SYSTEM A 1",
                    "BodyID": 1,
                    "ScanType": "Detailed",
                    "WasDiscovered": False,
                },
                gui_ref=None,
            )

        emitted = [str(c.kwargs.get("message_id") or "") for c in emit_mock.call_args_list]
        self.assertIn("MSG.FSS_PROGRESS_25", emitted)
        self.assertIn("MSG.FIRST_DISCOVERY", emitted)
        self.assertLess(emitted.index("MSG.FSS_PROGRESS_25"), emitted.index("MSG.FIRST_DISCOVERY"))


if __name__ == "__main__":
    unittest.main()
