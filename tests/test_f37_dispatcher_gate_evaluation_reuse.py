from __future__ import annotations

import unittest
from unittest.mock import patch

from logic import insight_dispatcher


class F37DispatcherGateEvaluationReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        insight_dispatcher.reset_dispatcher_runtime_state()

    def tearDown(self) -> None:
        insight_dispatcher.reset_dispatcher_runtime_state()

    @staticmethod
    def _pass_cross_module(insight, *, allow_tts, allow_reason):
        return allow_tts, allow_reason, False

    @staticmethod
    def _pass_matrix(insight, *, allow_tts, allow_reason):
        return allow_tts, allow_reason, False

    @staticmethod
    def _resolve_contract(**kwargs):
        return {
            "context": dict(kwargs.get("context") or {}),
            "priority": str(kwargs.get("priority") or "P2_NORMAL"),
            "dedup_key": kwargs.get("dedup_key"),
            "cooldown_scope": str(kwargs.get("cooldown_scope") or "message"),
            "cooldown_seconds": kwargs.get("cooldown_seconds"),
        }

    def test_emit_insight_reuses_initial_gate_when_priority_not_escalated(self) -> None:
        real_gate = insight_dispatcher.evaluate_risk_trust_gate
        with (
            patch("logic.insight_dispatcher.resolve_emit_contract", side_effect=self._resolve_contract),
            patch("logic.insight_dispatcher.evaluate_risk_trust_gate", wraps=real_gate) as gate_mock,
            patch("logic.insight_dispatcher._try_escalate_priority", return_value=("P2_NORMAL", "")),
            patch("logic.insight_dispatcher._evaluate_should_speak", return_value=(False, "test")),
            patch("logic.insight_dispatcher._apply_cross_module_voice_priority", side_effect=self._pass_cross_module),
            patch("logic.insight_dispatcher._apply_priority_matrix", side_effect=self._pass_matrix),
            patch("logic.insight_dispatcher._notify.powiedz"),
        ):
            ok = insight_dispatcher.emit_insight(
                "test",
                message_id="MSG.NEXT_HOP",
                source="test",
                context={"system": "SOL"},
                priority="P2_NORMAL",
            )

        self.assertFalse(ok)
        self.assertEqual(gate_mock.call_count, 1, "Gate should be evaluated once when no escalation occurs.")

    def test_emit_insight_recomputes_gate_when_priority_escalates(self) -> None:
        real_gate = insight_dispatcher.evaluate_risk_trust_gate
        with (
            patch("logic.insight_dispatcher.resolve_emit_contract", side_effect=self._resolve_contract),
            patch("logic.insight_dispatcher.evaluate_risk_trust_gate", wraps=real_gate) as gate_mock,
            patch("logic.insight_dispatcher._try_escalate_priority", return_value=("P1_HIGH", "test_escalation")),
            patch("logic.insight_dispatcher._evaluate_should_speak", return_value=(False, "test")),
            patch("logic.insight_dispatcher._apply_cross_module_voice_priority", side_effect=self._pass_cross_module),
            patch("logic.insight_dispatcher._apply_priority_matrix", side_effect=self._pass_matrix),
            patch("logic.insight_dispatcher._notify.powiedz"),
        ):
            ok = insight_dispatcher.emit_insight(
                "test",
                message_id="MSG.NEXT_HOP",
                source="test",
                context={"system": "SOL"},
                priority="P2_NORMAL",
            )

        self.assertFalse(ok)
        self.assertEqual(gate_mock.call_count, 2, "Gate should be recomputed when effective priority changes.")


if __name__ == "__main__":
    unittest.main()

