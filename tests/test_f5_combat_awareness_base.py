from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.state import app_state
from logic.events import combat_awareness as combat_events


class F5CombatAwarenessBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_signature = getattr(app_state, "last_combat_awareness_signature", None)
        self._saved_setting = app_state.config.get("combat_awareness_enabled", True)
        app_state.current_system = "F5_COMBAT_TEST_SYSTEM"
        app_state.last_combat_awareness_signature = None
        app_state.config._settings["combat_awareness_enabled"] = True
        combat_events.reset_combat_awareness_state()

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_combat_awareness_signature = self._saved_signature
        app_state.config._settings["combat_awareness_enabled"] = self._saved_setting
        combat_events.reset_combat_awareness_state()

    def test_high_pattern_requires_repeat_and_emits_neutral_warning(self) -> None:
        with (
            patch(
                "logic.events.combat_awareness.app_state.system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 30_000_000.0}),
            ),
            patch("logic.events.combat_awareness.emit_insight") as emit_mock,
        ):
            # First entry into pattern: counter=1 (no emit yet for high pattern).
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_COMBAT_TEST_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.55,
                    "ShieldsUp": False,
                    "FSDCooldown": 5.0,
                },
                gui_ref=None,
            )
            # Exit pattern.
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_COMBAT_TEST_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.80,
                    "ShieldsUp": True,
                    "FSDCooldown": 0.0,
                },
                gui_ref=None,
            )
            # Re-enter pattern: counter=2 -> emit.
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_COMBAT_TEST_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.55,
                    "ShieldsUp": False,
                    "FSDCooldown": 5.0,
                },
                gui_ref=None,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.COMBAT_AWARENESS_HIGH")
        self.assertEqual(kwargs.get("priority"), "P1_HIGH")
        ctx = dict(kwargs.get("context") or {})
        payload = dict(ctx.get("combat_payload") or {})
        self.assertIn(
            payload.get("pattern_id"),
            {"combat_shields_down_exposed", "combat_escape_window_unstable", "combat_high_stake_exposure"},
        )
        self.assertGreaterEqual(int(payload.get("pattern_count") or 0), 2)
        self.assertIn(payload.get("cargo_value_confidence"), {"HIGH", "MED", "LOW"})
        self.assertIsNotNone(payload.get("cargo_floor_cr"))
        self.assertIsNotNone(payload.get("cargo_expected_cr"))
        raw = str(ctx.get("raw_text") or "").lower()
        self.assertNotIn("musisz", raw)
        self.assertNotIn("znowu", raw)

    def test_critical_pattern_emits_immediately(self) -> None:
        with patch("logic.events.combat_awareness.emit_insight") as emit_mock:
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_COMBAT_TEST_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.19,
                    "ShieldsUp": False,
                },
                gui_ref=None,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.COMBAT_AWARENESS_CRITICAL")
        self.assertEqual(kwargs.get("priority"), "P0_CRITICAL")
        ctx = dict(kwargs.get("context") or {})
        self.assertTrue(bool(ctx.get("in_combat")))
        self.assertEqual(ctx.get("risk_status"), "RISK_CRITICAL")

    def test_auto_mode_is_non_flood_for_same_pattern_signature(self) -> None:
        with patch("logic.events.combat_awareness.emit_insight") as emit_mock:
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_COMBAT_TEST_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.18,
                    "ShieldsUp": False,
                },
                gui_ref=None,
            )
            combat_events.handle_status_update(
                {
                    "StarSystem": "F5_COMBAT_TEST_SYSTEM",
                    "InDanger": True,
                    "Hull": 0.18,
                    "ShieldsUp": False,
                },
                gui_ref=None,
            )

        self.assertEqual(emit_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
