from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.exit_summary import ExitSummaryData
from logic.events import exploration_summary


class F4ExplorationSummaryBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_signature = getattr(app_state, "last_exploration_summary_signature", None)
        self._saved_cash_in_signature = getattr(app_state, "last_cash_in_signature", None)
        self._saved_cash_in_skip_signature = getattr(app_state, "cash_in_skip_signature", None)
        app_state.current_system = "F4_SUMMARY_TEST_SYSTEM"
        app_state.last_exploration_summary_signature = None
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_exploration_summary_signature = self._saved_signature
        app_state.last_cash_in_signature = self._saved_cash_in_signature
        app_state.cash_in_skip_signature = self._saved_cash_in_skip_signature

    @staticmethod
    def _sample_data() -> ExitSummaryData:
        return ExitSummaryData(
            system_name="F4_SUMMARY_TEST_SYSTEM",
            scanned_bodies=10,
            total_bodies=12,
            elw_count=1,
            elw_value=25_000_000.0,
            ww_count=1,
            ww_value=4_200_000.0,
            ww_t_count=1,
            ww_t_value=4_200_000.0,
            hmc_t_count=1,
            hmc_t_value=2_000_000.0,
            biology_species_count=2,
            biology_value=6_000_000.0,
            bonus_discovery=1_000_000.0,
            c_cartography=31_000_000.0,
            c_exobiology=6_000_000.0,
            total_value=38_000_000.0,
        )

    def test_manual_trigger_emits_summary_with_payload_and_microcopy(self) -> None:
        data = self._sample_data()
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=data),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 77_500_000.0}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as emit_mock,
        ):
            ok = exploration_summary.trigger_exploration_summary(mode="manual")

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.EXPLORATION_SYSTEM_SUMMARY")
        self.assertEqual(kwargs.get("event_type"), "SYSTEM_SUMMARY")
        self.assertEqual(kwargs.get("priority"), "P3_LOW")
        self.assertEqual(float(kwargs.get("cooldown_seconds") or 0.0), 0.0)
        ctx = dict(kwargs.get("context") or {})
        self.assertIn("raw_text", ctx)
        self.assertIn("summary_payload", ctx)
        self.assertTrue(bool(ctx.get("force_tts")))
        raw_text = str(ctx.get("raw_text") or "")
        self.assertIn("Podsumowanie gotowe.", raw_text)
        self.assertIn("Dane warte", raw_text)
        payload = dict(ctx.get("summary_payload") or {})
        self.assertEqual(payload.get("system"), "F4_SUMMARY_TEST_SYSTEM")
        self.assertTrue(bool(payload.get("highlights")))
        self.assertTrue(bool(payload.get("next_step")))
        self.assertIn("cash_in_signal", payload)

    def test_auto_trigger_is_guarded_by_signature_change(self) -> None:
        data = self._sample_data()
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=data),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 77_500_000.0}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as emit_mock,
        ):
            first = exploration_summary.trigger_exploration_summary(mode="auto")
            second = exploration_summary.trigger_exploration_summary(mode="auto")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(emit_mock.call_count, 1)

    def test_manual_trigger_handles_nan_values_without_crash(self) -> None:
        data = self._sample_data()
        data.total_value = float("nan")
        data.bonus_discovery = float("nan")
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=data),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": float("nan")}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as emit_mock,
        ):
            ok = exploration_summary.trigger_exploration_summary(mode="manual")

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        ctx = dict(kwargs.get("context") or {})
        payload = dict(ctx.get("summary_payload") or {})
        self.assertEqual(float(payload.get("cash_in_system_estimated") or 0.0), 0.0)
        self.assertEqual(float(payload.get("cash_in_session_estimated") or 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
