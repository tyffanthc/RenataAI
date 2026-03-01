from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.context_state_contract import default_state_contract
from logic.events import exploration_bio_events as bio_events


def _fresh_contract(path: str) -> None:
    config.STATE_FILE = path
    config.save_state_contract(default_state_contract())
    bio_events.reset_bio_flags(persist=True)


def _sample_messages(emit_mock) -> list[str]:
    return [
        str(call.args[0])
        for call in emit_mock.call_args_list
        if str(call.kwargs.get("message_id") or "")
        in {"MSG.EXOBIO_NEW_ENTRY", "MSG.EXOBIO_SAMPLE_LOGGED", "MSG.EXOBIO_SPECIES_COMPLETE"}
    ]


class F30ExobioPowerlossStateRestoreAnd3of3SummaryTests(unittest.TestCase):
    def test_powerloss_restart_keeps_progress_tracker_and_allows_3of3_completion(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        old_system = str(getattr(app_state, "current_system", "") or "")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f30_exobio_powerloss_state.json")
            try:
                _fresh_contract(tmp_path)
                app_state.current_system = "F30 Exo System"

                sample_event = {
                    "event": "ScanOrganic",
                    "StarSystem": "F30 Exo System",
                    "BodyName": "F30 Exo System 1 A",
                    "Species_Localised": "Aleoida Arcus",
                }
                key = ("f30 exo system", "f30 exo system 1 a", "aleoida arcus")

                # Seed live status so tracker can arm from first sample.
                bio_events.handle_exobio_status_position(
                    {
                        "Latitude": 0.0,
                        "Longitude": 0.0,
                        "PlanetRadius": 1_000_000.0,
                        "BodyName": "F30 Exo System 1 A",
                    }
                )

                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
                    patch(
                        "logic.events.exploration_bio_events._species_minimum_distance",
                        return_value=500.0,
                    ),
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(sample_event, gui_ref=None)
                    self.assertEqual(len(_sample_messages(emit_mock)), 1)

                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)
                self.assertIn(key, bio_events.EXOBIO_RANGE_TRACKERS)

                # Simulate hard restart/power-loss and state restore.
                bio_events.reset_bio_flags()
                load_stats = bio_events.load_exobio_state_from_contract(force=True)
                self.assertTrue(bool(load_stats.get("loaded")))
                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)
                self.assertIn(key, bio_events.EXOBIO_RANGE_TRACKERS)

                # Move enough distance after restart -> range-ready callout should emit.
                with patch("logic.events.exploration_bio_events.emit_insight") as emit_mock:
                    bio_events.handle_exobio_status_position(
                        {
                            "Latitude": 0.0,
                            "Longitude": 1.0,
                            "PlanetRadius": 1_000_000.0,
                            "BodyName": "F30 Exo System 1 A",
                        }
                    )
                    ready_calls = [
                        c
                        for c in emit_mock.call_args_list
                        if str(c.kwargs.get("message_id") or "") == "MSG.EXOBIO_RANGE_READY"
                    ]
                    self.assertEqual(len(ready_calls), 1)

                # Continue sampling after restart and finish 3/3 with completion summary.
                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
                    patch(
                        "logic.events.exploration_bio_events._species_minimum_distance",
                        return_value=500.0,
                    ),
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        side_effect=[(None, False), (42000.0, False)],
                    ),
                ):
                    bio_events.handle_exobio_progress(sample_event, gui_ref=None)  # 2/3
                    bio_events.handle_exobio_progress(sample_event, gui_ref=None)  # 3/3
                    msgs = _sample_messages(emit_mock)
                    self.assertGreaterEqual(len(msgs), 2)
                    self.assertTrue(any("Mamy wszystko" in m for m in msgs))

                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 3)
                self.assertIn(key, bio_events.EXOBIO_SAMPLE_COMPLETE)

            finally:
                bio_events.reset_bio_flags()
                app_state.current_system = old_system
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)


if __name__ == "__main__":
    unittest.main()
