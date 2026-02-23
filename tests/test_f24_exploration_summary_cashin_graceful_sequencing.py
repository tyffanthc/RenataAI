from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.exit_summary import ExitSummaryData
from logic.events import exploration_summary


class F24ExplorationSummaryCashinGracefulSequencingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_summary_sig = getattr(app_state, "last_exploration_summary_signature", None)
        self._saved_cash_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_cash_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.current_system = "F24_SEQ_SYSTEM"
        app_state.last_exploration_summary_signature = None
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_exploration_summary_signature = self._saved_summary_sig
        app_state.last_cash_in_signature = self._saved_cash_sig
        app_state.cash_in_skip_signature = self._saved_cash_skip_sig

    @staticmethod
    def _sample_data() -> ExitSummaryData:
        return ExitSummaryData(
            system_name="F24_SEQ_SYSTEM",
            scanned_bodies=8,
            total_bodies=8,
            elw_count=0,
            elw_value=0.0,
            ww_count=0,
            ww_value=0.0,
            ww_t_count=0,
            ww_t_value=0.0,
            hmc_t_count=0,
            hmc_t_value=0.0,
            biology_species_count=4,
            biology_value=12_000_000.0,
            bonus_discovery=0.0,
            c_cartography=3_500_000.0,
            c_exobiology=12_000_000.0,
            total_value=15_500_000.0,
        )

    def test_auto_summary_triggers_cashin_panel_but_suppresses_cashin_tts(self) -> None:
        sample = self._sample_data()
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=sample),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 20_000_000.0}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as summary_emit,
            patch("logic.events.cash_in_assistant.emit_insight") as cash_emit,
        ):
            ok = exploration_summary.trigger_exploration_summary(mode="auto")

        self.assertTrue(ok)
        self.assertEqual(summary_emit.call_count, 1)
        self.assertEqual(cash_emit.call_count, 1)
        ctx = dict(cash_emit.call_args.kwargs.get("context") or {})
        self.assertTrue(bool(ctx.get("suppress_tts")))
        self.assertEqual(ctx.get("voice_sequence_reason"), "after_exploration_summary")

    def test_manual_summary_keeps_cashin_tts_available(self) -> None:
        sample = self._sample_data()
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=sample),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 20_000_000.0}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as summary_emit,
            patch("logic.events.cash_in_assistant.emit_insight") as cash_emit,
        ):
            ok = exploration_summary.trigger_exploration_summary(mode="manual")

        self.assertTrue(ok)
        self.assertEqual(summary_emit.call_count, 1)
        self.assertEqual(cash_emit.call_count, 1)
        ctx = dict(cash_emit.call_args.kwargs.get("context") or {})
        self.assertFalse(bool(ctx.get("suppress_tts")))


if __name__ == "__main__":
    unittest.main()
