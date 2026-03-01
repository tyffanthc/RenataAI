from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.exit_summary import ExitSummaryData
from logic.events import exploration_bio_events as bio_events
from logic.events import exploration_summary


class F24ExplorationExobioLandingCalloutsCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags()

    def test_dss_bio_signals_emits_low_count_landing_hint_with_body_name(self) -> None:
        ev = {
            "event": "SAASignalsFound",
            "StarSystem": "F24_EXO_SYSTEM",
            "BodyName": "F24_EXO_SYSTEM A 2",
            "Signals": [{"Type": "Biological", "Count": 2}],
        }
        with patch("logic.events.exploration_bio_events.emit_callout_or_summary") as emit_mock:
            bio_events.handle_dss_bio_signals(ev, gui_ref=None)

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.BIO_SIGNALS_HIGH")
        self.assertIn("Planeta A 2", str(kwargs.get("text") or ""))
        self.assertIn("mało sygnałów biologicznych", str(kwargs.get("text") or ""))

    def test_dss_bio_signals_emits_high_count_landing_hint_with_body_name(self) -> None:
        ev = {
            "event": "SAASignalsFound",
            "StarSystem": "F24_EXO_SYSTEM",
            "BodyName": "F24_EXO_SYSTEM A 3",
            "Signals": [{"Type": "Biological", "Count": 4}],
        }
        with patch("logic.events.exploration_bio_events.emit_callout_or_summary") as emit_mock:
            bio_events.handle_dss_bio_signals(ev, gui_ref=None)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertIn("Planeta A 3", str(emit_mock.call_args.kwargs.get("text") or ""))
        self.assertIn("liczne sygnały biologiczne", str(emit_mock.call_args.kwargs.get("text") or ""))

    def test_system_quality_hint_classifies_zero_few_and_many_targets(self) -> None:
        zero = ExitSummaryData(system_name="A", total_value=0.0)
        few = ExitSummaryData(system_name="B", biology_species_count=2, biology_value=1_000_000.0, total_value=1_000_000.0)
        many = ExitSummaryData(system_name="C", biology_species_count=4, biology_value=6_000_000.0, total_value=6_000_000.0)

        self.assertEqual(exploration_summary._pick_system_quality_hint(zero), "Tutaj nie ma nic wartościowego")  # noqa: SLF001
        self.assertEqual(exploration_summary._pick_system_quality_hint(few), "Mało obiektów badawczych")  # noqa: SLF001
        self.assertEqual(exploration_summary._pick_system_quality_hint(many), "Ten system wymaga dogłębnej analizy")  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()

