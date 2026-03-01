from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_bio_events as bio_events


class F36ExobioSampleMessageIdSequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags()
        app_state.current_system = "F36_EXOBIO_SEQ_SYS"

    def tearDown(self) -> None:
        bio_events.reset_bio_flags()

    def test_scanorganic_sequence_uses_dedicated_message_ids_and_first_is_not_kolejna(self) -> None:
        event = {
            "event": "ScanOrganic",
            # Intentionally omit StarSystem and use numeric BodyID to emulate uncertain payload.
            "BodyID": 42,
            "Species_Localised": "Aleoida Arcus",
        }

        with (
            patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
            patch(
                "logic.events.exploration_bio_events._estimate_collected_species_value",
                return_value=(123456.0, False),
            ),
        ):
            bio_events.handle_exobio_progress(event, gui_ref=None)  # 1/3
            bio_events.handle_exobio_progress(event, gui_ref=None)  # 2/3
            bio_events.handle_exobio_progress(event, gui_ref=None)  # 3/3

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

        self.assertIn("Nowy wpis biologiczny", texts[0])
        self.assertNotIn("Kolejna próbka", texts[0])

        completion_kwargs = dict(progress_calls[-1].kwargs)
        self.assertEqual(str(completion_kwargs.get("priority") or ""), "P1_HIGH")
        completion_ctx = dict(completion_kwargs.get("context") or {})
        self.assertTrue(bool(completion_ctx.get("bypass_priority_matrix")))


if __name__ == "__main__":
    unittest.main()

