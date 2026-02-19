from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.context_state_contract import default_state_contract
from logic.events import exploration_bio_events as bio_events


class F10ExobioSampleContinuityTests(unittest.TestCase):
    def test_sample_count_persists_across_restart_for_1_to_2_flow(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_exobio_continuity.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())
                bio_events.reset_bio_flags(persist=True)

                event = {
                    "event": "ScanOrganic",
                    "StarSystem": "F10_EXOBIO_SYSTEM",
                    "BodyName": "F10_EXOBIO_BODY_A",
                    "Species_Localised": "Aleoida Arcus",
                }
                key = ("f10_exobio_system", "f10_exobio_body_a", "aleoida arcus")

                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(12345.0, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event, gui_ref=None)
                    sample_calls = [
                        call
                        for call in emit_mock.call_args_list
                        if call.kwargs.get("message_id") == "MSG.EXOBIO_SAMPLE_LOGGED"
                    ]
                    self.assertEqual(len(sample_calls), 1)
                    self.assertIn("Pierwsza próbka", str(sample_calls[0].args[0]))

                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)

                # Simulated restart: runtime memory is gone, persisted state should restore continuity.
                bio_events.reset_bio_flags()
                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 0)
                load_stats = bio_events.load_exobio_state_from_contract(force=True)
                self.assertTrue(bool(load_stats.get("loaded")))
                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)

                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(12345.0, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event, gui_ref=None)
                    sample_calls = [
                        call
                        for call in emit_mock.call_args_list
                        if call.kwargs.get("message_id") == "MSG.EXOBIO_SAMPLE_LOGGED"
                    ]
                    self.assertEqual(len(sample_calls), 1)
                    self.assertIn("Druga próbka", str(sample_calls[0].args[0]))

                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 2)
            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_recovery_from_journal_uses_neutral_wording_when_sequence_is_uncertain(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_exobio_recovery.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())
                bio_events.reset_bio_flags(persist=True)
                app_state.current_system = "F10_EXOBIO_RECOVERY_SYSTEM"

                # Recovery line without StarSystem and with numeric body token -> uncertain numbering.
                lines = [
                    json.dumps({"event": "Location", "StarSystem": "F10_EXOBIO_RECOVERY_SYSTEM"}),
                    json.dumps(
                        {
                            "event": "ScanOrganic",
                            "BodyID": 5,
                            "Species_Localised": "Aleoida Arcus",
                        }
                    ),
                ]
                recovery_stats = bio_events.recover_exobio_from_journal_lines(lines, persist=True)
                self.assertTrue(bool(recovery_stats.get("recovered")))
                key = ("f10_exobio_recovery_system", "5", "aleoida arcus")
                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)
                self.assertIn(key, bio_events.EXOBIO_RECOVERY_UNCERTAIN_KEYS)

                next_event = {
                    "event": "ScanOrganic",
                    "BodyID": 5,
                    "Species_Localised": "Aleoida Arcus",
                }
                with patch("logic.events.exploration_bio_events.emit_insight") as emit_mock:
                    bio_events.handle_exobio_progress(next_event, gui_ref=None)
                    sample_calls = [
                        call
                        for call in emit_mock.call_args_list
                        if call.kwargs.get("message_id") == "MSG.EXOBIO_SAMPLE_LOGGED"
                    ]
                    self.assertEqual(len(sample_calls), 1)
                    self.assertIn("Kolejna próbka", str(sample_calls[0].args[0]))
            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_main_loop_bootstrap_contains_exobio_recovery_hook(self) -> None:
        project_root = os.path.dirname(os.path.dirname(__file__))
        main_loop_path = os.path.join(project_root, "app", "main_loop.py")
        with open(main_loop_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
        self.assertIn("bootstrap_exobio_state_from_journal_lines", content)


if __name__ == "__main__":
    unittest.main()
