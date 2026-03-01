from __future__ import annotations

import json
import unittest

from app.state import app_state
from logic.events import exploration_bio_events as bio_events


class F36ExobioRecoveryCanonicalBodyKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags()
        app_state.current_system = "F36_RECOVERY_SYS"

    def tearDown(self) -> None:
        bio_events.reset_bio_flags()

    def test_recovery_uses_runtime_canonical_body_key_for_numeric_scanorganic(self) -> None:
        # Provide persisted-like status body context used by _canonical_body_for_key.
        bio_events.EXOBIO_LAST_STATUS_POS.update(
            {
                "body": "f36_recovery_sys a 1",
                "system": "f36_recovery_sys",
                "lat": 0.0,
                "lon": 0.0,
                "radius_m": 1_000_000.0,
                # ts omitted on purpose -> canonical helper treats it as persisted state sentinel.
            }
        )

        lines = [
            json.dumps({"event": "Location", "StarSystem": "F36_RECOVERY_SYS"}),
            json.dumps(
                {
                    "event": "ScanOrganic",
                    "BodyID": 7,
                    "Species_Localised": "Aleoida Arcus",
                }
            ),
        ]

        out = bio_events.recover_exobio_from_journal_lines(lines, persist=False)
        self.assertTrue(bool(out.get("recovered")))
        canonical_key = ("f36_recovery_sys", "f36_recovery_sys a 1", "aleoida arcus")
        numeric_key = ("f36_recovery_sys", "7", "aleoida arcus")

        self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(canonical_key, 0)), 1)
        self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(numeric_key, 0)), 0)


if __name__ == "__main__":
    unittest.main()

