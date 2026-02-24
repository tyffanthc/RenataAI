from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_bio_events as bio_events


class F28SaaSignalsFoundPerBodyDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags()
        app_state.current_system = "F28_BIO_DIAG_SYSTEM"

    def tearDown(self) -> None:
        bio_events.reset_bio_flags()

    def test_logs_emit_diagnostics_with_bio_count(self) -> None:
        ev = {
            "event": "SAASignalsFound",
            "StarSystem": "F28_BIO_DIAG_SYSTEM",
            "BodyName": "F28 Planet A 1",
            "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 4}],
        }
        with (
            patch("logic.events.exploration_bio_events.emit_callout_or_summary") as emit_mock,
            patch("logic.events.exploration_bio_events.log_event_throttled") as log_mock,
        ):
            bio_events.handle_dss_bio_signals(ev, gui_ref=None)

        self.assertTrue(emit_mock.called)
        self.assertTrue(log_mock.called)
        # Last diagnostic call should be the emit event with bio_count=4.
        _, _, channel, message = log_mock.call_args.args[:4]
        self.assertEqual(channel, "EXOBIO")
        self.assertEqual(message, "SAASignalsFound diagnostics")
        self.assertEqual(log_mock.call_args.kwargs.get("stage"), "emit")
        self.assertEqual(int(log_mock.call_args.kwargs.get("bio_count") or 0), 4)

    def test_logs_duplicate_body_skip_reason(self) -> None:
        ev = {
            "event": "SAASignalsFound",
            "StarSystem": "F28_BIO_DIAG_SYSTEM",
            "BodyName": "F28 Planet A 1",
            "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 2}],
        }
        with patch("logic.events.exploration_bio_events.emit_callout_or_summary"), patch(
            "logic.events.exploration_bio_events.log_event_throttled"
        ) as log_mock:
            bio_events.handle_dss_bio_signals(ev, gui_ref=None)
            bio_events.handle_dss_bio_signals(ev, gui_ref=None)

        reasons = [str(call.kwargs.get("reason") or "") for call in log_mock.call_args_list]
        self.assertIn("duplicate_body", reasons)


if __name__ == "__main__":
    unittest.main()

