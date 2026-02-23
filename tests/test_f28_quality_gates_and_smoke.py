from __future__ import annotations

import json
import unittest

from app.state import app_state
from logic.events.exploration_value_recovery import recover_system_value_from_journal_lines
from logic.system_value_engine import SystemValueEngine
from logic.tts.text_preprocessor import prepare_tts


class F28QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_engine = getattr(app_state, "system_value_engine", None)

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.system_value_engine = self._saved_engine

    def test_smoke_f28_exploration_summary_text_and_number_verbalization(self) -> None:
        text = prepare_tts(
            "MSG.CASH_IN_ASSISTANT",
            {"raw_text": "Podsumowanie gotowe. Dane warte 132 555 000 Cr. Rozwaz ladowanie pod exobio."},
        ) or ""
        lowered = text.lower()
        self.assertIn("podsumowanie gotowe", lowered)
        self.assertIn("rozważ", lowered)
        self.assertIn("exobio", lowered)
        self.assertIn("sto trzydzieści dwa", lowered)
        self.assertIn("kredyt", lowered)

    def test_smoke_f28_route_progress_wording_and_percent_verbalization(self) -> None:
        text = prepare_tts(
            "MSG.RUNTIME_CRITICAL",
            {"raw_text": "Do boosta. 25% drogi."},
        ) or ""
        lowered = text.lower()
        self.assertIn("do boosta", lowered)
        self.assertIn("dwadzieścia pięć procent", lowered)
        self.assertIn("drogi", lowered)

    def test_smoke_f28_star_cartography_and_recovery_diagnostics(self) -> None:
        src_engine = self._saved_engine
        self.assertIsNotNone(src_engine)
        engine = SystemValueEngine((src_engine.exobio_df, src_engine.carto_df))
        app_state.system_value_engine = engine
        app_state.current_system = "F28_STAR_RECOVERY_SYS"
        engine.set_current_system("F28_STAR_RECOVERY_SYS")

        lines = [
            json.dumps({"event": "Location", "StarSystem": "F28_STAR_RECOVERY_SYS"}),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "F28_STAR_RECOVERY_SYS",
                    "BodyName": "F28_STAR_RECOVERY_SYS A",
                    "BodyType": "Star",
                    "StarType": "K",
                    "WasDiscovered": False,
                    "WasMapped": False,
                }
            ),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "F28_STAR_RECOVERY_SYS",
                    "BodyName": "F28_STAR_RECOVERY_SYS B",
                    "BodyType": "Star",
                    "StarType": "UnknownX",
                    "WasDiscovered": True,
                    "WasMapped": False,
                }
            ),
        ]

        stats = recover_system_value_from_journal_lines(lines, max_lines=200)
        totals = engine.calculate_totals()
        diag = engine.get_runtime_diagnostics()

        self.assertTrue(bool(stats.get("recovered")))
        self.assertGreaterEqual(int(stats.get("scan_events") or 0), 2)
        self.assertGreater(float(totals.get("c_cartography") or 0.0), 0.0)
        self.assertGreaterEqual(int(diag.get("scan_star_counted") or 0), 1)
        self.assertGreaterEqual(int(diag.get("scan_star_skipped_unmapped") or 0), 1)


if __name__ == "__main__":
    unittest.main()
