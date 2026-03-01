from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_bio_events as bio_events


class F3ExobioHelperProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags()
        app_state.current_system = "SMOKE_EXOBIO_F3_SYSTEM"

    def test_sample_progress_1_2_3_and_completion_stop(self) -> None:
        event = {
            "event": "ScanOrganic",
            "StarSystem": "SMOKE_EXOBIO_F3_SYSTEM",
            "BodyName": "SMOKE_EXOBIO_BODY_A",
            "Species_Localised": "Aleoida Arcus",
        }

        with (
            patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
            patch(
                "logic.events.exploration_bio_events._estimate_collected_species_value",
                return_value=(12345.0, False),
            ),
        ):
            bio_events.handle_exobio_progress(event, gui_ref=None)
            bio_events.handle_exobio_progress(event, gui_ref=None)
            bio_events.handle_exobio_progress(event, gui_ref=None)
            bio_events.handle_exobio_progress(event, gui_ref=None)  # no extra after 3/3

        progress_calls = [
            call
            for call in emit_mock.call_args_list
            if str(call.kwargs.get("message_id") or "")
            in {"MSG.EXOBIO_NEW_ENTRY", "MSG.EXOBIO_SAMPLE_LOGGED", "MSG.EXOBIO_SPECIES_COMPLETE"}
        ]
        self.assertEqual(len(progress_calls), 3)
        ids = [str(call.kwargs.get("message_id") or "") for call in progress_calls]
        texts = [str(call.args[0]) for call in progress_calls]
        self.assertEqual(ids, ["MSG.EXOBIO_NEW_ENTRY", "MSG.EXOBIO_SAMPLE_LOGGED", "MSG.EXOBIO_SPECIES_COMPLETE"])
        self.assertIn("Pierwsza", texts[0])
        self.assertIn("Druga", texts[1])
        self.assertIn("Mamy wszystko", texts[2])

    def test_ready_fire_once_per_cycle_retries_after_combat_silence_block(self) -> None:
        key = ("smoke_exobio_f3_system", "smoke_exobio_body_b", "aleoida arcus")
        bio_events.EXOBIO_SAMPLE_COUNT[key] = 1
        bio_events.EXOBIO_RANGE_TRACKERS[key] = {
            "lat": 0.0,
            "lon": 0.0,
            "radius_m": 6_371_000.0,
            "threshold_m": 100.0,
            "pending": False,
            "body": "smoke_exobio_body_b",
        }

        # First call suppressed (combat silence), second should retry and emit.
        with patch("logic.events.exploration_bio_events.emit_insight", side_effect=[False, True]) as emit_mock:
            bio_events.handle_exobio_status_position(
                {
                    "Latitude": 0.0,
                    "Longitude": 0.002,
                    "PlanetRadius": 6_371_000.0,
                    "BodyName": "SMOKE_EXOBIO_BODY_B",
                    "in_combat": True,
                },
                gui_ref=None,
            )
            self.assertNotIn(key, bio_events.EXOBIO_RANGE_READY_WARNED)

            bio_events.handle_exobio_status_position(
                {
                    "Latitude": 0.0,
                    "Longitude": 0.0022,
                    "PlanetRadius": 6_371_000.0,
                    "BodyName": "SMOKE_EXOBIO_BODY_B",
                },
                gui_ref=None,
            )

        ready_calls = [
            call for call in emit_mock.call_args_list if call.kwargs.get("message_id") == "MSG.EXOBIO_RANGE_READY"
        ]
        self.assertEqual(len(ready_calls), 2)
        self.assertIn(key, bio_events.EXOBIO_RANGE_READY_WARNED)

    def test_codex_new_entry_is_deduped_per_system_species(self) -> None:
        event = {
            "event": "CodexEntry",
            "StarSystem": "SMOKE_EXOBIO_F3_SYSTEM",
            "BodyName": "SMOKE_EXOBIO_BODY_C",
            "Category": "Biology",
            "Name_Localised": "Cactoida Cortexum",
            "IsNewEntry": True,
        }

        with patch("logic.events.exploration_bio_events.emit_insight") as emit_mock:
            bio_events.handle_exobio_progress(event, gui_ref=None)
            bio_events.handle_exobio_progress(event, gui_ref=None)

        codex_calls = [
            call for call in emit_mock.call_args_list if call.kwargs.get("message_id") == "MSG.EXOBIO_NEW_ENTRY"
        ]
        self.assertEqual(len(codex_calls), 1)


if __name__ == "__main__":
    unittest.main()
