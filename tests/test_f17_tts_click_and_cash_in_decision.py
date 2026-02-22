from __future__ import annotations

import unittest
from unittest.mock import patch

from app.route_manager import route_manager
from app.state import app_state
from gui.app import RenataApp


class _DummyApp:
    _emit_cash_in_ui_callout = RenataApp._emit_cash_in_ui_callout
    _resolve_cash_in_profile_label = staticmethod(RenataApp._resolve_cash_in_profile_label)
    _has_ready_neutron_route_for_target = staticmethod(RenataApp._has_ready_neutron_route_for_target)
    _open_spansh_neutron_tab = RenataApp._open_spansh_neutron_tab
    _trigger_cash_in_neutron_route = RenataApp._trigger_cash_in_neutron_route
    _watch_cash_in_neutron_outcome = RenataApp._watch_cash_in_neutron_outcome

    def __init__(self) -> None:
        self.status_lines: list[str] = []

    def show_status(self, text: str) -> None:
        self.status_lines.append(str(text or ""))

    def on_cash_in_assistant_action(self, action: str, option=None):
        return RenataApp.on_cash_in_assistant_action(self, action, option)


class F17TtsClickAndCashInDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", "")
        self._saved_pending = app_state.get_pending_station_clipboard_snapshot()
        self._saved_route = list(getattr(route_manager, "route", []) or [])
        self._saved_route_type = str(getattr(route_manager, "route_type", "") or "")
        self._saved_route_idx = int(getattr(route_manager, "current_index", 0) or 0)
        app_state.set_system("F17_UI_ORIGIN")
        app_state.clear_pending_station_clipboard(source="test.f17.tts.setup")
        route_manager.clear_route()
        self.app = _DummyApp()

    def tearDown(self) -> None:
        app_state.clear_pending_station_clipboard(source="test.f17.tts.teardown")
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

    def test_set_intent_emits_profile_tts(self) -> None:
        with patch("logic.insight_dispatcher.emit_insight") as emit_mock:
            self.app.on_cash_in_assistant_action("set_intent", {"profile": "FAST"})

        self.assertTrue(any("wybrano profil FAST" in line for line in self.app.status_lines))
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        self.assertIn("Wybrano profil FAST", str(ctx.get("raw_text") or ""))

    def test_set_route_emits_tts_and_arms_station_copy(self) -> None:
        with (
            patch(
                "logic.events.cash_in_assistant.handoff_cash_in_to_route_intent",
                return_value={
                    "ok": True,
                    "target_display": "F17 Target Station (F17_TARGET_SYS)",
                    "target_system": "F17_TARGET_SYS",
                    "target_station": "F17 Target Station",
                    "route_profile": "SAFE",
                },
            ),
            patch("gui.app.common.copy_text_to_clipboard", return_value=True),
            patch("logic.insight_dispatcher.emit_insight") as emit_mock,
        ):
            self.app.on_cash_in_assistant_action(
                "set_route",
                {"profile": "SAFE", "target": {"system_name": "F17_TARGET_SYS", "name": "F17 Target Station"}},
            )

        pending = app_state.get_pending_station_clipboard_snapshot()
        self.assertTrue(bool(pending.get("active")))
        self.assertEqual(str(pending.get("target_system") or ""), "F17_TARGET_SYS")
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        raw_text = str(ctx.get("raw_text") or "")
        self.assertIn("Ustawilam cel trasy i skopiowalam nastepny hop: F17_TARGET_SYS.", raw_text)
        self.assertIn("Stacja zostanie skopiowana po wejsciu do systemu docelowego.", raw_text)

    def test_set_route_fast_neutron_emits_fallback_when_neutron_route_missing(self) -> None:
        with (
            patch(
                "logic.events.cash_in_assistant.handoff_cash_in_to_route_intent",
                return_value={
                    "ok": True,
                    "target_display": "F17 Neutron Hub (F17_NEUTRON_SYS)",
                    "target_system": "F17_NEUTRON_SYS",
                    "target_station": "F17 Neutron Hub",
                    "route_profile": "FAST_NEUTRON",
                },
            ),
            patch("gui.app.common.copy_text_to_clipboard", return_value=True),
            patch("logic.insight_dispatcher.emit_insight") as emit_mock,
        ):
            self.app.on_cash_in_assistant_action(
                "set_route",
                {"profile": "FAST", "target": {"system_name": "F17_NEUTRON_SYS", "name": "F17 Neutron Hub"}},
            )

        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        raw_text = str(ctx.get("raw_text") or "")
        self.assertIn("Nie znalazlam trasy neutronowej. Skopiowalam cel do schowka.", raw_text)

    def test_set_route_fast_neutron_triggers_neutron_planner_when_target_is_real(self) -> None:
        with (
            patch(
                "logic.events.cash_in_assistant.handoff_cash_in_to_route_intent",
                return_value={
                    "ok": True,
                    "target_display": "F17 Neutron Hub (F17_NEUTRON_SYS)",
                    "target_system": "F17_NEUTRON_SYS",
                    "target_station": "F17 Neutron Hub",
                    "route_profile": "FAST_NEUTRON",
                },
            ),
            patch("gui.app.common.copy_text_to_clipboard", return_value=True),
            patch.object(_DummyApp, "_trigger_cash_in_neutron_route", return_value={"ok": True}) as trigger_mock,
            patch.object(_DummyApp, "_watch_cash_in_neutron_outcome") as watch_mock,
            patch("logic.insight_dispatcher.emit_insight"),
        ):
            self.app.on_cash_in_assistant_action(
                "set_route",
                {"profile": "FAST", "target": {"system_name": "F17_NEUTRON_SYS", "name": "F17 Neutron Hub"}},
            )

        self.assertTrue(trigger_mock.called)
        self.assertEqual(trigger_mock.call_args.args[0], "F17_NEUTRON_SYS")
        self.assertEqual(watch_mock.call_count, 1)

    def test_copy_next_hop_emits_tts(self) -> None:
        with (
            patch(
                "logic.events.cash_in_assistant.resolve_cash_in_option_target",
                return_value={
                    "target_is_real": True,
                    "target_system": "F17_COPY_HOP_SYS",
                    "route_profile": "SAFE",
                },
            ),
            patch("logic.events.cash_in_assistant.persist_cash_in_route_profile", return_value={"ok": True}),
            patch("gui.app.common.copy_text_to_clipboard", return_value=True),
            patch("logic.insight_dispatcher.emit_insight") as emit_mock,
        ):
            self.app.on_cash_in_assistant_action("copy_next_hop", {"profile": "SAFE"})

        self.assertTrue(any("skopiowano next hop" in line.lower() for line in self.app.status_lines))
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        self.assertIn("Skopiowalam nastepny hop: F17_COPY_HOP_SYS.", str(ctx.get("raw_text") or ""))


if __name__ == "__main__":
    unittest.main()
