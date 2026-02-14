from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from app.state import app_state
from logic.insight_dispatcher import Insight, should_speak
from logic.events import exploration_awareness as awareness
from logic.events import exploration_bio_events as bio_events
from logic.events import exploration_dss_events as dss_events
from logic.events import exploration_fss_events as fss_events
from logic.events import exploration_high_value_events as high_value_events
from logic.events import exploration_misc_events as misc_events


class F3QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        app_state.current_system = "SMOKE_F3_QUALITY_SYSTEM"
        awareness.reset_exploration_awareness()
        fss_events.reset_fss_progress()
        bio_events.reset_bio_flags()
        dss_events.reset_dss_helper_state()
        high_value_events.reset_high_value_flags()
        misc_events.reset_footfall_flags()

    @staticmethod
    def _awareness_limits(max_per_system: int, max_per_session: int):
        def _getter(key: str, default=None):
            if key == "exploration.awareness.max_callouts_per_system":
                return max_per_system
            if key == "exploration.awareness.max_callouts_per_session":
                return max_per_session
            return default

        return _getter

    def _make_gui_ref(self) -> SimpleNamespace:
        return SimpleNamespace(
            carto_df=pd.DataFrame(
                [
                    {
                        "Body_Type": "earth-like world",
                        "Terraformable": "No",
                        "DSS_Mapped_Value": 1_500_000,
                    },
                    {
                        "Body_Type": "rocky body",
                        "Terraformable": "No",
                        "DSS_Mapped_Value": 900_000,
                    },
                ]
            )
        )

    def test_mixed_system_emits_single_summary_cross_module(self) -> None:
        gui_ref = self._make_gui_ref()

        with (
            patch(
                "logic.events.exploration_awareness.config.get",
                side_effect=self._awareness_limits(1, 60),
            ),
            patch("logic.events.exploration_awareness.emit_insight") as emit_mock,
        ):
            # 1) High-value callout enters awareness stack.
            fss_events.handle_scan(
                {
                    "event": "Scan",
                    "StarSystem": "SMOKE_F3_QUALITY_SYSTEM",
                    "BodyName": "SMOKE_F3_BODY_1",
                    "PlanetClass": "Earth-like world",
                    "WasDiscovered": False,
                },
                gui_ref=gui_ref,
            )

            # 2) Bio callout in the same system should trigger one summary.
            bio_events.handle_dss_bio_signals(
                {
                    "event": "SAASignalsFound",
                    "StarSystem": "SMOKE_F3_QUALITY_SYSTEM",
                    "BodyName": "SMOKE_F3_BODY_2",
                    "Signals": [{"Type": "Biological", "Count": 3}],
                },
                gui_ref=gui_ref,
            )

            # 3) Another awareness candidate in same system should be suppressed after summary.
            dss_events.handle_dss_target_hint(
                {
                    "event": "Scan",
                    "StarSystem": "SMOKE_F3_QUALITY_SYSTEM",
                    "BodyName": "SMOKE_F3_BODY_3",
                    "PlanetClass": "Rocky body",
                    "WasMapped": False,
                },
                gui_ref=gui_ref,
            )

        message_ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertIn("MSG.ELW_DETECTED", message_ids)
        self.assertEqual(message_ids.count("MSG.EXPLORATION_SYSTEM_SUMMARY"), 1)
        self.assertEqual(len(message_ids), 2)

        snap = awareness.get_awareness_snapshot("SMOKE_F3_QUALITY_SYSTEM")
        self.assertEqual(snap.get("callouts_emitted"), 1)
        self.assertTrue(bool(snap.get("summary_emitted")))
        self.assertGreaterEqual(int(snap.get("suppressed_count") or 0), 2)

    def test_combat_silence_blocks_dss_and_exobio_noncritical(self) -> None:
        # DSS in combat.
        with patch("logic.events.exploration_dss_events.emit_insight") as dss_emit_mock:
            dss_events.handle_dss_scan_complete(
                {
                    "event": "SAAScanComplete",
                    "StarSystem": "SMOKE_F3_QUALITY_SYSTEM",
                    "BodyName": "SMOKE_F3_DSS_COMBAT_BODY",
                    "in_combat": True,
                    "combat_state": "active",
                },
                gui_ref=None,
            )

        dss_call = dss_emit_mock.call_args_list[0]
        dss_insight = Insight(
            text=str(dss_call.args[0]),
            message_id=str(dss_call.kwargs.get("message_id") or ""),
            source=str(dss_call.kwargs.get("source") or "smoke"),
            priority=str(dss_call.kwargs.get("priority") or "P2_NORMAL"),
            context=dict(dss_call.kwargs.get("context") or {}),
            dedup_key=dss_call.kwargs.get("dedup_key"),
            cooldown_scope=dss_call.kwargs.get("cooldown_scope"),
            cooldown_seconds=dss_call.kwargs.get("cooldown_seconds"),
        )
        self.assertFalse(should_speak(dss_insight))

        # Exobio sample in combat.
        with (
            patch("logic.events.exploration_bio_events.emit_insight") as bio_emit_mock,
            patch(
                "logic.events.exploration_bio_events._estimate_collected_species_value",
                return_value=(0.0, False),
            ),
        ):
            bio_events.handle_exobio_progress(
                {
                    "event": "ScanOrganic",
                    "StarSystem": "SMOKE_F3_QUALITY_SYSTEM",
                    "BodyName": "SMOKE_F3_BIO_COMBAT_BODY",
                    "Species_Localised": "Aleoida Arcus",
                    "in_combat": True,
                    "combat_state": "active",
                },
                gui_ref=None,
            )

        bio_call = bio_emit_mock.call_args_list[0]
        bio_insight = Insight(
            text=str(bio_call.args[0]),
            message_id=str(bio_call.kwargs.get("message_id") or ""),
            source=str(bio_call.kwargs.get("source") or "smoke"),
            priority=str(bio_call.kwargs.get("priority") or "P2_NORMAL"),
            context=dict(bio_call.kwargs.get("context") or {}),
            dedup_key=bio_call.kwargs.get("dedup_key"),
            cooldown_scope=bio_call.kwargs.get("cooldown_scope"),
            cooldown_seconds=bio_call.kwargs.get("cooldown_seconds"),
        )
        self.assertFalse(should_speak(bio_insight))


if __name__ == "__main__":
    unittest.main()
