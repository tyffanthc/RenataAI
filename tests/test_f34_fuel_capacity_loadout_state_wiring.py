from __future__ import annotations

import unittest

import config
from app.state import app_state


class F34FuelCapacityLoadoutStateWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_fuel_capacity = getattr(app_state, "fuel_capacity", None)
        self._saved_state_fuel_capacity = config.STATE.get("fuel_capacity")
        with app_state.lock:
            app_state.fuel_capacity = None
        config.STATE.pop("fuel_capacity", None)

    def tearDown(self) -> None:
        with app_state.lock:
            app_state.fuel_capacity = self._saved_fuel_capacity
        if self._saved_state_fuel_capacity is None:
            config.STATE.pop("fuel_capacity", None)
        else:
            config.STATE["fuel_capacity"] = self._saved_state_fuel_capacity

    def test_loadout_sets_global_fuel_capacity_from_main_and_reserve(self) -> None:
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "FuelCapacity": {"Main": 32.0, "Reserve": 0.63}},
            source="test.f34.loadout.capacity.main_reserve",
        )
        self.assertIsNotNone(app_state.fuel_capacity)
        self.assertAlmostEqual(float(app_state.fuel_capacity or 0.0), 32.63, places=3)
        self.assertAlmostEqual(float(config.STATE.get("fuel_capacity") or 0.0), 32.63, places=3)

    def test_loadout_deterministically_overwrites_fuel_capacity(self) -> None:
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "FuelCapacity": {"Main": 16.0}},
            source="test.f34.loadout.capacity.prime",
        )
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "FuelCapacity": {"Main": 8.0, "Reserve": 0.5}},
            source="test.f34.loadout.capacity.overwrite",
        )
        self.assertIsNotNone(app_state.fuel_capacity)
        self.assertAlmostEqual(float(app_state.fuel_capacity or 0.0), 8.5, places=3)
        self.assertAlmostEqual(float(config.STATE.get("fuel_capacity") or 0.0), 8.5, places=3)

    def test_loadout_with_invalid_capacity_keeps_last_known_value(self) -> None:
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "FuelCapacity": {"Main": 24.0}},
            source="test.f34.loadout.capacity.valid",
        )
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "FuelCapacity": {"Main": "broken", "Reserve": "n/a"}},
            source="test.f34.loadout.capacity.invalid",
        )
        self.assertIsNotNone(app_state.fuel_capacity)
        self.assertAlmostEqual(float(app_state.fuel_capacity or 0.0), 24.0, places=3)
        self.assertAlmostEqual(float(config.STATE.get("fuel_capacity") or 0.0), 24.0, places=3)


if __name__ == "__main__":
    unittest.main()

