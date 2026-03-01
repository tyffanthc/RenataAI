from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from app.state import app_state
from logic.events import exploration_dss_events as dss_events


class F3DssHelperCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        dss_events.reset_dss_helper_state()
        app_state.current_system = "SMOKE_DSS_SYSTEM"

    def test_completion_is_emitted_once_per_body(self) -> None:
        event = {
            "event": "SAAScanComplete",
            "BodyName": "SMOKE_DSS_BODY_A",
            "ProbesUsed": 4,
            "EfficiencyTarget": 6,
        }

        with patch("logic.events.exploration_dss_events.emit_insight") as emit_mock:
            dss_events.handle_dss_scan_complete(event, gui_ref=None)
            dss_events.handle_dss_scan_complete(event, gui_ref=None)

        ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertEqual(ids.count("MSG.DSS_COMPLETED"), 1)
        self.assertEqual(ids.count("MSG.DSS_PROGRESS"), 1)  # first milestone only once

    def test_progress_milestones_are_sparse(self) -> None:
        with patch("logic.events.exploration_dss_events.emit_insight") as emit_mock:
            for idx in range(1, 7):
                dss_events.handle_dss_scan_complete(
                    {
                        "event": "SAAScanComplete",
                        "BodyName": f"SMOKE_DSS_BODY_{idx}",
                        "ProbesUsed": 6,
                        "EfficiencyTarget": 6,
                    },
                    gui_ref=None,
                )

        ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertEqual(ids.count("MSG.DSS_COMPLETED"), 6)
        self.assertEqual(ids.count("MSG.DSS_PROGRESS"), 3)  # milestones: 1,3,5

    def test_first_mapped_emits_only_when_confirmed(self) -> None:
        with patch("logic.events.exploration_dss_events.emit_insight") as emit_mock:
            dss_events.handle_dss_scan_complete(
                {
                    "event": "SAAScanComplete",
                    "BodyName": "SMOKE_DSS_FIRST_MAPPED_1",
                    "WasMapped": False,
                },
                gui_ref=None,
            )
            dss_events.handle_dss_scan_complete(
                {
                    "event": "SAAScanComplete",
                    "BodyName": "SMOKE_DSS_FIRST_MAPPED_2",
                    "WasMapped": True,
                },
                gui_ref=None,
            )

        ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertEqual(ids.count("MSG.FIRST_MAPPED"), 1)

    def test_dss_target_hint_uses_value_threshold_and_dedup(self) -> None:
        gui_ref = SimpleNamespace(
            carto_df=pd.DataFrame(
                [
                    {
                        "Body_Type": "rocky body",
                        "Terraformable": "No",
                        "DSS_Mapped_Value": 900000,
                    }
                ]
            )
        )
        event = {
            "event": "Scan",
            "BodyName": "SMOKE_DSS_TARGET_1",
            "PlanetClass": "Rocky body",
            "WasMapped": False,
        }

        with (
            patch("logic.events.exploration_dss_events.emit_callout_or_summary") as callout_mock,
            patch("logic.events.exploration_dss_events.config.get", return_value=600000),
        ):
            dss_events.handle_dss_target_hint(event, gui_ref=gui_ref)
            dss_events.handle_dss_target_hint(event, gui_ref=gui_ref)

        self.assertEqual(callout_mock.call_count, 1)
        self.assertEqual(callout_mock.call_args.kwargs.get("message_id"), "MSG.DSS_TARGET_HINT")

    def test_completion_carries_combat_context_flags(self) -> None:
        with patch("logic.events.exploration_dss_events.emit_insight") as emit_mock:
            dss_events.handle_dss_scan_complete(
                {
                    "event": "SAAScanComplete",
                    "BodyName": "SMOKE_DSS_COMBAT_BODY",
                    "in_combat": True,
                    "combat_state": "active",
                },
                gui_ref=None,
            )

        completion_calls = [
            call for call in emit_mock.call_args_list if call.kwargs.get("message_id") == "MSG.DSS_COMPLETED"
        ]
        self.assertEqual(len(completion_calls), 1)
        ctx = completion_calls[0].kwargs.get("context") or {}
        self.assertTrue(ctx.get("in_combat"))
        self.assertEqual(ctx.get("combat_state"), "active")

    def test_dss_completed_text_uses_short_body_name(self) -> None:
        with patch("logic.events.exploration_dss_events.emit_insight") as emit_mock:
            dss_events.handle_dss_scan_complete(
                {
                    "event": "SAAScanComplete",
                    "StarSystem": "SMOKE_DSS_SYSTEM",
                    "BodyName": "SMOKE_DSS_SYSTEM A 3",
                    "ProbesUsed": 4,
                    "EfficiencyTarget": 8,
                },
                gui_ref=None,
            )

        completion_calls = [
            call for call in emit_mock.call_args_list if call.kwargs.get("message_id") == "MSG.DSS_COMPLETED"
        ]
        self.assertEqual(len(completion_calls), 1)
        ctx = completion_calls[0].kwargs.get("context") or {}
        raw_text = str(ctx.get("raw_text") or "")
        self.assertIn("A 3", raw_text)
        self.assertNotIn("SMOKE_DSS_SYSTEM A 3", raw_text)

    def test_first_mapped_text_uses_short_body_name(self) -> None:
        with patch("logic.events.exploration_dss_events.emit_insight") as emit_mock:
            dss_events.handle_dss_scan_complete(
                {
                    "event": "SAAScanComplete",
                    "StarSystem": "SMOKE_DSS_SYSTEM",
                    "BodyName": "SMOKE_DSS_SYSTEM A 5",
                    "WasMapped": False,
                },
                gui_ref=None,
            )

        first_mapped_calls = [call for call in emit_mock.call_args_list if call.kwargs.get("message_id") == "MSG.FIRST_MAPPED"]
        self.assertEqual(len(first_mapped_calls), 1)
        ctx = first_mapped_calls[0].kwargs.get("context") or {}
        raw_text = str(ctx.get("raw_text") or "")
        self.assertIn("A 5", raw_text)
        self.assertNotIn("SMOKE_DSS_SYSTEM A 5", raw_text)


if __name__ == "__main__":
    unittest.main()
