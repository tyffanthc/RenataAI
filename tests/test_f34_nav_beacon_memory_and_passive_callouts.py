from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic import player_local_db
from logic.event_handler import EventHandler
from logic.events import exploration_fss_events as fss_events
from logic.events import navigation_events


class F34VisitedNavBeaconPlayerDbTests(unittest.TestCase):
    def test_mark_and_check_nav_beacon_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "player_local.db")
            player_local_db.ensure_playerdb_schema(path=db_path)

            out = player_local_db.mark_nav_beacon_as_scanned(
                system_address=128_123_123_123,
                system_name="F34_NAV_MEMORY",
                path=db_path,
                last_scan_utc="2026-03-01T13:30:00Z",
            )
            self.assertTrue(bool(out.get("ok")))
            self.assertTrue(
                player_local_db.is_nav_beacon_already_scanned(128_123_123_123, path=db_path)
            )
            self.assertFalse(
                player_local_db.is_nav_beacon_already_scanned(999_999_999, path=db_path)
            )

            player_local_db.mark_nav_beacon_as_scanned(
                system_address=128_123_123_123,
                system_name="F34_NAV_MEMORY_RENAMED",
                path=db_path,
                last_scan_utc="2026-03-01T13:35:00Z",
            )
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT system_name, last_scan_utc
                    FROM visited_nav_beacons
                    WHERE system_address = ?;
                    """,
                    (128_123_123_123,),
                ).fetchone()
            finally:
                conn.close()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(str(row[0]), "F34_NAV_MEMORY_RENAMED")
            self.assertEqual(str(row[1]), "2026-03-01T13:35:00Z")


class F34NavBeaconEventRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_state_sys = config.STATE.get("sys")
        config.config._settings["read_system_after_jump"] = False
        with app_state.lock:
            app_state.current_system = "F34_NAV_EVENT_SYS"
        config.STATE["sys"] = "F34_NAV_EVENT_SYS"

    def tearDown(self) -> None:
        config.config._settings = self._saved_settings
        with app_state.lock:
            app_state.current_system = self._saved_system
        if self._saved_state_sys is None:
            config.STATE.pop("sys", None)
        else:
            config.STATE["sys"] = self._saved_state_sys

    def test_fsdjump_population_marks_nav_beacon_scanned(self) -> None:
        event = {
            "event": "FSDJump",
            "timestamp": "2026-03-01T13:40:00Z",
            "StarSystem": "F34_NAV_EVENT_SYS",
            "SystemAddress": 55_000_001,
            "Population": 1200,
        }
        with (
            patch("logic.events.navigation_events._mark_nav_beacon_scanned") as mark_mock,
            patch("logic.events.navigation_events.emit_insight"),
        ):
            navigation_events.handle_location_fsdjump_carrier(event)

        mark_mock.assert_called_once()
        kwargs = dict(mark_mock.call_args.kwargs)
        self.assertEqual(int(kwargs.get("system_address") or 0), 55_000_001)
        self.assertEqual(str(kwargs.get("system_name") or ""), "F34_NAV_EVENT_SYS")
        self.assertEqual(str(kwargs.get("source") or ""), "journal.fsdjump.population")

    def test_fsdjump_population_zero_does_not_mark_nav_beacon(self) -> None:
        event = {
            "event": "FSDJump",
            "timestamp": "2026-03-01T13:41:00Z",
            "StarSystem": "F34_NAV_EVENT_SYS",
            "SystemAddress": 55_000_002,
            "Population": 0,
        }
        with (
            patch("logic.events.navigation_events._mark_nav_beacon_scanned") as mark_mock,
            patch("logic.events.navigation_events.emit_insight"),
        ):
            navigation_events.handle_location_fsdjump_carrier(event)

        mark_mock.assert_not_called()

    def test_event_handler_routes_nav_beacon_scan(self) -> None:
        handler = EventHandler()
        with (
            patch("logic.event_handler.navigation_events.handle_nav_beacon_scan") as nav_mock,
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
        ):
            handler.handle_event(
                json.dumps(
                    {
                        "event": "NavBeaconScan",
                        "timestamp": "2026-03-01T13:42:00Z",
                        "StarSystem": "F34_NAV_EVENT_SYS",
                        "SystemAddress": 55_000_003,
                    }
                )
            )

        nav_mock.assert_called_once()


class F34PassiveFssCalloutMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_state_sys = config.STATE.get("sys")
        self._saved_population = config.STATE.get("current_system_population")
        self._saved_passive_data = bool(getattr(fss_events, "FSS_PASSIVE_DATA_WARNED", False))
        self._saved_passive_full = bool(getattr(fss_events, "FSS_PASSIVE_FULL_WARNED", False))
        with app_state.lock:
            app_state.current_system = "F34_FSS_PASSIVE_SYS"
        config.STATE["sys"] = "F34_FSS_PASSIVE_SYS"
        config.STATE["current_system_population"] = 0
        fss_events.FSS_PASSIVE_DATA_WARNED = False
        fss_events.FSS_PASSIVE_FULL_WARNED = False

    def tearDown(self) -> None:
        with app_state.lock:
            app_state.current_system = self._saved_system
        if self._saved_state_sys is None:
            config.STATE.pop("sys", None)
        else:
            config.STATE["sys"] = self._saved_state_sys
        if self._saved_population is None:
            config.STATE.pop("current_system_population", None)
        else:
            config.STATE["current_system_population"] = self._saved_population
        fss_events.FSS_PASSIVE_DATA_WARNED = self._saved_passive_data
        fss_events.FSS_PASSIVE_FULL_WARNED = self._saved_passive_full

    def test_passive_beacon_intro_is_suppressed_for_visited_system(self) -> None:
        with (
            patch(
                "logic.events.exploration_fss_events.player_local_db.is_nav_beacon_already_scanned",
                return_value=True,
            ),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch.object(fss_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fss_events._maybe_emit_passive_scan_callouts(
                scan_type="NavBeaconDetail",
                system_address=90_001,
            )

        self.assertEqual(emit_mock.call_count, 0)
        self.assertTrue(bool(fss_events.FSS_PASSIVE_DATA_WARNED))

    def test_autoscan_in_empty_system_uses_offline_maps_variant(self) -> None:
        config.STATE["current_system_population"] = 0
        with (
            patch(
                "logic.events.exploration_fss_events.player_local_db.is_nav_beacon_already_scanned",
                return_value=False,
            ),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch.object(fss_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fss_events._maybe_emit_passive_scan_callouts(
                scan_type="AutoScan",
                system_address=90_002,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = dict(emit_mock.call_args.kwargs)
        self.assertEqual(str(kwargs.get("message_id") or ""), "MSG.FSS_PASSIVE_DATA_OFFLINE_MAP")

    def test_navbeacon_in_inhabited_system_uses_beacon_message(self) -> None:
        config.STATE["current_system_population"] = 1500
        with (
            patch(
                "logic.events.exploration_fss_events.player_local_db.is_nav_beacon_already_scanned",
                return_value=False,
            ),
            patch("logic.events.exploration_fss_events.emit_insight") as emit_mock,
            patch.object(fss_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fss_events._maybe_emit_passive_scan_callouts(
                scan_type="NavBeaconDetail",
                system_address=90_003,
            )

        self.assertEqual(emit_mock.call_count, 1)
        kwargs = dict(emit_mock.call_args.kwargs)
        self.assertEqual(str(kwargs.get("message_id") or ""), "MSG.FSS_PASSIVE_DATA_INGESTED")


if __name__ == "__main__":
    unittest.main()

