from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.event_insight_mapping import resolve_emit_contract
from logic.events import exploration_fss_events as fss_events


class F3FirstStatusContractTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()
        app_state.current_system = "SMOKE_FIRST_STATUS_SYSTEM"

    def test_confirmed_first_status_uses_confirmed_context(self) -> None:
        with patch("logic.events.exploration_fss_events.emit_insight") as emit_mock:
            fss_events.handle_scan(
                {
                    "event": "Scan",
                    "BodyName": "SMOKE_FIRST_BODY_1",
                    "WasDiscovered": False,
                },
                gui_ref=None,
            )

        ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertIn("MSG.FIRST_DISCOVERY", ids)
        self.assertIn("MSG.BODY_NO_PREV_DISCOVERY", ids)

        for call in emit_mock.call_args_list:
            msg_id = call.kwargs.get("message_id")
            if msg_id not in {"MSG.FIRST_DISCOVERY", "MSG.BODY_NO_PREV_DISCOVERY"}:
                continue
            ctx = call.kwargs.get("context") or {}
            self.assertEqual(ctx.get("first_status_kind"), "confirmed")
            self.assertEqual(ctx.get("trust_status"), "TRUST_HIGH")
            self.assertEqual(ctx.get("confidence"), "high")

    def test_opportunity_first_status_uses_cautious_context(self) -> None:
        with patch("logic.events.exploration_fss_events.emit_insight") as emit_mock:
            # No WasDiscovered in payload -> opportunity only.
            fss_events.handle_scan(
                {
                    "event": "Scan",
                    "BodyName": "SMOKE_FIRST_OPPORTUNITY_BODY_1",
                },
                gui_ref=None,
            )
            # Second scan in same system should not re-emit system-level opportunity.
            fss_events.handle_scan(
                {
                    "event": "Scan",
                    "BodyName": "SMOKE_FIRST_OPPORTUNITY_BODY_2",
                },
                gui_ref=None,
            )

        opp_calls = [
            call
            for call in emit_mock.call_args_list
            if call.kwargs.get("message_id") == "MSG.FIRST_DISCOVERY_OPPORTUNITY"
        ]
        self.assertEqual(len(opp_calls), 1)
        ctx = opp_calls[0].kwargs.get("context") or {}
        self.assertEqual(ctx.get("first_status_kind"), "opportunity")
        self.assertEqual(ctx.get("trust_status"), "TRUST_MEDIUM")
        self.assertEqual(ctx.get("confidence"), "mid")

    def test_event_mapping_exposes_opportunity_vs_confirmed_decision_spaces(self) -> None:
        confirmed = resolve_emit_contract(
            message_id="MSG.FIRST_DISCOVERY",
            context={"system": "SOL"},
            event_type="BODY_DISCOVERED",
        )
        opportunity = resolve_emit_contract(
            message_id="MSG.FIRST_DISCOVERY_OPPORTUNITY",
            context={"system": "SOL"},
            event_type="BODY_DISCOVERED",
        )
        body_confirmed = resolve_emit_contract(
            message_id="MSG.BODY_NO_PREV_DISCOVERY",
            context={"system": "SOL", "body": "SOL A 1"},
            event_type="BODY_DISCOVERED",
        )

        self.assertEqual((confirmed.get("context") or {}).get("decision_space"), "first_confirmed")
        self.assertEqual((body_confirmed.get("context") or {}).get("decision_space"), "first_confirmed")
        self.assertEqual((opportunity.get("context") or {}).get("decision_space"), "first_opportunity")


if __name__ == "__main__":
    unittest.main()

