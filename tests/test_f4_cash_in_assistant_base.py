from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import cash_in_assistant


class F4CashInAssistantBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.current_system = "F4_CASH_IN_TEST_SYSTEM"
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()

    @staticmethod
    def _summary_payload() -> dict:
        return {
            "system": "F4_CASH_IN_TEST_SYSTEM",
            "scanned_bodies": 9,
            "total_bodies": 12,
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 18_000_000.0,
            "cash_in_session_estimated": 39_500_000.0,
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }

    def test_manual_trigger_emits_decision_space_with_skip(self) -> None:
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._summary_payload(),
            )

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.CASH_IN_ASSISTANT")
        self.assertEqual(kwargs.get("event_type"), "CASH_IN_REVIEW")
        self.assertEqual(kwargs.get("priority"), "P2_NORMAL")
        self.assertEqual(float(kwargs.get("cooldown_seconds") or 0.0), 0.0)

        ctx = dict(kwargs.get("context") or {})
        self.assertIn("cash_in_payload", ctx)
        payload = dict(ctx.get("cash_in_payload") or {})
        options = payload.get("options") or []
        self.assertGreaterEqual(len(options), 2)
        self.assertLessEqual(len(options), 3)
        self.assertEqual((payload.get("skip_action") or {}).get("label"), "Pomijam")
        self.assertTrue(str(ctx.get("raw_text") or "").strip())

    def test_auto_trigger_is_guarded_by_signature_and_skip(self) -> None:
        payload = self._summary_payload()
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            first = cash_in_assistant.trigger_cash_in_assistant(mode="auto", summary_payload=payload)
            second = cash_in_assistant.trigger_cash_in_assistant(mode="auto", summary_payload=payload)
            app_state.cash_in_skip_signature = str(app_state.last_cash_in_signature or "")
            third = cash_in_assistant.trigger_cash_in_assistant(mode="auto", summary_payload=payload)

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertFalse(third)
        self.assertEqual(emit_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
