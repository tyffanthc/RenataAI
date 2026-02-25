from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_fss_events as fss_events


class F30ExplorationSummaryAfterJumpFssGateTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()
        app_state.current_system = "F30_SUMMARY_GATE_SYS"

    def test_full_scan_arms_summary_but_does_not_emit_immediately(self) -> None:
        fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN = True
        fss_events.FSS_TOTAL_BODIES = 6
        fss_events.FSS_DISCOVERED = 6

        with patch("logic.events.exploration_summary.trigger_exploration_summary") as trigger_mock:
            fss_events._wire_exit_summary_to_runtime(gui_ref=None)

        self.assertFalse(trigger_mock.called)
        self.assertTrue(fss_events.FSS_PENDING_EXIT_SUMMARY)
        self.assertEqual(fss_events.FSS_PENDING_EXIT_SUMMARY_SYSTEM, "F30_SUMMARY_GATE_SYS")
        self.assertEqual(fss_events.FSS_PENDING_EXIT_SUMMARY_SCANNED, 6)
        self.assertEqual(fss_events.FSS_PENDING_EXIT_SUMMARY_TOTAL, 6)

    def test_flush_pending_summary_on_jump_emits_once(self) -> None:
        fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN = True
        fss_events.FSS_TOTAL_BODIES = 4
        fss_events.FSS_DISCOVERED = 4
        fss_events._wire_exit_summary_to_runtime(gui_ref=None)

        with patch("logic.events.exploration_summary.trigger_exploration_summary", return_value=True) as trigger_mock:
            ok = fss_events.flush_pending_exit_summary_on_jump(gui_ref=None)

        self.assertTrue(ok)
        self.assertTrue(trigger_mock.called)
        kwargs = dict(trigger_mock.call_args.kwargs or {})
        self.assertEqual(kwargs.get("mode"), "auto")
        self.assertEqual(kwargs.get("system_name"), "F30_SUMMARY_GATE_SYS")
        self.assertEqual(kwargs.get("scanned_bodies"), 4)
        self.assertEqual(kwargs.get("total_bodies"), 4)
        self.assertFalse(bool(fss_events.FSS_PENDING_EXIT_SUMMARY))

    def test_no_manual_fss_progress_means_no_pending_summary(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 3
        fss_events.FSS_DISCOVERED = 3

        with patch("logic.events.exploration_summary.trigger_exploration_summary") as trigger_mock:
            fss_events._wire_exit_summary_to_runtime(gui_ref=None)

        self.assertFalse(trigger_mock.called)
        self.assertFalse(bool(fss_events.FSS_PENDING_EXIT_SUMMARY))

    def test_discovery_scan_without_manual_progress_still_does_not_arm_summary(self) -> None:
        fss_events.FSS_HAD_DISCOVERY_SCAN = True
        fss_events.FSS_TOTAL_BODIES = 5
        fss_events.FSS_DISCOVERED = 5

        with patch("logic.events.exploration_summary.trigger_exploration_summary") as trigger_mock:
            fss_events._wire_exit_summary_to_runtime(gui_ref=None)

        self.assertFalse(trigger_mock.called)
        self.assertFalse(bool(fss_events.FSS_PENDING_EXIT_SUMMARY))


if __name__ == "__main__":
    unittest.main()
