from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
from app.state import app_state
from logic.event_handler import EventHandler
from logic.exit_summary import ExitSummaryData
from logic.events import cash_in_assistant


class F11CashInStartJumpCalloutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_bootstrap = getattr(app_state, "bootstrap_replay", None)
        self._orig_settings = dict(config.config._settings)
        app_state.current_system = "F11_STARTJUMP_TEST_SYSTEM"
        app_state.bootstrap_replay = False
        config.config._settings["cash_in.startjump_callout_enabled"] = True
        config.config._settings["cash_in.startjump_callout_cooldown_sec"] = 35.0

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.bootstrap_replay = self._saved_bootstrap
        config.config._settings = self._orig_settings

    @staticmethod
    def _summary(*, total_value: float) -> ExitSummaryData:
        return ExitSummaryData(
            system_name="F11_STARTJUMP_TEST_SYSTEM",
            total_value=total_value,
        )

    def test_startjump_hyperspace_high_confidence_emits_exact_amounts(self) -> None:
        with (
            patch.object(
                app_state.exit_summary,
                "build_summary_data",
                return_value=self._summary(total_value=4_200_000.0),
            ),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 22_900_000.0}),
            ),
            patch("logic.events.cash_in_assistant.DEBOUNCER.is_allowed", return_value=True),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"}
            )

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.CASH_IN_STARTJUMP")
        self.assertEqual(kwargs.get("event_type"), "CASH_IN_STARTJUMP")
        self.assertEqual(kwargs.get("priority"), "P2_NORMAL")
        self.assertEqual(float(kwargs.get("cooldown_seconds") or 0.0), 35.0)
        ctx = dict(kwargs.get("context") or {})
        self.assertEqual(ctx.get("confidence"), "high")
        self.assertIn("22 900 000 Cr", str(ctx.get("raw_text") or ""))
        self.assertIn("4 200 000 Cr", str(ctx.get("raw_text") or ""))
        self.assertTrue(bool(ctx.get("force_tts")))

    def test_startjump_mid_confidence_uses_approx_text(self) -> None:
        with (
            patch.object(
                app_state.exit_summary,
                "build_summary_data",
                return_value=self._summary(total_value=0.0),
            ),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 7_650_000.0}),
            ),
            patch("logic.events.cash_in_assistant.DEBOUNCER.is_allowed", return_value=True),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"}
            )

        self.assertTrue(ok)
        kwargs = emit_mock.call_args.kwargs
        ctx = dict(kwargs.get("context") or {})
        self.assertEqual(ctx.get("confidence"), "mid")
        raw_text = str(ctx.get("raw_text") or "")
        self.assertIn("orientacyjnie", raw_text.lower())
        self.assertNotIn("Cash-in", raw_text)
        self.assertIn("8 000 000 Cr", raw_text)

    def test_startjump_low_confidence_is_silent_when_values_are_zero(self) -> None:
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=None),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 0.0}),
            ),
            patch("logic.events.cash_in_assistant.DEBOUNCER.is_allowed", return_value=True) as debouncer_mock,
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"}
            )

        self.assertFalse(ok)
        self.assertEqual(emit_mock.call_count, 0)
        debouncer_mock.assert_not_called()

    def test_startjump_non_hyperspace_is_ignored(self) -> None:
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Supercruise"}
            )

        self.assertFalse(ok)
        self.assertEqual(emit_mock.call_count, 0)

    def test_startjump_respects_cooldown_guard(self) -> None:
        with (
            patch.object(
                app_state.exit_summary,
                "build_summary_data",
                return_value=self._summary(total_value=2_000_000.0),
            ),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 10_000_000.0}),
            ),
            patch("logic.events.cash_in_assistant.DEBOUNCER.is_allowed", return_value=False),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"}
            )

        self.assertFalse(ok)
        self.assertEqual(emit_mock.call_count, 0)

    def test_event_handler_routes_startjump_to_cash_in_callout(self) -> None:
        router = EventHandler()
        with patch(
            "logic.event_handler.cash_in_assistant.trigger_startjump_cash_in_callout",
            return_value=True,
        ) as callout_mock:
            router.handle_event(json.dumps({"event": "StartJump", "JumpType": "Hyperspace"}))

        self.assertEqual(callout_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
