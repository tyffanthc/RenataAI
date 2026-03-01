from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import fuel_events


class F34FuelAmbiguousNumericFallbackLastKnownCapacityTests(unittest.TestCase):
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

    def test_ambiguous_numeric_uses_last_known_capacity_and_alerts(self) -> None:
        with app_state.lock:
            app_state.fuel_capacity = 20.0
        config.STATE["fuel_capacity"] = 20.0

        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {},
            "StarSystem": "F34_AMBIG_FALLBACK",
        }

        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))

    def test_ambiguous_numeric_without_any_capacity_is_rejected(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {},
            "StarSystem": "F34_AMBIG_REJECT",
        }

        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 0)
        self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

    def test_ambiguous_numeric_logs_fallback_applied_reason(self) -> None:
        with app_state.lock:
            app_state.fuel_capacity = 20.0
        config.STATE["fuel_capacity"] = 20.0

        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {},
            "StarSystem": "F34_AMBIG_REASON",
        }

        with (
            patch("logic.events.fuel_events.log_event_throttled") as log_mock,
            patch("logic.events.fuel_events.emit_insight", return_value=True),
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        reasons = [str(call.kwargs.get("reason") or "") for call in log_mock.call_args_list]
        self.assertIn("ambiguous_numeric_without_capacity_fallback_applied", reasons)
        self.assertNotIn("ambiguous_numeric_without_capacity", reasons)


if __name__ == "__main__":
    unittest.main()
