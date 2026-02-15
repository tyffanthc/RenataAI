from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.utils import notify as notify_module


class F4CrossModuleVoicePriorityTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_dispatcher_runtime_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    def tearDown(self) -> None:
        reset_dispatcher_runtime_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    @staticmethod
    def _base_context() -> dict:
        return {
            "system": "F4_PRIORITY_TEST",
            "risk_status": "RISK_MEDIUM",
            "var_status": "VAR_MEDIUM",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }

    def test_cash_in_preempts_summary_when_notify_policy_blocks_second_message(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False]),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            summary_ok = emit_insight(
                "summary",
                message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
                source="exploration_summary",
                event_type="SYSTEM_SUMMARY",
                context=self._base_context(),
                priority="P3_LOW",
                dedup_key="summary:test",
                cooldown_scope="entity",
                cooldown_seconds=45.0,
            )
            cash_ok = emit_insight(
                "cash-in",
                message_id="MSG.CASH_IN_ASSISTANT",
                source="cash_in_assistant",
                event_type="CASH_IN_REVIEW",
                context=self._base_context(),
                priority="P2_NORMAL",
                dedup_key="cash:test",
                cooldown_scope="entity",
                cooldown_seconds=90.0,
            )

        self.assertTrue(summary_ok)
        self.assertTrue(cash_ok)
        self.assertEqual(powiedz_mock.call_count, 2)
        second_call = powiedz_mock.call_args_list[1]
        self.assertTrue(bool(second_call.kwargs.get("force")))
        ctx = dict(second_call.kwargs.get("context") or {})
        self.assertEqual(ctx.get("voice_priority_reason"), "cross_module_preempt_higher_force")
        self.assertTrue(bool(ctx.get("voice_priority_forced")))

    def test_lower_priority_summary_is_suppressed_after_survival_high(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            high_ok = emit_insight(
                "survival high",
                message_id="MSG.SURVIVAL_REBUY_HIGH",
                source="survival_rebuy_awareness",
                event_type="SURVIVAL_RISK_CHANGED",
                context=self._base_context(),
                priority="P1_HIGH",
                dedup_key="survival-high:test",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
            )
            summary_ok = emit_insight(
                "summary",
                message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
                source="exploration_summary",
                event_type="SYSTEM_SUMMARY",
                context=self._base_context(),
                priority="P3_LOW",
                dedup_key="summary:test",
                cooldown_scope="entity",
                cooldown_seconds=45.0,
            )

        self.assertTrue(high_ok)
        self.assertFalse(summary_ok)
        self.assertEqual(powiedz_mock.call_count, 2)
        second_call = powiedz_mock.call_args_list[1]
        self.assertFalse(bool(second_call.kwargs.get("force")))
        ctx = dict(second_call.kwargs.get("context") or {})
        self.assertEqual(ctx.get("voice_priority_reason"), "cross_module_suppressed_by_recent_higher_or_equal")

    def test_survival_critical_can_force_through_notify_policy_after_lower_priority_message(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False]),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            summary_ok = emit_insight(
                "summary",
                message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
                source="exploration_summary",
                event_type="SYSTEM_SUMMARY",
                context=self._base_context(),
                priority="P3_LOW",
                dedup_key="summary:test",
                cooldown_scope="entity",
                cooldown_seconds=45.0,
            )
            critical_ok = emit_insight(
                "survival critical",
                message_id="MSG.SURVIVAL_REBUY_CRITICAL",
                source="survival_rebuy_awareness",
                event_type="SURVIVAL_RISK_CHANGED",
                context=self._base_context(),
                priority="P0_CRITICAL",
                dedup_key="survival-critical:test",
                cooldown_scope="entity",
                cooldown_seconds=180.0,
            )

        self.assertTrue(summary_ok)
        self.assertTrue(critical_ok)
        self.assertEqual(powiedz_mock.call_count, 2)
        second_call = powiedz_mock.call_args_list[1]
        self.assertTrue(bool(second_call.kwargs.get("force")))
        ctx = dict(second_call.kwargs.get("context") or {})
        self.assertEqual(ctx.get("voice_priority_reason"), "cross_module_p0_critical")
        self.assertFalse(bool(ctx.get("voice_priority_forced")))


if __name__ == "__main__":
    unittest.main()
