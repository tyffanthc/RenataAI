from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import high_g_warning


class F26HighGOrbitTriggerAndGravityCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", "")
        self._saved_body = getattr(app_state, "current_body", "")
        config.config._settings["high_g_warning"] = True
        config.config._settings["high_g_warning_threshold_g"] = 2.0
        app_state.set_system("F26_SYS")
        app_state.current_body = "F26_BODY_A"
        high_g_warning._reset_state_for_tests()  # noqa: SLF001

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.set_system(self._saved_system or "Unknown")
        app_state.current_body = self._saved_body
        high_g_warning._reset_state_for_tests()  # noqa: SLF001

    def test_scan_caches_gravity_but_does_not_emit(self) -> None:
        ev = {
            "event": "Scan",
            "BodyName": "F26_BODY_A",
            "StarSystem": "F26_SYS",
            "SurfaceGravity": 24.6,
        }
        with patch("logic.events.high_g_warning.emit_insight") as emit_mock:
            ok = high_g_warning.handle_journal_event(ev, gui_ref=None)
        self.assertFalse(ok)
        self.assertEqual(emit_mock.call_count, 0)

        # ApproachBody should reuse cached gravity and emit.
        with patch("logic.events.high_g_warning.emit_insight") as emit_mock:
            ok2 = high_g_warning.handle_journal_event(
                {"event": "ApproachBody", "BodyName": "F26_BODY_A", "StarSystem": "F26_SYS"},
                gui_ref=None,
            )
        self.assertTrue(ok2)
        self.assertEqual(emit_mock.call_count, 1)
        self.assertEqual(str(emit_mock.call_args.kwargs.get("message_id") or ""), "MSG.HIGH_G_WARNING")

    def test_status_update_emits_only_on_orbit_glide_rising_edge(self) -> None:
        status = {
            "StarSystem": "F26_SYS",
            "BodyName": "F26_BODY_A",
            "SurfaceGravity": 24.6,
            "OrbitalCruise": True,
        }
        with patch("logic.events.high_g_warning.emit_insight") as emit_mock:
            first = high_g_warning.handle_status_update(status, gui_ref=None)
            second = high_g_warning.handle_status_update(status, gui_ref=None)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(emit_mock.call_count, 1)

        # Drop state then rise again -> one more emission.
        with patch("logic.events.high_g_warning.emit_insight") as emit_mock:
            self.assertFalse(
                high_g_warning.handle_status_update(
                    {
                        "StarSystem": "F26_SYS",
                        "BodyName": "F26_BODY_A",
                        "SurfaceGravity": 24.6,
                        "OrbitalCruise": False,
                    },
                    gui_ref=None,
                )
            )
            self.assertTrue(high_g_warning.handle_status_update(status, gui_ref=None))
        self.assertEqual(emit_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()

