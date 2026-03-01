from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import fuel_events


class F34FuelCriticalGuardCapacityConfirmedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_warned = fuel_events.LOW_FUEL_WARNED
        self._saved_pending = fuel_events.LOW_FUEL_FLAG_PENDING
        self._saved_pending_ts = fuel_events.LOW_FUEL_FLAG_PENDING_TS
        self._saved_initialized = bool(getattr(fuel_events, "_FUEL_STATUS_INITIALIZED", False))
        self._saved_seen_valid = bool(getattr(fuel_events, "_FUEL_SEEN_VALID_SAMPLE", False))
        self._saved_fuel_capacity = getattr(app_state, "fuel_capacity", None)
        self._saved_state_fuel_capacity = config.STATE.get("fuel_capacity")

        fuel_events.LOW_FUEL_WARNED = False
        fuel_events.LOW_FUEL_FLAG_PENDING = False
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = 0.0
        fuel_events._FUEL_STATUS_INITIALIZED = False
        fuel_events._FUEL_SEEN_VALID_SAMPLE = False
        with app_state.lock:
            app_state.fuel_capacity = None
        config.STATE.pop("fuel_capacity", None)

    def tearDown(self) -> None:
        fuel_events.LOW_FUEL_WARNED = self._saved_warned
        fuel_events.LOW_FUEL_FLAG_PENDING = self._saved_pending
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = self._saved_pending_ts
        fuel_events._FUEL_STATUS_INITIALIZED = self._saved_initialized
        fuel_events._FUEL_SEEN_VALID_SAMPLE = self._saved_seen_valid
        with app_state.lock:
            app_state.fuel_capacity = self._saved_fuel_capacity
        if self._saved_state_fuel_capacity is None:
            config.STATE.pop("fuel_capacity", None)
        else:
            config.STATE["fuel_capacity"] = self._saved_state_fuel_capacity

    def test_flag_only_low_fuel_is_suppressed_until_capacity_confirmed(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": True,
            "Fuel": {},
            "FuelCapacity": {},
            "StarSystem": "F34_CAPACITY_UNKNOWN",
        }
        with (
            patch("logic.events.fuel_events.emit_insight") as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertFalse(emit_mock.called)
        self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))
        self.assertIsNone(getattr(app_state, "fuel_capacity", None))

    def test_status_capacity_confirms_and_allows_alert(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
            "StarSystem": "F34_STATUS_CAPACITY",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))
        self.assertAlmostEqual(float(getattr(app_state, "fuel_capacity") or 0.0), 20.0, places=3)
        self.assertAlmostEqual(float(config.STATE.get("fuel_capacity") or 0.0), 20.0, places=3)

    def test_confirmed_capacity_from_previous_sample_allows_flag_only_alert(self) -> None:
        prime_status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 10.0},
            "FuelCapacity": {"Main": 20.0},
        }
        low_flag_status = {
            "Docked": False,
            "LowFuel": True,
            "Fuel": {},
            "FuelCapacity": {},
            "StarSystem": "F34_FLAG_AFTER_CONFIRM",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(prime_status)
            fuel_events.handle_status_update(low_flag_status)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))
        self.assertAlmostEqual(float(getattr(app_state, "fuel_capacity") or 0.0), 20.0, places=3)


if __name__ == "__main__":
    unittest.main()

