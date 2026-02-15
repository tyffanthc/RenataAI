from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.event_insight_mapping import get_tts_policy_spec, resolve_emit_contract
from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.utils import notify as notify_module


class F5VoicePolicyContractTests(unittest.TestCase):
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

    def test_tts_policy_spec_core_threshold_messages(self) -> None:
        expected = {
            "MSG.EXOBIO_RANGE_READY": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.EXOBIO_SAMPLE_LOGGED": ("context", "explore", "ALWAYS_SAY"),
            "MSG.FSS_PROGRESS_25": ("context", "explore", "BYPASS_GLOBAL"),
            "MSG.FUEL_CRITICAL": ("critical", "alert", "ALWAYS_SAY"),
        }
        for message_id, (intent, category, cooldown_policy) in expected.items():
            policy = get_tts_policy_spec(message_id)
            self.assertEqual(policy.intent, intent)
            self.assertEqual(policy.category, category)
            self.assertEqual(policy.cooldown_policy, cooldown_policy)

    def test_resolve_emit_contract_injects_tts_policy_metadata(self) -> None:
        resolved = resolve_emit_contract(
            message_id="MSG.EXOBIO_RANGE_READY",
            context={"system": "POLICY_TEST_SYSTEM"},
            event_type="BIO_PROGRESS",
            priority=None,
            dedup_key=None,
            cooldown_scope=None,
            cooldown_seconds=None,
        )
        ctx = dict(resolved.get("context") or {})
        self.assertEqual(ctx.get("tts_intent"), "context")
        self.assertEqual(ctx.get("tts_category"), "explore")
        self.assertEqual(ctx.get("tts_cooldown_policy"), "BYPASS_GLOBAL")

    def test_notify_policy_bypass_global_still_allows_threshold_message(self) -> None:
        def can_send_side_effect(key, cooldown_sec, context=None):
            # Simulate blocked global cooldown but open intent cooldown.
            if key == "TTS_GLOBAL":
                return False
            return True

        with (
            patch("logic.utils.notify.has_capability", return_value=False),
            patch("logic.utils.notify._is_transit_mode", return_value=False),
            patch.object(notify_module.DEBOUNCER, "can_send", side_effect=can_send_side_effect),
        ):
            allowed = notify_module._should_speak_tts(
                "MSG.EXOBIO_RANGE_READY",
                {"confidence": "high"},
            )
        self.assertTrue(allowed, "BYPASS_GLOBAL should ignore blocked global cooldown")

    def test_emit_insight_context_contains_voice_policy_contract(self) -> None:
        with (
            patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
            patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
            patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
        ):
            ok = emit_insight(
                "FSS 25",
                message_id="MSG.FSS_PROGRESS_25",
                source="exploration_fss_events",
                event_type="SYSTEM_SCANNED",
                context={
                    "system": "POLICY_TEST_SYSTEM",
                    "risk_status": "RISK_MEDIUM",
                    "trust_status": "TRUST_HIGH",
                    "confidence": "high",
                },
                priority="P2_NORMAL",
                dedup_key="policy:fss25:test",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )

        self.assertTrue(ok)
        self.assertEqual(powiedz_mock.call_count, 1)
        runtime_ctx = dict(powiedz_mock.call_args.kwargs.get("context") or {})
        self.assertEqual(runtime_ctx.get("tts_intent"), "context")
        self.assertEqual(runtime_ctx.get("tts_category"), "explore")
        self.assertEqual(runtime_ctx.get("tts_cooldown_policy"), "BYPASS_GLOBAL")
        self.assertTrue(bool(runtime_ctx.get("gate_reason")))


if __name__ == "__main__":
    unittest.main()

