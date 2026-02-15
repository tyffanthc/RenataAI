from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.utils import notify as notify_module


class F5AntiSpamRegressionTests(unittest.TestCase):
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
    def _ctx(
        *,
        system: str = "F5_ANTI_SPAM_SYSTEM",
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

    def test_burst_same_combat_signature_is_non_flood(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            results = []
            for _ in range(4):
                results.append(
                    emit_insight(
                        "combat high burst",
                        message_id="MSG.COMBAT_AWARENESS_HIGH",
                        source="combat_awareness",
                        event_type="COMBAT_RISK_PATTERN",
                        context=self._ctx(in_combat=True, risk="RISK_HIGH", var="VAR_HIGH"),
                        priority="P1_HIGH",
                        dedup_key="f5:anti_spam:combat:burst",
                        cooldown_scope="entity",
                        cooldown_seconds=75.0,
                    )
                )

        self.assertEqual(results, [False, True, False, False])
        reasons = [dict(call.kwargs.get("context") or {}).get("voice_priority_reason") for call in powiedz_mock.call_args_list]
        self.assertIn("priority_critical", reasons[1:2])
        self.assertIn("insight_cooldown", reasons[2:])

    def test_ready_exception_recovers_after_combat_silence_and_stays_non_flood(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            blocked_in_combat = emit_insight(
                "ready in combat",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=True),
                priority="P2_NORMAL",
                dedup_key="f5:anti_spam:ready:recover",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            allowed_after_combat = emit_insight(
                "ready after combat",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=False),
                priority="P2_NORMAL",
                dedup_key="f5:anti_spam:ready:recover",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            blocked_by_cooldown = emit_insight(
                "ready after combat second",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=False),
                priority="P2_NORMAL",
                dedup_key="f5:anti_spam:ready:recover",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )

        self.assertFalse(blocked_in_combat)
        self.assertTrue(allowed_after_combat)
        self.assertFalse(blocked_by_cooldown)
        reasons = [dict(call.kwargs.get("context") or {}).get("voice_priority_reason") for call in powiedz_mock.call_args_list]
        self.assertEqual(reasons[0], "combat_silence")
        self.assertIn("insight_cooldown", reasons[2:])

    def test_fss_threshold_bypasses_global_cooldown_but_respects_entity_cooldown(self) -> None:
        # Prime global TTS cooldown to simulate a busy speech window.
        self.assertTrue(notify_module.DEBOUNCER.can_send("TTS_GLOBAL", 8.0))

        first = emit_insight(
            "fss 25",
            message_id="MSG.FSS_PROGRESS_25",
            source="exploration_fss_events",
            event_type="SYSTEM_SCANNED",
            context=self._ctx(system="F5_ANTI_SPAM_FSS"),
            priority="P2_NORMAL",
            dedup_key="f5:anti_spam:fss25",
            cooldown_scope="entity",
            cooldown_seconds=120.0,
        )
        second = emit_insight(
            "fss 25 again",
            message_id="MSG.FSS_PROGRESS_25",
            source="exploration_fss_events",
            event_type="SYSTEM_SCANNED",
            context=self._ctx(system="F5_ANTI_SPAM_FSS"),
            priority="P2_NORMAL",
            dedup_key="f5:anti_spam:fss25",
            cooldown_scope="entity",
            cooldown_seconds=120.0,
        )

        self.assertTrue(first, "FSS threshold message should bypass global cooldown")
        self.assertFalse(second, "FSS threshold should still respect anti-spam entity cooldown")

    def test_fuel_critical_is_not_lost_during_combat_burst(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            _combat_attempt = emit_insight(
                "combat high",
                message_id="MSG.COMBAT_AWARENESS_HIGH",
                source="combat_awareness",
                event_type="COMBAT_RISK_PATTERN",
                context=self._ctx(in_combat=True, risk="RISK_HIGH", var="VAR_HIGH"),
                priority="P1_HIGH",
                dedup_key="f5:anti_spam:combat:for_fuel",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
            fuel_ok = emit_insight(
                "fuel critical",
                message_id="MSG.FUEL_CRITICAL",
                source="fuel_events",
                event_type="SHIP_HEALTH_CHANGED",
                context=self._ctx(in_combat=True, risk="RISK_CRITICAL", var="VAR_HIGH"),
                priority="P0_CRITICAL",
                dedup_key="f5:anti_spam:fuel:critical",
                cooldown_scope="entity",
                cooldown_seconds=300.0,
                combat_silence_sensitive=False,
            )

        self.assertTrue(fuel_ok, "Critical fuel alert must not be lost during combat burst")
        fuel_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
        self.assertIn(
            fuel_ctx.get("voice_priority_reason"),
            {"priority_critical", "matrix_p0_critical"},
        )


if __name__ == "__main__":
    unittest.main()
