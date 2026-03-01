from __future__ import annotations

import unittest
from unittest.mock import patch

import app.main_loop as main_loop
import config
from app.route_manager import route_manager
from app.state import app_state
from gui.app import RenataApp
from logic.event_insight_mapping import get_insight_class, get_tts_policy_spec
from logic.events import high_g_warning, navigation_events


class _DummyApp:
    _emit_cash_in_ui_callout = RenataApp._emit_cash_in_ui_callout
    _resolve_cash_in_profile_label = staticmethod(RenataApp._resolve_cash_in_profile_label)
    _has_ready_neutron_route_for_target = staticmethod(RenataApp._has_ready_neutron_route_for_target)

    def __init__(self) -> None:
        self.status_lines: list[str] = []

    def show_status(self, text: str) -> None:
        self.status_lines.append(str(text or ""))

    def on_cash_in_assistant_action(self, action: str, option=None):
        return RenataApp.on_cash_in_assistant_action(self, action, option)


class F17QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", "")
        self._saved_pending = app_state.get_pending_station_clipboard_snapshot()
        self._saved_route = list(getattr(route_manager, "route", []) or [])
        self._saved_route_type = str(getattr(route_manager, "route_type", "") or "")
        self._saved_route_idx = int(getattr(route_manager, "current_index", 0) or 0)

        app_state.set_system("F17_QG_ORIGIN")
        app_state.clear_pending_station_clipboard(source="test.f17.qg.setup")
        route_manager.clear_route()
        config.config._settings["high_g_warning"] = True
        config.config._settings["high_g_warning_threshold_g"] = 2.0
        high_g_warning._reset_state_for_tests()  # noqa: SLF001

    def tearDown(self) -> None:
        high_g_warning._reset_state_for_tests()  # noqa: SLF001
        config.config._settings = self._orig_settings
        app_state.clear_pending_station_clipboard(source="test.f17.qg.teardown")
        if bool(self._saved_pending.get("active")):
            app_state.set_pending_station_clipboard(
                target_system=str(self._saved_pending.get("target_system") or ""),
                station_name=str(self._saved_pending.get("station_name") or ""),
                source=str(self._saved_pending.get("source") or "test.restore"),
            )
        app_state.set_system(self._saved_system or "Unknown")
        if self._saved_route:
            route_manager.set_route(self._saved_route, self._saved_route_type or "trade")
            route_manager.current_index = int(self._saved_route_idx)
        else:
            route_manager.clear_route()

    def test_quality_gate_f17_message_ids_have_mapping_and_voice_policy(self) -> None:
        for message_id in (
            "MSG.HIGH_G_WARNING",
            "MSG.TRADE_DATA_STALE",
            "MSG.PPM_SET_TARGET",
            "MSG.PPM_PIN_ACTION",
            "MSG.PPM_COPY_SYSTEM",
            "MSG.RUNTIME_CRITICAL",
        ):
            self.assertIsNotNone(get_insight_class(message_id), f"Missing insight mapping for {message_id}")
            policy = get_tts_policy_spec(message_id)
            self.assertEqual(policy.message_id, message_id)
            self.assertNotEqual(policy.intent, "silent")

    def test_quality_gate_high_g_and_runtime_critical_callouts(self) -> None:
        high_g_scan = {
            "event": "Scan",
            "BodyName": "F17_QG_HIGH_G",
            "StarSystem": "F17_QG_ORIGIN",
            "SurfaceGravity": 24.6,
        }
        high_g_event = {
            "event": "ApproachBody",
            "BodyName": "F17_QG_HIGH_G",
            "StarSystem": "F17_QG_ORIGIN",
        }
        high_g_warning.handle_journal_event(high_g_scan, gui_ref=None)
        with patch("logic.events.high_g_warning.emit_insight") as highg_emit_mock:
            ok_high_g = high_g_warning.handle_journal_event(high_g_event, gui_ref=None)
        self.assertTrue(ok_high_g)
        self.assertEqual(highg_emit_mock.call_count, 1)
        self.assertEqual(str(highg_emit_mock.call_args.kwargs.get("message_id") or ""), "MSG.HIGH_G_WARNING")

        loop = main_loop.MainLoop(gui_ref=None, log_dir="")
        with patch("app.main_loop.emit_insight") as runtime_emit_mock:
            loop._emit_runtime_critical("F17 test runtime critical", component="journal_stream")
        self.assertEqual(runtime_emit_mock.call_count, 1)
        self.assertEqual(str(runtime_emit_mock.call_args.kwargs.get("message_id") or ""), "MSG.RUNTIME_CRITICAL")

    def test_smoke_set_route_then_system_copy_then_station_copy_after_arrival(self) -> None:
        app = _DummyApp()
        with (
            patch(
                "logic.events.cash_in_assistant.handoff_cash_in_to_route_intent",
                return_value={
                    "ok": True,
                    "target_display": "F17 Smoke Station (F17_SMOKE_TARGET_SYS)",
                    "target_system": "F17_SMOKE_TARGET_SYS",
                    "target_station": "F17 Smoke Station",
                    "route_profile": "SAFE",
                },
            ),
            patch("gui.app.common.copy_text_to_clipboard", return_value=True) as system_copy_mock,
            patch("logic.insight_dispatcher.emit_insight") as _tts_emit_mock,
        ):
            app.on_cash_in_assistant_action(
                "set_route",
                {
                    "profile": "NEAREST",
                    "target": {
                        "system_name": "F17_SMOKE_TARGET_SYS",
                        "name": "F17 Smoke Station",
                    },
                },
            )

        self.assertGreaterEqual(system_copy_mock.call_count, 1)
        self.assertEqual(str(system_copy_mock.call_args.args[0] if system_copy_mock.call_args else ""), "F17_SMOKE_TARGET_SYS")
        pending = app_state.get_pending_station_clipboard_snapshot()
        self.assertTrue(bool(pending.get("active")))
        self.assertEqual(str(pending.get("target_system") or ""), "F17_SMOKE_TARGET_SYS")

        with (
            patch("logic.events.navigation_events.pyperclip.copy") as station_copy_mock,
            patch("logic.events.navigation_events.emit_insight") as nav_emit_mock,
            patch("logic.events.navigation_events.route_manager.get_next_system", return_value=None),
        ):
            navigation_events.handle_location_fsdjump_carrier(
                {"event": "FSDJump", "StarSystem": "F17_OTHER_SYS"},
                gui_ref=None,
            )
            self.assertEqual(station_copy_mock.call_count, 0)

            navigation_events.handle_location_fsdjump_carrier(
                {"event": "FSDJump", "StarSystem": "F17_SMOKE_TARGET_SYS"},
                gui_ref=None,
            )

        station_copy_mock.assert_any_call("F17 Smoke Station")
        self.assertFalse(bool(app_state.get_pending_station_clipboard_snapshot().get("active")))
        self.assertTrue(
            any(
                str(call.kwargs.get("message_id") or "") == "MSG.NEXT_HOP_COPIED"
                for call in nav_emit_mock.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
