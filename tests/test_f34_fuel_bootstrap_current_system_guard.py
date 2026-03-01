from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import fuel_events


class F34FuelBootstrapCurrentSystemGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_warned = fuel_events.LOW_FUEL_WARNED
        self._saved_pending = fuel_events.LOW_FUEL_FLAG_PENDING
        self._saved_pending_ts = fuel_events.LOW_FUEL_FLAG_PENDING_TS
        self._saved_initialized = bool(getattr(fuel_events, "_FUEL_STATUS_INITIALIZED", False))
        self._saved_seen_valid = bool(getattr(fuel_events, "_FUEL_SEEN_VALID_SAMPLE", False))
        self._saved_fuel_capacity = getattr(app_state, "fuel_capacity", None)
        self._saved_state_fuel_capacity = config.STATE.get("fuel_capacity")
        self._saved_current_system = getattr(app_state, "current_system", None)
        self._saved_state_sys = config.STATE.get("sys")

        fuel_events.LOW_FUEL_WARNED = False
        fuel_events.LOW_FUEL_FLAG_PENDING = False
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = 0.0
        fuel_events._FUEL_STATUS_INITIALIZED = False
        fuel_events._FUEL_SEEN_VALID_SAMPLE = False
        with app_state.lock:
            app_state.fuel_capacity = None
            app_state.current_system = "Unknown"
        config.STATE.pop("fuel_capacity", None)
        config.STATE["sys"] = "Unknown"

    def tearDown(self) -> None:
        fuel_events.LOW_FUEL_WARNED = self._saved_warned
        fuel_events.LOW_FUEL_FLAG_PENDING = self._saved_pending
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = self._saved_pending_ts
        fuel_events._FUEL_STATUS_INITIALIZED = self._saved_initialized
        fuel_events._FUEL_SEEN_VALID_SAMPLE = self._saved_seen_valid
        with app_state.lock:
            app_state.fuel_capacity = self._saved_fuel_capacity
            app_state.current_system = self._saved_current_system
        if self._saved_state_fuel_capacity is None:
            config.STATE.pop("fuel_capacity", None)
        else:
            config.STATE["fuel_capacity"] = self._saved_state_fuel_capacity
        if self._saved_state_sys is None:
            config.STATE.pop("sys", None)
        else:
            config.STATE["sys"] = self._saved_state_sys

    def test_bootstrap_unknown_system_blocks_fuel_critical_even_with_confirmed_capacity(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
            "StarSystem": "F34_STATUS_HAS_SYSTEM_BUT_BOOTSTRAP_UNKNOWN",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 0)
        self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

    def test_known_runtime_system_allows_fuel_critical(self) -> None:
        with app_state.lock:
            app_state.current_system = "F34_BOOTSTRAP_KNOWN_SYS"
        config.STATE["sys"] = "F34_BOOTSTRAP_KNOWN_SYS"

        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))

    def test_alert_unlocks_after_runtime_system_becomes_known(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
            "StarSystem": "F34_BOOTSTRAP_UNLOCK_SYS",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)
            self.assertEqual(emit_mock.call_count, 0)
            self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

            with app_state.lock:
                app_state.current_system = "F34_BOOTSTRAP_UNLOCK_SYS"
            config.STATE["sys"] = "F34_BOOTSTRAP_UNLOCK_SYS"
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))


if __name__ == "__main__":
    unittest.main()

