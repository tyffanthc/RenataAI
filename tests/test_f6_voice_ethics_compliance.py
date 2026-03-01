from __future__ import annotations

import unicodedata
import unittest
from dataclasses import replace
from unittest.mock import patch

from logic.event_insight_mapping import (
    TTS_POLICY_BY_MESSAGE_ID,
    get_tts_policy_spec,
    resolve_emit_contract,
)
from logic.events.cash_in_assistant import (
    CashInAssistantPayload,
    _build_tts_line as cash_in_tts_line,
)
from logic.events.combat_awareness import (
    CombatAwarenessPayload,
    _tts_line as combat_tts_line,
)
from logic.events.survival_rebuy_awareness import (
    SurvivalRebuyPayload,
    _tts_line as survival_tts_line,
)
from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.tts.text_preprocessor import prepare_tts
from logic.utils import notify as notify_module


class F6VoiceEthicsComplianceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_dispatcher_runtime_state()
        self._clear_debouncer()

    def tearDown(self) -> None:
        reset_dispatcher_runtime_state()
        self._clear_debouncer()

    @staticmethod
    def _clear_debouncer() -> None:
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    @staticmethod
    def _ctx(
        *,
        system: str = "F6_VOICE_ETHICS_SYSTEM",
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

    @staticmethod
    def _normalize_tone_text(text: str) -> str:
        lowered = str(text or "").lower()
        return unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")

    def _assert_neutral_tone(self, text: str) -> None:
        normalized = self._normalize_tone_text(text)
        forbidden_snippets = (
            "musisz",
            "powinienes",
            "natychmiast",
            "jedyna opcja",
            "jedyny sluszny",
            "top 1",
            "top1",
        )
        for snippet in forbidden_snippets:
            self.assertNotIn(snippet, normalized, f"Non-neutral wording found: '{snippet}' in '{text}'")

    def test_policy_exception_matrix_matches_public_voice_policy(self) -> None:
        expected = {
            "MSG.EXOBIO_SAMPLE_LOGGED": ("context", "explore", "ALWAYS_SAY"),
            "MSG.EXOBIO_SPECIES_COMPLETE": ("context", "explore", "ALWAYS_SAY"),
            "MSG.EXOBIO_RANGE_READY": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.FSS_PROGRESS_25": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.FSS_PROGRESS_50": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.FSS_PROGRESS_75": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.FSS_LAST_BODY": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.SYSTEM_FULLY_SCANNED": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.FUEL_CRITICAL": ("critical", "alert", "ALWAYS_SAY"),
        }
        for message_id, (intent, category, cooldown_policy) in expected.items():
            policy = get_tts_policy_spec(message_id)
            self.assertEqual(policy.intent, intent)
            self.assertEqual(policy.category, category)
            self.assertEqual(policy.cooldown_policy, cooldown_policy)

    def test_emit_contract_injects_policy_metadata_for_all_voice_policies(self) -> None:
        allowed_policies = {"NORMAL", "BYPASS_GLOBAL", "ALWAYS_SAY"}
        for message_id in sorted(TTS_POLICY_BY_MESSAGE_ID):
            policy = get_tts_policy_spec(message_id)
            resolved = resolve_emit_contract(
                message_id=message_id,
                context={"system": "F6_VOICE_ETHICS_SYSTEM"},
                event_type="F6_VOICE_POLICY_AUDIT",
                priority=None,
                dedup_key=None,
                cooldown_scope=None,
                cooldown_seconds=None,
            )
            ctx = dict(resolved.get("context") or {})
            self.assertEqual(ctx.get("tts_intent"), policy.intent)
            self.assertEqual(ctx.get("tts_category"), policy.category)
            self.assertEqual(ctx.get("tts_cooldown_policy"), policy.cooldown_policy)
            self.assertIn(str(policy.cooldown_policy), allowed_policies)

    def test_bypass_global_and_always_say_ignore_global_tts_cooldown(self) -> None:
        def can_send_side_effect(key: str, cooldown_sec: float, context=None) -> bool:
            if key == "TTS_GLOBAL":
                return False
            return True

        with (
            patch("logic.utils.notify.has_capability", return_value=False),
            patch("logic.utils.notify._is_transit_mode", return_value=False),
            patch.object(notify_module.DEBOUNCER, "can_send", side_effect=can_send_side_effect),
        ):
            self.assertTrue(notify_module._should_speak_tts("MSG.EXOBIO_RANGE_READY", {"confidence": "high"}))
            self.assertTrue(notify_module._should_speak_tts("MSG.FSS_PROGRESS_50", {"confidence": "high"}))
            self.assertTrue(notify_module._should_speak_tts("MSG.FUEL_CRITICAL", {"confidence": "high"}))
            self.assertFalse(notify_module._should_speak_tts("MSG.NEXT_HOP", {"confidence": "high"}))

    def test_cooldown_exceptions_keep_antispam_and_combat_silence_invariants(self) -> None:
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
                dedup_key="f6:voice_ethics:ready",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            ready_allowed = emit_insight(
                "ready after combat",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=False),
                priority="P2_NORMAL",
                dedup_key="f6:voice_ethics:ready",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            ready_blocked_by_cooldown = emit_insight(
                "ready second",
                message_id="MSG.EXOBIO_RANGE_READY",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=self._ctx(in_combat=False),
                priority="P2_NORMAL",
                dedup_key="f6:voice_ethics:ready",
                cooldown_scope="entity",
                cooldown_seconds=10.0,
            )
            fuel_allowed = emit_insight(
                "fuel critical",
                message_id="MSG.FUEL_CRITICAL",
                source="fuel_events",
                event_type="SHIP_HEALTH_CHANGED",
                context=self._ctx(in_combat=True, risk="RISK_CRITICAL", var="VAR_HIGH"),
                priority="P0_CRITICAL",
                dedup_key="f6:voice_ethics:fuel",
                cooldown_scope="entity",
                cooldown_seconds=300.0,
                combat_silence_sensitive=False,
            )
            fuel_blocked_by_cooldown = emit_insight(
                "fuel critical second",
                message_id="MSG.FUEL_CRITICAL",
                source="fuel_events",
                event_type="SHIP_HEALTH_CHANGED",
                context=self._ctx(in_combat=True, risk="RISK_CRITICAL", var="VAR_HIGH"),
                priority="P0_CRITICAL",
                dedup_key="f6:voice_ethics:fuel",
                cooldown_scope="entity",
                cooldown_seconds=300.0,
                combat_silence_sensitive=False,
            )

        self.assertFalse(ready_blocked)
        self.assertTrue(ready_allowed)
        self.assertFalse(ready_blocked_by_cooldown)
        self.assertTrue(fuel_allowed)
        self.assertFalse(fuel_blocked_by_cooldown)

        reasons = [dict(call.kwargs.get("context") or {}).get("voice_priority_reason") for call in powiedz_mock.call_args_list]
        self.assertIn("combat_silence", reasons)
        self.assertIn("insight_cooldown", reasons)
        self.assertTrue(
            any(reason in {"priority_critical", "matrix_p0_critical", "matrix_p0_critical_force"} for reason in reasons),
            f"Missing critical voice reason in: {reasons}",
        )

    def test_voice_lines_are_informational_and_non_coercive(self) -> None:
        samples: list[str] = []

        # Text preprocessor templates (no raw_text path).
        samples.extend(
            [
                prepare_tts("MSG.NEXT_HOP", {"system": "SOL"}) or "",
                prepare_tts("MSG.JUMPED_SYSTEM", {"system": "SOL"}) or "",
                prepare_tts("MSG.FSS_PROGRESS_25", {}) or "",
                prepare_tts("MSG.FSS_PROGRESS_50", {}) or "",
                prepare_tts("MSG.FSS_PROGRESS_75", {}) or "",
                prepare_tts("MSG.FSS_LAST_BODY", {}) or "",
                prepare_tts("MSG.SYSTEM_FULLY_SCANNED", {}) or "",
                prepare_tts("MSG.BODY_NO_PREV_DISCOVERY", {"body": "SOL A 1"}) or "",
                prepare_tts("MSG.FUEL_CRITICAL", {}) or "",
                prepare_tts(
                    "MSG.SMUGGLER_ILLEGAL_CARGO",
                    {"raw_text": "Uwaga. Nielegalny ladunek na pokladzie."},
                )
                or "",
                prepare_tts("MSG.MILESTONE_PROGRESS", {"percent": 50, "target": "LHS 20"}) or "",
                prepare_tts(
                    "MSG.MILESTONE_REACHED",
                    {"target": "LHS 20", "next_target": "COL 285 SECTOR"},
                )
                or "",
            ]
        )

        combat_base = CombatAwarenessPayload(
            system="F6_VOICE_ETHICS_SYSTEM",
            mode="auto",
            level="high",
            pattern_id="combat_hull_critical",
            pattern_count=2,
            in_combat=True,
            hull_percent=18.0,
            shields_up=False,
            under_attack=True,
            being_interdicted=False,
            fsd_cooldown_sec=5.0,
            var_status="VAR_HIGH",
            risk_status="RISK_HIGH",
            session_value_estimated=20_000_000.0,
            system_value_estimated=5_000_000.0,
            cargo_tons=40.0,
            options=[],
            note="",
            signature="f6",
        )
        for pattern_id in (
            "combat_hull_critical",
            "combat_shields_down_exposed",
            "combat_escape_window_unstable",
            "combat_high_stake_exposure",
        ):
            samples.append(combat_tts_line(replace(combat_base, pattern_id=pattern_id)))

        survival_base = SurvivalRebuyPayload(
            system="F6_VOICE_ETHICS_SYSTEM",
            mode="auto",
            level="high",
            reason="no_rebuy",
            credits=1_000_000.0,
            rebuy_cost=2_000_000.0,
            rebuy_ratio=0.5,
            hull_percent=20.0,
            shields_up=False,
            in_combat=True,
            var_status="VAR_HIGH",
            risk_status="RISK_HIGH",
            session_value_estimated=10_000_000.0,
            system_value_estimated=4_000_000.0,
            cargo_tons=20.0,
            options=[],
            note="",
            signature="f6",
        )
        for reason in (
            "no_rebuy",
            "combat_hull_critical",
            "rebuy_borderline",
            "combat_hull_high_var",
            "fallback",
        ):
            samples.append(survival_tts_line(replace(survival_base, reason=reason)))

        cash_base = CashInAssistantPayload(
            system="F6_VOICE_ETHICS_SYSTEM",
            mode="auto",
            signal="wysoki",
            scanned_bodies=10,
            total_bodies=12,
            system_value_estimated=4_000_000.0,
            session_value_estimated=20_000_000.0,
            trust_status="TRUST_HIGH",
            confidence="high",
            options=[{"id": "a"}],
            skip_action={"id": "skip", "label": "Pomijam"},
            note="",
            signature="f6",
        )
        samples.append(cash_in_tts_line(cash_base))
        samples.append(cash_in_tts_line(replace(cash_base, options=[{"id": "a"}, {"id": "b"}])))
        samples.append(cash_in_tts_line(replace(cash_base, options=[{"id": "a"}, {"id": "b"}, {"id": "c"}])))

        for line in samples:
            self.assertTrue(str(line).strip(), "Voice line must not be empty in ethics audit")
            self._assert_neutral_tone(line)


if __name__ == "__main__":
    unittest.main()
