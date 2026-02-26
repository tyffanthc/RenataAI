from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from logic.event_handler import EventHandler


class F32EventHandlerFssRouterExceptionIsolationTests(unittest.TestCase):
    def test_scan_event_fss_exception_isolated_and_dss_hint_still_runs(self) -> None:
        handler = EventHandler()
        line = json.dumps({"event": "Scan", "BodyName": "F32 A 1", "BodyID": 1})

        with (
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
            patch("logic.event_handler.MSG_QUEUE.put"),
            patch("app.state.app_state.update_mode_signal_from_journal"),
            patch("logic.event_handler.high_g_warning.handle_journal_event"),
            patch("logic.event_handler.survival_rebuy_awareness.handle_journal_event"),
            patch("logic.event_handler.combat_awareness.handle_journal_event"),
            patch("app.state.app_state.system_value_engine.analyze_scan_event"),
            patch(
                "logic.event_handler.exploration_fss_events.handle_scan",
                side_effect=RuntimeError("fss boom"),
            ),
            patch("logic.event_handler.exploration_dss_events.handle_dss_target_hint") as dss_hint_mock,
            patch("logic.event_handler._log_router_fallback") as router_log_mock,
        ):
            handler.handle_event(line, gui_ref=None)

        dss_hint_mock.assert_called_once()
        self.assertTrue(router_log_mock.called, "router should log local handler failure")
        first_call_args = router_log_mock.call_args_list[0][0]
        self.assertEqual(str(first_call_args[0]), "scan.fss")

    def test_fss_discovery_scan_exception_does_not_escape_event_handler(self) -> None:
        handler = EventHandler()
        line = json.dumps({"event": "FSSDiscoveryScan", "BodyCount": 6})

        with (
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
            patch("logic.event_handler.MSG_QUEUE.put"),
            patch("app.state.app_state.update_mode_signal_from_journal"),
            patch("logic.event_handler.high_g_warning.handle_journal_event"),
            patch("logic.event_handler.survival_rebuy_awareness.handle_journal_event"),
            patch("logic.event_handler.combat_awareness.handle_journal_event"),
            patch(
                "logic.event_handler.exploration_fss_events.handle_fss_discovery_scan",
                side_effect=RuntimeError("fss discovery boom"),
            ),
            patch("logic.event_handler._log_router_fallback") as router_log_mock,
        ):
            handler.handle_event(line, gui_ref=None)

        self.assertTrue(router_log_mock.called)
        first_call_args = router_log_mock.call_args_list[0][0]
        self.assertEqual(str(first_call_args[0]), "journal.fss_discovery_scan")


if __name__ == "__main__":
    unittest.main()

