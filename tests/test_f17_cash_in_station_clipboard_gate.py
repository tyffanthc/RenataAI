from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import navigation_events


class F17CashInStationClipboardGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", "")
        self._saved_pending = app_state.get_pending_station_clipboard_snapshot()
        app_state.clear_pending_station_clipboard(source="test.f17.setup")
        app_state.set_system("F17_TEST_ORIGIN")

    def tearDown(self) -> None:
        app_state.clear_pending_station_clipboard(source="test.f17.teardown")
        if bool(self._saved_pending.get("active")):
            app_state.set_pending_station_clipboard(
                target_system=str(self._saved_pending.get("target_system") or ""),
                station_name=str(self._saved_pending.get("station_name") or ""),
                source=str(self._saved_pending.get("source") or "test.restore"),
            )
        app_state.set_system(self._saved_system or "Unknown")

    def test_pending_station_clipboard_arm_and_clear(self) -> None:
        snap = app_state.set_pending_station_clipboard(
            target_system="LHS 20",
            station_name="Ray Gateway",
            source="test.f17.arm",
        )
        self.assertTrue(bool(snap.get("active")))
        self.assertEqual(str(snap.get("target_system") or ""), "LHS 20")
        self.assertEqual(str(snap.get("station_name") or ""), "Ray Gateway")

        cleared = app_state.clear_pending_station_clipboard(source="test.f17.clear")
        self.assertFalse(bool(cleared.get("active")))
        self.assertEqual(str(cleared.get("target_system") or ""), "")
        self.assertEqual(str(cleared.get("station_name") or ""), "")

    def test_navigation_copies_station_only_after_arrival(self) -> None:
        app_state.set_pending_station_clipboard(
            target_system="F17_TARGET_SYS",
            station_name="F17 Target Station",
            source="test.f17.navigation",
        )

        with (
            patch("logic.events.navigation_events.pyperclip.copy") as copy_mock,
            patch("logic.events.navigation_events.emit_insight") as emit_mock,
            patch("logic.events.navigation_events.route_manager.get_next_system", return_value=None),
        ):
            navigation_events.handle_location_fsdjump_carrier(
                {"event": "FSDJump", "StarSystem": "F17_OTHER_SYS"},
                gui_ref=None,
            )
            self.assertEqual(copy_mock.call_count, 0)
            self.assertTrue(bool(app_state.get_pending_station_clipboard_snapshot().get("active")))

            navigation_events.handle_location_fsdjump_carrier(
                {"event": "FSDJump", "StarSystem": "F17_TARGET_SYS"},
                gui_ref=None,
            )

        copy_mock.assert_any_call("F17 Target Station")
        self.assertFalse(bool(app_state.get_pending_station_clipboard_snapshot().get("active")))

        copied_callouts = [
            call
            for call in emit_mock.call_args_list
            if str(call.kwargs.get("message_id") or "") == "MSG.NEXT_HOP_COPIED"
        ]
        self.assertGreaterEqual(len(copied_callouts), 1)


if __name__ == "__main__":
    unittest.main()

