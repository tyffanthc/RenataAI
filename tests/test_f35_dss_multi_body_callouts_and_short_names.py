"""F35 — DSS multi-body sequential callouts and short body names.

Tests cover:
  1. get_short_body_name() trims system prefix correctly.
  2. Multiple high-value planets in one system each fire their own callout
     (regression: priority matrix and TTS_GLOBAL previously blocked planet 2+).
  3. DSS target hint uses short body name.
  4. High-value hint uses short body name.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch, call

import pandas as pd

from logic.events import exploration_high_value_events as hv_events
from logic.events.exploration_high_value_events import get_short_body_name
from logic.events import exploration_dss_events as dss_events


_CARTO_DF = pd.DataFrame([
    {"Body_Type": "earth-like world", "Terraformable": "No", "DSS_Mapped_Value": 700000},
    {"Body_Type": "water world", "Terraformable": "No", "DSS_Mapped_Value": 650000},
    {"Body_Type": "high metal content world", "Terraformable": "Yes", "DSS_Mapped_Value": 620000},
])


class F35ShortBodyNameTests(unittest.TestCase):
    def test_strips_system_prefix(self) -> None:
        self.assertEqual(get_short_body_name("Sol 243 A 2", "Sol 243"), "A 2")

    def test_strips_system_prefix_case_insensitive(self) -> None:
        self.assertEqual(get_short_body_name("sol 243 a 2", "Sol 243"), "a 2")

    def test_no_prefix_match_returns_full(self) -> None:
        self.assertEqual(get_short_body_name("Betelgeuse 1", "Sol"), "Betelgeuse 1")

    def test_empty_system_returns_full(self) -> None:
        self.assertEqual(get_short_body_name("Foo A 1", ""), "Foo A 1")

    def test_empty_body_returns_empty(self) -> None:
        self.assertEqual(get_short_body_name("", "Sol"), "")

    def test_exact_match_returns_full_not_empty(self) -> None:
        # body == system → short would be "" → fallback to full
        self.assertEqual(get_short_body_name("Sol", "Sol"), "Sol")


class F35HighValueMultiBodyCalloutTests(unittest.TestCase):
    """Ensure each unique ELW/WW in a system fires emit_callout_or_summary independently."""

    def setUp(self) -> None:
        hv_events.reset_high_value_flags()
        self.gui = SimpleNamespace(carto_df=_CARTO_DF)

    def tearDown(self) -> None:
        hv_events.reset_high_value_flags()

    def test_three_elw_planets_each_emit_callout(self) -> None:
        bodies = [
            {"BodyID": 10, "BodyName": "Test Sys A 1", "PlanetClass": "Earth-like world",
             "TerraformState": "", "StarSystem": "Test Sys"},
            {"BodyID": 11, "BodyName": "Test Sys A 2", "PlanetClass": "Earth-like world",
             "TerraformState": "", "StarSystem": "Test Sys"},
            {"BodyID": 12, "BodyName": "Test Sys B 1", "PlanetClass": "Earth-like world",
             "TerraformState": "", "StarSystem": "Test Sys"},
        ]
        with patch("logic.events.exploration_high_value_events.emit_callout_or_summary") as mock_emit:
            for ev in bodies:
                hv_events.check_high_value_planet(ev, gui_ref=self.gui)

        self.assertEqual(mock_emit.call_count, 3, "Each unique ELW body should fire its own callout")

    def test_short_body_name_in_callout_text_elw(self) -> None:
        ev = {"BodyID": 20, "BodyName": "Proxima B 3", "PlanetClass": "Earth-like world",
              "TerraformState": "", "StarSystem": "Proxima B"}
        with patch("logic.events.exploration_high_value_events.emit_callout_or_summary") as mock_emit:
            hv_events.check_high_value_planet(ev, gui_ref=self.gui)

        self.assertEqual(mock_emit.call_count, 1)
        text_arg = mock_emit.call_args.kwargs.get("text") or mock_emit.call_args[1].get("text") or ""
        self.assertIn("3", text_arg, "Short name '3' should appear in callout text")
        self.assertNotIn("Proxima B 3", text_arg, "Full name should NOT appear in callout text")

    def test_short_body_name_in_callout_text_ww(self) -> None:
        ev = {"BodyID": 30, "BodyName": "HR 1234 C 2 a", "PlanetClass": "Water world",
              "TerraformState": "", "StarSystem": "HR 1234"}
        with patch("logic.events.exploration_high_value_events.emit_callout_or_summary") as mock_emit:
            hv_events.check_high_value_planet(ev, gui_ref=self.gui)

        self.assertEqual(mock_emit.call_count, 1)
        text_arg = mock_emit.call_args.kwargs.get("text") or mock_emit.call_args[1].get("text") or ""
        self.assertIn("C 2 a", text_arg, "Short name 'C 2 a' should appear in callout text")
        self.assertNotIn("HR 1234 C 2 a", text_arg, "Full name should NOT appear in callout text")


class F35DssTargetHintShortNameTests(unittest.TestCase):
    """DSS target hint should use short body name for TTS."""

    def setUp(self) -> None:
        dss_events.reset_dss_helper_state()

    def tearDown(self) -> None:
        dss_events.reset_dss_helper_state()

    def test_dss_target_hint_uses_short_name(self) -> None:
        ev = {
            "event": "Scan",
            "BodyName": "Sol 243 A 2",
            "StarSystem": "Sol 243",
            "PlanetClass": "high metal content world",
            "TerraformState": "",
            "WasMapped": False,
        }
        gui = SimpleNamespace(carto_df=_CARTO_DF)
        with patch("logic.events.exploration_dss_events.emit_callout_or_summary") as mock_emit:
            with patch("logic.events.exploration_dss_events._is_worth_mapping", return_value=True):
                dss_events.handle_dss_target_hint(ev, gui_ref=gui)

        self.assertEqual(mock_emit.call_count, 1)
        text_arg = mock_emit.call_args.kwargs.get("text") or mock_emit.call_args[1].get("text") or ""
        self.assertIn("A 2", text_arg, "Short name 'A 2' should appear in DSS hint text")
        self.assertNotIn("Sol 243 A 2", text_arg, "Full name should NOT appear in DSS hint text")


class F35PriorityMatrixBypassTests(unittest.TestCase):
    """exploration_awareness_required flag should bypass the priority matrix."""

    def test_exploration_awareness_required_bypasses_matrix(self) -> None:
        from logic.insight_dispatcher import _apply_priority_matrix, Insight
        insight = Insight(
            text="test",
            message_id="MSG.HIGH_VALUE_DSS_HINT",
            source="exploration_high_value_events",
            context={"exploration_awareness_required": True},
            priority="P2_NORMAL",
        )
        # Simulate a recent same-priority voice that would normally suppress this.
        from logic import insight_dispatcher
        import time
        insight_dispatcher._PRIORITY_MATRIX_RUNTIME["last_voice"] = {
            "message_id": "MSG.HIGH_VALUE_DSS_HINT",
            "module_class": "EXPLORATION",
            "class_rank": 2,
            "priority_rank": 2,
            "ts": time.monotonic(),
        }
        allow_tts, allow_reason, forced = _apply_priority_matrix(
            insight, allow_tts=True, allow_reason="notify_policy_allow"
        )
        self.assertTrue(allow_tts, "exploration_awareness_required should bypass priority matrix")
        self.assertFalse(forced)
        # Cleanup
        insight_dispatcher._PRIORITY_MATRIX_RUNTIME.pop("last_voice", None)


if __name__ == "__main__":
    unittest.main()
