from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import fuel_events
from logic.jump_range_engine import compute_jump_range_current


def _jr_modules_data() -> dict:
    return {
        "fsd": [
            {
                "class": 5,
                "rating": "A",
                "name": "5A Frame Shift Drive",
                "symbol": "Int_FSD_Size5_Class5",
                "opt_mass": 1000.0,
                "max_fuel": 5.0,
                "fuel_power": 2.0,
                "fuel_multiplier": 0.1,
            }
        ]
    }


def _jr_ship_state() -> SimpleNamespace:
    return SimpleNamespace(
        fsd={
            "class": 5,
            "rating": "A",
            "item": "Frame Shift Drive",
            "engineering": None,
            "experimental": None,
        },
        fsd_booster={"bonus_ly": 0.0},
        unladen_mass_t=100.0,
        cargo_mass_t=10.0,
        fuel_main_t=4.0,
        fuel_reservoir_t=1.0,
    )


class F34QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_warned = fuel_events.LOW_FUEL_WARNED
        self._saved_pending = fuel_events.LOW_FUEL_FLAG_PENDING
        self._saved_pending_ts = fuel_events.LOW_FUEL_FLAG_PENDING_TS
        self._saved_initialized = bool(getattr(fuel_events, "_FUEL_STATUS_INITIALIZED", False))
        self._saved_seen_valid = bool(getattr(fuel_events, "_FUEL_SEEN_VALID_SAMPLE", False))

        self._saved_fuel_capacity = getattr(app_state, "fuel_capacity", None)
        self._saved_current_system = getattr(app_state, "current_system", None)
        self._saved_state_fuel_capacity = config.STATE.get("fuel_capacity")
        self._saved_state_sys = config.STATE.get("sys")

        self._saved_settings = dict(config.config._settings)
        config.config._settings["jump_range_include_reservoir_mass"] = True
        config.config._settings["jump_range_engineering_enabled"] = True
        config.config._settings["jump_range_rounding"] = 2

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

        config.config._settings = self._saved_settings

    def test_quality_gate_bootstrap_guard_and_ambiguous_fallback_path(self) -> None:
        low_with_capacity = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
            "StarSystem": "F34_QG_BOOTSTRAP",
        }
        low_ambiguous_without_capacity = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {},
            "StarSystem": "",
        }

        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch("logic.events.fuel_events.log_event_throttled") as log_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(low_with_capacity)
            self.assertEqual(emit_mock.call_count, 0)
            self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

            with app_state.lock:
                app_state.current_system = "F34_QG_LIVE"
            config.STATE["sys"] = "F34_QG_LIVE"
            fuel_events.handle_status_update(low_ambiguous_without_capacity)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))
        self.assertAlmostEqual(float(getattr(app_state, "fuel_capacity") or 0.0), 20.0, places=3)
        reasons = [str(call.kwargs.get("reason") or "") for call in log_mock.call_args_list]
        self.assertIn("bootstrap_current_system_unknown", reasons)
        self.assertIn("ambiguous_numeric_without_capacity_fallback_applied", reasons)

    def test_smoke_capacity_confirmation_and_jump_range_regression(self) -> None:
        with app_state.lock:
            app_state.current_system = "F34_QG_SMOKE_SYS"
        config.STATE["sys"] = "F34_QG_SMOKE_SYS"

        low_flag_without_capacity = {
            "Docked": False,
            "LowFuel": True,
            "Fuel": {},
            "FuelCapacity": {},
            "StarSystem": "F34_QG_SMOKE_SYS",
        }
        low_with_confirmed_capacity = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
            "StarSystem": "F34_QG_SMOKE_SYS",
        }

        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(low_flag_without_capacity)
            self.assertEqual(emit_mock.call_count, 0)
            self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

            fuel_events.handle_status_update(low_with_confirmed_capacity)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))

        jr = compute_jump_range_current(_jr_ship_state(), _jr_modules_data())
        self.assertTrue(bool(jr.ok))
        self.assertIsNone(jr.error)
        self.assertIsNotNone(jr.jump_range_ly)
        self.assertGreater(float(jr.jump_range_ly or 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()

