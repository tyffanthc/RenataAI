from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from logic.events import exploration_high_value_events as hv_events


class F30HighValueDedupePerBodyTests(unittest.TestCase):
    def setUp(self) -> None:
        hv_events.reset_high_value_flags()
        self.gui_ref = SimpleNamespace(
            carto_df=pd.DataFrame(
                [
                    {"Body_Type": "earth-like world", "Terraformable": "No"},
                    {"Body_Type": "water world", "Terraformable": "No"},
                    {"Body_Type": "high metal content world", "Terraformable": "Yes"},
                ]
            )
        )

    def tearDown(self) -> None:
        hv_events.reset_high_value_flags()

    def test_high_value_hint_emits_for_each_unique_body_id(self) -> None:
        with patch("logic.events.exploration_high_value_events.emit_callout_or_summary") as emit_mock:
            hv_events.check_high_value_planet(
                {"BodyID": 101, "BodyName": "SYS A 1", "PlanetClass": "Earth-like world", "TerraformState": ""},
                gui_ref=self.gui_ref,
            )
            hv_events.check_high_value_planet(
                {"BodyID": 102, "BodyName": "SYS A 2", "PlanetClass": "Earth-like world", "TerraformState": ""},
                gui_ref=self.gui_ref,
            )

        self.assertEqual(emit_mock.call_count, 2)
        ids = [str(call.kwargs.get("message_id") or "") for call in emit_mock.call_args_list]
        self.assertEqual(ids, ["MSG.HIGH_VALUE_DSS_HINT", "MSG.HIGH_VALUE_DSS_HINT"])

    def test_high_value_hint_dedupes_same_body_id(self) -> None:
        with patch("logic.events.exploration_high_value_events.emit_callout_or_summary") as emit_mock:
            hv_events.check_high_value_planet(
                {"BodyID": 201, "BodyName": "SYS B 1", "PlanetClass": "Water world", "TerraformState": ""},
                gui_ref=self.gui_ref,
            )
            hv_events.check_high_value_planet(
                {"BodyID": 201, "BodyName": "SYS B 1", "PlanetClass": "Water world", "TerraformState": ""},
                gui_ref=self.gui_ref,
            )

        self.assertEqual(emit_mock.call_count, 1)
        self.assertEqual(str(emit_mock.call_args.kwargs.get("message_id") or ""), "MSG.HIGH_VALUE_DSS_HINT")


if __name__ == "__main__":
    unittest.main()
