from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.utils import notify as notify_module


class F5DispatcherPriorityMatrixTests(unittest.TestCase):
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
    def _ctx(*, risk: str = "RISK_HIGH") -> dict:
        return {
            "system": "F5_MATRIX_TEST",
            "risk_status": risk,
            "var_status": "VAR_HIGH",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }

    def test_navigation_is_suppressed_after_recent_combat_message(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            combat_ok = emit_insight(
                "combat high",
                message_id="MSG.COMBAT_AWARENESS_HIGH",
                source="combat_awareness",
                event_type="COMBAT_RISK_PATTERN",
                context=self._ctx(risk="RISK_HIGH"),
                priority="P1_HIGH",
                dedup_key="combat:test",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
            nav_ok = emit_insight(
                "nav update",
                message_id="MSG.NEXT_HOP",
                source="navigation_events",
                event_type="ROUTE_PROGRESS",
                context=self._ctx(risk="RISK_MEDIUM"),
                priority="P2_NORMAL",
                dedup_key="nav:test",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )

        self.assertTrue(combat_ok)
        self.assertFalse(nav_ok)
        self.assertEqual(powiedz_mock.call_count, 2)
        nav_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
        self.assertEqual(
            nav_ctx.get("voice_priority_reason"),
            "matrix_suppressed_by_recent_higher_or_equal",
        )

    def test_combat_preempts_navigation_and_forces_when_notify_policy_blocks(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False]),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            nav_ok = emit_insight(
                "nav update",
                message_id="MSG.NEXT_HOP",
                source="navigation_events",
                event_type="ROUTE_PROGRESS",
                context=self._ctx(risk="RISK_MEDIUM"),
                priority="P2_NORMAL",
                dedup_key="nav:test",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
            combat_ok = emit_insight(
                "combat high",
                message_id="MSG.COMBAT_AWARENESS_HIGH",
                source="combat_awareness",
                event_type="COMBAT_RISK_PATTERN",
                context=self._ctx(risk="RISK_HIGH"),
                priority="P1_HIGH",
                dedup_key="combat:test",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )

        self.assertTrue(nav_ok)
        self.assertTrue(combat_ok)
        self.assertEqual(powiedz_mock.call_count, 2)
        combat_call = powiedz_mock.call_args_list[1]
        self.assertTrue(bool(combat_call.kwargs.get("force")))
        combat_ctx = dict(combat_call.kwargs.get("context") or {})
        self.assertEqual(combat_ctx.get("voice_priority_reason"), "matrix_preempt_higher_force")
        self.assertTrue(bool(combat_ctx.get("voice_priority_forced")))

    def test_priority_escalation_is_controlled_for_repeated_p2_risk_signal(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            for _ in range(3):
                ok = emit_insight(
                    "escalation candidate",
                    message_id="MSG.TEST_ESCALATION",
                    source="navigation_events",
                    event_type="TEST_EVENT",
                    context=self._ctx(risk="RISK_CRITICAL"),
                    priority="P2_NORMAL",
                    dedup_key="matrix:escalate:test",
                    cooldown_scope="entity",
                    cooldown_seconds=0.0,
                )
                self.assertTrue(ok)

        priorities = [
            dict(call.kwargs.get("context") or {}).get("effective_priority")
            for call in powiedz_mock.call_args_list
        ]
        self.assertEqual(priorities[0], "P2_NORMAL")
        self.assertEqual(priorities[1], "P1_HIGH")
        self.assertEqual(priorities[2], "P0_CRITICAL")


if __name__ == "__main__":
    unittest.main()

