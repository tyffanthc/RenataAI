from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.events import combat_awareness as combat_events
from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.utils import notify as notify_module


class F5QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_combat_signature = getattr(app_state, "last_combat_awareness_signature", None)
        app_state.current_system = "F5_QUALITY_SYSTEM"
        app_state.last_combat_awareness_signature = None
        reset_dispatcher_runtime_state()
        combat_events.reset_combat_awareness_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_combat_awareness_signature = self._saved_combat_signature
        reset_dispatcher_runtime_state()
        combat_events.reset_combat_awareness_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    @staticmethod
    def _ctx(
        *,
        system: str = "F5_QUALITY_SYSTEM",
        in_combat: bool = False,
        risk: str = "RISK_MEDIUM",
        var: str = "VAR_MEDIUM",
    ) -> dict:
        return {
            "system": system,
            "in_combat": in_combat,
            "risk_status": risk,
            "var_status": var,
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }

    def test_combat_awareness_is_pattern_only_and_non_coercive(self) -> None:
        with (
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 31_000_000.0}),
            ),
            patch("logic.events.combat_awareness.emit_insight") as emit_mock,
        ):
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_QUALITY_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.55,
                    "ShieldsUp": False,
                    "FSDCooldown": 5.0,
                },
                gui_ref=None,
            )
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_QUALITY_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.80,
                    "ShieldsUp": True,
                    "FSDCooldown": 0.0,
                },
                gui_ref=None,
            )
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_QUALITY_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.55,
                    "ShieldsUp": False,
                    "FSDCooldown": 5.0,
                },
                gui_ref=None,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("event_type"), "COMBAT_RISK_PATTERN")
        self.assertIn(kwargs.get("message_id"), {"MSG.COMBAT_AWARENESS_HIGH", "MSG.COMBAT_AWARENESS_CRITICAL"})
        ctx = dict(kwargs.get("context") or {})
        payload = dict(ctx.get("combat_payload") or {})
        self.assertTrue(str(payload.get("pattern_id") or "").strip())
        self.assertGreaterEqual(int(payload.get("pattern_count") or 0), 2)
        raw_text = str(ctx.get("raw_text") or "").lower()
        self.assertIn("wzorzec ryzyka", raw_text)
        for forbidden in ("musisz", "powinienes", "zrob teraz", "natychmiast"):
            self.assertNotIn(forbidden, raw_text)

    def test_priority_matrix_is_deterministic_for_f4_vs_f5(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False, True]),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            summary_ok = emit_insight(
                "summary",
                message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
                source="exploration_summary",
                event_type="SYSTEM_SUMMARY",
                context=self._ctx(),
                priority="P3_LOW",
                dedup_key="f5:quality:summary",
                cooldown_scope="entity",
                cooldown_seconds=45.0,
            )
            combat_ok = emit_insight(
                "combat high",
                message_id="MSG.COMBAT_AWARENESS_HIGH",
                source="combat_awareness",
                event_type="COMBAT_RISK_PATTERN",
                context=self._ctx(in_combat=False, risk="RISK_HIGH", var="VAR_HIGH"),
                priority="P1_HIGH",
                dedup_key="f5:quality:combat",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
            nav_ok = emit_insight(
                "next hop",
                message_id="MSG.NEXT_HOP",
                source="navigation_events",
                event_type="ROUTE_PROGRESS",
                context=self._ctx(),
                priority="P2_NORMAL",
                dedup_key="f5:quality:nav",
                cooldown_scope="entity",
                cooldown_seconds=30.0,
            )

        self.assertTrue(summary_ok)
        self.assertTrue(combat_ok)
        self.assertFalse(nav_ok)
        self.assertEqual(powiedz_mock.call_count, 3)
        second_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
        self.assertEqual(second_ctx.get("voice_priority_reason"), "matrix_preempt_higher_force")
        third_ctx = dict(powiedz_mock.call_args_list[2].kwargs.get("context") or {})
        self.assertEqual(third_ctx.get("voice_priority_reason"), "matrix_suppressed_by_recent_higher_or_equal")

    def test_anti_spam_stability_for_combat_and_non_combat(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            ready_blocked = emit_insight(
                "ready in combat",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=True),
                priority="P2_NORMAL",
                dedup_key="f5:quality:ready",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            ready_recovered = emit_insight(
                "ready after combat",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=False),
                priority="P2_NORMAL",
                dedup_key="f5:quality:ready",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            ready_cooldown = emit_insight(
                "ready second",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=False),
                priority="P2_NORMAL",
                dedup_key="f5:quality:ready",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            fuel_ok = emit_insight(
                "fuel critical",
                message_id="MSG.FUEL_CRITICAL",
                source="fuel_events",
                event_type="SHIP_HEALTH_CHANGED",
                context=self._ctx(in_combat=True, risk="RISK_CRITICAL", var="VAR_HIGH"),
                priority="P0_CRITICAL",
                dedup_key="f5:quality:fuel",
                cooldown_scope="entity",
                cooldown_seconds=300.0,
                combat_silence_sensitive=False,
            )

        self.assertFalse(ready_blocked)
        self.assertTrue(ready_recovered)
        self.assertFalse(ready_cooldown)
        self.assertTrue(fuel_ok)
        reasons = [dict(call.kwargs.get("context") or {}).get("voice_priority_reason") for call in powiedz_mock.call_args_list]
        self.assertIn("combat_silence", reasons)
        self.assertIn("insight_cooldown", reasons)
        self.assertIn(reasons[-1], {"priority_critical", "matrix_p0_critical"})

    def test_no_conflict_between_f4_survival_and_f5_combat_critical(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False]),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            survival_ok = emit_insight(
                "survival high",
                message_id="MSG.SURVIVAL_REBUY_HIGH",
                source="survival_rebuy_awareness",
                event_type="SURVIVAL_RISK_CHANGED",
                context=self._ctx(risk="RISK_HIGH", var="VAR_HIGH"),
                priority="P1_HIGH",
                dedup_key="f5:quality:survival",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
            )
            combat_critical_ok = emit_insight(
                "combat critical",
                message_id="MSG.COMBAT_AWARENESS_CRITICAL",
                source="combat_awareness",
                event_type="COMBAT_RISK_PATTERN",
                context=self._ctx(in_combat=True, risk="RISK_CRITICAL", var="VAR_HIGH"),
                priority="P0_CRITICAL",
                dedup_key="f5:quality:combat:critical",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )

        self.assertTrue(survival_ok)
        self.assertTrue(combat_critical_ok)
        self.assertEqual(powiedz_mock.call_count, 2)
        combat_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
        self.assertIn(
            combat_ctx.get("voice_priority_reason"),
            {"priority_critical", "matrix_p0_critical_force", "matrix_p0_critical"},
        )


if __name__ == "__main__":
    unittest.main()
