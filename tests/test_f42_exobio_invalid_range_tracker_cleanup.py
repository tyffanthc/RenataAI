from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_bio_events as bio_events


class F42ExobioInvalidRangeTrackerCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags(persist=False)
        app_state.current_system = "F42_EXOBIO_SYS"

    def tearDown(self) -> None:
        bio_events.reset_bio_flags(persist=False)

    def test_invalid_non_pending_tracker_is_dropped_and_logged(self) -> None:
        key = ("f42_exobio_sys", "f42_body_a", "aleoida arcus")
        bio_events.EXOBIO_SAMPLE_COUNT[key] = 1
        bio_events.EXOBIO_RANGE_TRACKERS[key] = {
            "lat": None,  # broken baseline
            "lon": 0.0,
            "radius_m": 6_371_000.0,
            "threshold_m": 100.0,
            "pending": False,
            "body": "f42_body_a",
            "system": "f42_exobio_sys",
        }

        with (
            patch("logic.events.exploration_bio_events.log_event_throttled") as log_throttled,
            patch("logic.events.exploration_bio_events._persist_exobio_state") as persist_mock,
            patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
        ):
            bio_events.handle_exobio_status_position(
                {
                    "Latitude": 0.0,
                    "Longitude": 0.001,
                    "PlanetRadius": 6_371_000.0,
                    "BodyName": "F42_BODY_A",
                },
                gui_ref=None,
            )

        self.assertNotIn(key, bio_events.EXOBIO_RANGE_TRACKERS)
        emit_mock.assert_not_called()
        persist_mock.assert_called()
        log_throttled.assert_called()
        args = log_throttled.call_args.args
        self.assertIn("RANGE_TRACKER_INVALID", str(args[0]))
        self.assertIn("Dropped invalid exobio range tracker", str(args[3]))


if __name__ == "__main__":
    unittest.main()
