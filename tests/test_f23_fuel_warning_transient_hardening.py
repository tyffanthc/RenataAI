from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.events import fuel_events


class F23FuelWarningTransientHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_warned = fuel_events.LOW_FUEL_WARNED
        self._saved_pending = fuel_events.LOW_FUEL_FLAG_PENDING
        self._saved_pending_ts = fuel_events.LOW_FUEL_FLAG_PENDING_TS
        self._saved_initialized = bool(getattr(fuel_events, "_FUEL_STATUS_INITIALIZED", False))
        fuel_events.LOW_FUEL_WARNED = False
        fuel_events.LOW_FUEL_FLAG_PENDING = False
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = 0.0
        fuel_events._FUEL_STATUS_INITIALIZED = False

    def tearDown(self) -> None:
        fuel_events.LOW_FUEL_WARNED = self._saved_warned
        fuel_events.LOW_FUEL_FLAG_PENDING = self._saved_pending
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = self._saved_pending_ts
        fuel_events._FUEL_STATUS_INITIALIZED = self._saved_initialized

    def test_uncertain_numeric_samples_without_lowfuel_flag_do_not_trigger_or_arm_pending(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 0.12},  # ambiguous without FuelCapacity
            "FuelCapacity": {},
        }
        with (
            patch("logic.events.fuel_events.emit_insight") as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)
            fuel_events.handle_status_update(status)

        self.assertFalse(emit_mock.called)
        self.assertFalse(bool(fuel_events.LOW_FUEL_FLAG_PENDING))
        self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

    def test_missing_fuel_and_capacity_sample_without_flag_is_ignored_and_resets_pending(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {},
            "FuelCapacity": {},
        }
        # Seed pending to ensure "no-decision" startup sample clears stale confirmation state.
        fuel_events.LOW_FUEL_FLAG_PENDING = True
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = 123.0
        with (
            patch("logic.events.fuel_events.emit_insight") as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertFalse(emit_mock.called)
        self.assertFalse(bool(fuel_events.LOW_FUEL_FLAG_PENDING))
        self.assertEqual(float(fuel_events.LOW_FUEL_FLAG_PENDING_TS), 0.0)
        self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

    def test_real_low_fuel_from_reliable_numeric_sample_still_alerts(self) -> None:
        prime_ok_status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 10.0},
            "FuelCapacity": {"Main": 20.0},
        }
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},  # 10%
            "StarSystem": "F23_REAL_LOW_FUEL_SYS",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(prime_ok_status)
            fuel_events.handle_status_update(status)

        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = dict(emit_mock.call_args.kwargs)
        self.assertEqual(kwargs.get("message_id"), "MSG.FUEL_CRITICAL")
        self.assertEqual(kwargs.get("source"), "fuel_events")

    def test_flag_only_low_fuel_still_requires_confirmation_and_then_alerts(self) -> None:
        prime_ok_status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 10.0},
            "FuelCapacity": {"Main": 20.0},
        }
        status = {
            "Docked": False,
            "LowFuel": True,
            "Fuel": {},
            "FuelCapacity": {},
            "StarSystem": "F23_FLAG_ONLY_SYS",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(prime_ok_status)
            fuel_events.handle_status_update(status)
            self.assertEqual(emit_mock.call_count, 0)
            self.assertTrue(bool(fuel_events.LOW_FUEL_FLAG_PENDING))

            fuel_events.handle_status_update(status)

        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))
        self.assertFalse(bool(fuel_events.LOW_FUEL_FLAG_PENDING))
        self.assertEqual(emit_mock.call_count, 1)

    def test_startup_with_already_low_fuel_is_suppressed_but_marked_warned(self) -> None:
        status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},  # 10%
            "StarSystem": "F23_STARTUP_SUPPRESS_SYS",
        }
        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(status)

        self.assertEqual(emit_mock.call_count, 0)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))


if __name__ == "__main__":
    unittest.main()
