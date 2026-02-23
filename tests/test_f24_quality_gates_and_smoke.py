from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_awareness as awareness
from logic.events import exploration_bio_events as bio_events
from logic.events import exploration_fss_events as fss_events
from logic.events import exploration_summary
from logic.exit_summary import ExitSummaryData


class F24QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_summary_sig = getattr(app_state, "last_exploration_summary_signature", None)
        self._saved_cash_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_cash_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.current_system = "F24_QG_SYSTEM"
        app_state.last_exploration_summary_signature = None
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        awareness.reset_exploration_awareness()
        bio_events.reset_bio_flags()
        fss_events.reset_fss_progress()

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_exploration_summary_signature = self._saved_summary_sig
        app_state.last_cash_in_signature = self._saved_cash_sig
        app_state.cash_in_skip_signature = self._saved_cash_skip_sig
        awareness.reset_exploration_awareness()
        bio_events.reset_bio_flags()
        fss_events.reset_fss_progress()

    @staticmethod
    def _summary_data() -> ExitSummaryData:
        return ExitSummaryData(
            system_name="F24_QG_SYSTEM",
            scanned_bodies=9,
            total_bodies=9,
            elw_count=0,
            elw_value=0.0,
            ww_count=0,
            ww_value=0.0,
            ww_t_count=0,
            ww_t_value=0.0,
            hmc_t_count=0,
            hmc_t_value=0.0,
            biology_species_count=4,
            biology_value=10_000_000.0,
            bonus_discovery=0.0,
            c_cartography=2_500_000.0,
            c_exobiology=10_000_000.0,
            total_value=12_500_000.0,
        )

    def test_smoke_f24_full_scan_text_is_correct_and_wires_summary(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 3
        fss_events.FSS_DISCOVERED = 3
        fss_events.FSS_FULL_WARNED = False

        with (
            patch("logic.events.exploration_fss_events.DEBOUNCER.can_send", return_value=True),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch("logic.events.exploration_fss_events._wire_exit_summary_to_runtime") as summary_wire,
        ):
            ok = fss_events._maybe_speak_fss_full(gui_ref=None)

        self.assertTrue(ok)
        self.assertTrue(summary_wire.called)
        self.assertEqual(emit_mock.call_count, 1)
        self.assertEqual(str(emit_mock.call_args.kwargs.get("message_id") or ""), "MSG.SYSTEM_FULLY_SCANNED")
        self.assertEqual(str(emit_mock.call_args.args[0] or ""), "System w pe\u0142ni przeskanowany.")

    def test_smoke_f24_required_bio_callout_bypasses_awareness_limits(self) -> None:
        def _cfg(key: str, default=None):
            if key == "exploration.awareness.max_callouts_per_system":
                return 0
            if key == "exploration.awareness.max_callouts_per_session":
                return 0
            return default

        ev = {
            "event": "SAASignalsFound",
            "StarSystem": "F24_QG_SYSTEM",
            "BodyName": "F24_QG_SYSTEM A 2",
            "Signals": [{"Type": "Biological", "Count": 4}],
        }
        with (
            patch("logic.events.exploration_awareness.config.get", side_effect=_cfg),
            patch("logic.events.exploration_awareness.emit_insight") as emit_mock,
        ):
            bio_events.handle_dss_bio_signals(ev, gui_ref=None)

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.BIO_SIGNALS_HIGH")
        self.assertIn("Planeta F24_QG_SYSTEM A 2", str(kwargs.get("context", {}).get("raw_text") or kwargs.get("text") or ""))
        snap = awareness.get_awareness_snapshot("F24_QG_SYSTEM")
        self.assertEqual(int(snap.get("callouts_emitted") or 0), 0)
        self.assertFalse(bool(snap.get("summary_emitted")))

    def test_smoke_f24_auto_summary_keeps_cashin_panel_but_suppresses_followup_tts(self) -> None:
        sample = self._summary_data()
        with (
            patch.object(app_state.exit_summary, "build_summary_data", return_value=sample),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 18_000_000.0}),
            ),
            patch("logic.events.exploration_summary.emit_insight") as summary_emit,
            patch("logic.events.cash_in_assistant.emit_insight") as cash_emit,
        ):
            ok = exploration_summary.trigger_exploration_summary(mode="auto")

        self.assertTrue(ok)
        self.assertEqual(summary_emit.call_count, 1)
        self.assertEqual(cash_emit.call_count, 1)
        cash_ctx = dict(cash_emit.call_args.kwargs.get("context") or {})
        self.assertTrue(bool(cash_ctx.get("suppress_tts")))
        self.assertEqual(cash_ctx.get("voice_sequence_reason"), "after_exploration_summary")
        summary_ctx = dict(summary_emit.call_args.kwargs.get("context") or {})
        summary_payload = dict(summary_ctx.get("summary_payload") or {})
        self.assertEqual(str(summary_payload.get("next_step") or ""), "Ten system wymaga dog\u0142\u0119bnej analizy")


if __name__ == "__main__":
    unittest.main()
