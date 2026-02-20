from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from gui.app import _to_tk_hotkey_sequence
from logic.events import cash_in_assistant


class F11CashInHotkeyTriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._saved_route_mode = getattr(app_state, "route_mode", None)
        self._saved_route_target = getattr(app_state, "route_target", None)
        self._saved_next_system = getattr(app_state, "next_system", None)

        app_state.current_system = "F11_CASH_IN_HOTKEY_TEST_SYSTEM"
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        app_state.set_route_intent("", source="test.hotkey.setup")

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        app_state.route_mode = self._saved_route_mode
        app_state.route_target = self._saved_route_target
        app_state.next_system = self._saved_next_system

    def _payload(self) -> dict:
        return {
            "system": "F11_CASH_IN_HOTKEY_TEST_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 4_000_000.0,
            "cash_in_session_estimated": 13_500_000.0,
        }

    def test_manual_hotkey_mode_uses_manual_dedup_and_zero_cooldown(self) -> None:
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual_hotkey",
                summary_payload=self._payload(),
            )

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = dict(emit_mock.call_args.kwargs or {})
        self.assertTrue(str(kwargs.get("dedup_key") or "").startswith("cash_in_manual:"))
        self.assertIn("cooldown_seconds", kwargs)
        self.assertEqual(float(kwargs.get("cooldown_seconds")), 0.0)

        context = dict(kwargs.get("context") or {})
        structured = dict(context.get("cash_in_payload") or {})
        self.assertEqual(str(structured.get("mode") or ""), "manual_hotkey")

    def test_manual_hotkey_trigger_does_not_mutate_route_state(self) -> None:
        before = {
            "route_mode": str(getattr(app_state, "route_mode", "")),
            "route_target": str(getattr(app_state, "route_target", "")),
            "next_system": str(getattr(app_state, "next_system", "")),
        }
        with patch("logic.events.cash_in_assistant.emit_insight"):
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual_hotkey",
                summary_payload=self._payload(),
            )
        self.assertTrue(ok)
        after = {
            "route_mode": str(getattr(app_state, "route_mode", "")),
            "route_target": str(getattr(app_state, "route_target", "")),
            "next_system": str(getattr(app_state, "next_system", "")),
        }
        self.assertEqual(after, before)

    def test_hotkey_binding_parser_maps_human_notation_to_tk_sequence(self) -> None:
        self.assertEqual(_to_tk_hotkey_sequence("Ctrl+Shift+C"), "<Control-Shift-c>")
        self.assertEqual(_to_tk_hotkey_sequence("Alt+Enter"), "<Alt-Return>")
        self.assertEqual(_to_tk_hotkey_sequence("<Control-Shift-c>"), "<Control-Shift-c>")
        self.assertIsNone(_to_tk_hotkey_sequence("Ctrl"))
        self.assertIsNone(_to_tk_hotkey_sequence("Ctrl+Shift+"))


if __name__ == "__main__":
    unittest.main()
