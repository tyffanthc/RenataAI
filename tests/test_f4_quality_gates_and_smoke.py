from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.events import cash_in_assistant
from logic.events import exploration_summary
from logic.events import survival_rebuy_awareness
from logic.insight_dispatcher import emit_insight, reset_dispatcher_runtime_state
from logic.utils import notify as notify_module
from logic.exit_summary import ExitSummaryData


class F4QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_summary_sig = getattr(app_state, "last_exploration_summary_signature", None)
        self._saved_cash_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_cash_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._saved_survival_sig = getattr(app_state, "last_survival_rebuy_signature", None)
        app_state.current_system = "F4_QUALITY_SYSTEM"
        app_state.last_exploration_summary_signature = None
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        app_state.last_survival_rebuy_signature = None
        reset_dispatcher_runtime_state()
        survival_rebuy_awareness.reset_survival_rebuy_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_exploration_summary_signature = self._saved_summary_sig
        app_state.last_cash_in_signature = self._saved_cash_sig
        app_state.cash_in_skip_signature = self._saved_cash_skip_sig
        app_state.last_survival_rebuy_signature = self._saved_survival_sig
        reset_dispatcher_runtime_state()
        survival_rebuy_awareness.reset_survival_rebuy_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    @staticmethod
    def _summary_data() -> ExitSummaryData:
        return ExitSummaryData(
            system_name="F4_QUALITY_SYSTEM",
            scanned_bodies=9,
            total_bodies=12,
            elw_count=1,
            elw_value=20_000_000.0,
            ww_count=1,
            ww_value=3_500_000.0,
            ww_t_count=1,
            ww_t_value=3_500_000.0,
            hmc_t_count=1,
            hmc_t_value=1_700_000.0,
            biology_species_count=2,
            biology_value=5_200_000.0,
            bonus_discovery=900_000.0,
            c_cartography=24_000_000.0,
            c_exobiology=5_200_000.0,
            total_value=29_200_000.0,
        )

    @staticmethod
    def _base_context() -> dict:
        return {
            "system": "F4_QUALITY_SYSTEM",
            "risk_status": "RISK_MEDIUM",
            "var_status": "VAR_MEDIUM",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }

    def test_summary_auto_nonfloods_and_cashin_signature_is_aligned(self) -> None:
        sample = self._summary_data()
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=sample),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 41_000_000.0}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as summary_emit,
            patch("logic.events.cash_in_assistant.emit_insight") as cash_emit,
        ):
            first = exploration_summary.trigger_exploration_summary(mode="auto")
            second = exploration_summary.trigger_exploration_summary(mode="auto")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(summary_emit.call_count, 1)
        self.assertEqual(cash_emit.call_count, 1)
        self.assertTrue(str(getattr(app_state, "last_exploration_summary_signature", "") or "").strip())
        self.assertTrue(str(getattr(app_state, "last_cash_in_signature", "") or "").strip())

    def test_cash_in_decision_space_has_2_to_3_options_and_skip(self) -> None:
        payload = {
            "system": "F4_QUALITY_SYSTEM",
            "scanned_bodies": 9,
            "total_bodies": 12,
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 18_500_000.0,
            "cash_in_session_estimated": 42_500_000.0,
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        options = structured.get("options") or []
        self.assertGreaterEqual(len(options), 2)
        self.assertLessEqual(len(options), 3)
        self.assertEqual((structured.get("skip_action") or {}).get("label"), "Pomijam")

    def test_survival_no_rebuy_is_critical_and_is_deduped(self) -> None:
        no_rebuy_event = {
            "event": "LoadGame",
            "StarSystem": "F4_QUALITY_SYSTEM",
            "Credits": 120_000,
            "Rebuy": 850_000,
        }
        with patch("logic.events.survival_rebuy_awareness.emit_insight") as emit_mock:
            survival_rebuy_awareness.handle_journal_event(no_rebuy_event)
            survival_rebuy_awareness.handle_journal_event(no_rebuy_event)

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.SURVIVAL_REBUY_CRITICAL")
        self.assertEqual(kwargs.get("priority"), "P0_CRITICAL")

    def test_cross_module_priority_is_deterministic(self) -> None:
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
                dedup_key="f4:quality:summary",
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
                dedup_key="f4:quality:cashin",
                cooldown_scope="entity",
                cooldown_seconds=90.0,
            )

        self.assertTrue(summary_ok)
        self.assertTrue(cash_ok)
        second_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
        self.assertEqual(second_ctx.get("voice_priority_reason"), "cross_module_preempt_higher_force")
        self.assertTrue(bool(second_ctx.get("voice_priority_forced")))


if __name__ == "__main__":
    unittest.main()

