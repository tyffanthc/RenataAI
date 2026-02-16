from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.events import survival_rebuy_awareness as survival_events


class F4SurvivalRebuyAwarenessBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_signature = getattr(app_state, "last_survival_rebuy_signature", None)
        self._saved_setting = app_state.config.get("survival_rebuy_awareness_enabled", True)
        app_state.current_system = "F4_SURVIVAL_TEST_SYSTEM"
        app_state.last_survival_rebuy_signature = None
        app_state.config._settings["survival_rebuy_awareness_enabled"] = True
        survival_events.reset_survival_rebuy_state()

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_survival_rebuy_signature = self._saved_signature
        app_state.config._settings["survival_rebuy_awareness_enabled"] = self._saved_setting
        survival_events.reset_survival_rebuy_state()

    def test_no_rebuy_emits_critical_with_consequence_options(self) -> None:
        with patch("logic.events.survival_rebuy_awareness.emit_insight") as emit_mock:
            survival_events.handle_journal_event(
                {
                    "event": "LoadGame",
                    "StarSystem": "F4_SURVIVAL_TEST_SYSTEM",
                    "Credits": 120000,
                    "Rebuy": 900000,
                },
                gui_ref=None,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.SURVIVAL_REBUY_CRITICAL")
        self.assertEqual(kwargs.get("priority"), "P0_CRITICAL")
        ctx = dict(kwargs.get("context") or {})
        payload = dict(ctx.get("survival_payload") or {})
        self.assertEqual(payload.get("reason"), "no_rebuy")
        self.assertIn(payload.get("cargo_value_confidence"), {"HIGH", "MED", "LOW"})
        self.assertIsNotNone(payload.get("cargo_floor_cr"))
        self.assertIsNotNone(payload.get("cargo_expected_cr"))
        self.assertTrue(bool(payload.get("options")))
        self.assertTrue(str(ctx.get("raw_text") or "").strip())

    def test_auto_signature_gate_emits_only_on_state_change(self) -> None:
        event = {
            "event": "LoadGame",
            "StarSystem": "F4_SURVIVAL_TEST_SYSTEM",
            "Credits": 120000,
            "Rebuy": 900000,
        }
        with patch("logic.events.survival_rebuy_awareness.emit_insight") as emit_mock:
            survival_events.handle_journal_event(event, gui_ref=None)
            survival_events.handle_journal_event(event, gui_ref=None)
            # Resolve risk -> clears signature.
            survival_events.handle_journal_event(
                {
                    "event": "LoadGame",
                    "StarSystem": "F4_SURVIVAL_TEST_SYSTEM",
                    "Credits": 2000000,
                    "Rebuy": 900000,
                },
                gui_ref=None,
            )
            survival_events.handle_journal_event(event, gui_ref=None)

        self.assertEqual(emit_mock.call_count, 2)

    def test_combat_high_var_with_hull_high_emits_p1_high(self) -> None:
        with (
            patch(
                "logic.events.survival_rebuy_awareness.app_state.system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 25_000_000.0}),
            ),
            patch("logic.events.survival_rebuy_awareness.emit_insight") as emit_mock,
        ):
            survival_events.handle_status_update(
                {
                    "StarSystem": "F4_SURVIVAL_TEST_SYSTEM",
                    "Hull": 0.2,
                    "Flags": (1 << 22),  # in danger
                },
                gui_ref=None,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.SURVIVAL_REBUY_HIGH")
        self.assertEqual(kwargs.get("priority"), "P1_HIGH")
        ctx = dict(kwargs.get("context") or {})
        self.assertTrue(bool(ctx.get("in_combat")))
        self.assertEqual(ctx.get("var_status"), "VAR_HIGH")


if __name__ == "__main__":
    unittest.main()
