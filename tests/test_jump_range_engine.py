import unittest
from types import SimpleNamespace

import config
from logic.jump_range_engine import (
    compute_jump_range_current,
    compute_jump_range_loadout_max,
)


def _modules_data() -> dict:
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


def _ship_state(
    *,
    engineering=None,
    experimental=None,
    unladen=100.0,
    cargo=10.0,
    fuel_main=4.0,
    fuel_res=1.0,
    booster=5.0,
):
    return SimpleNamespace(
        fsd={
            "class": 5,
            "rating": "A",
            "item": "Frame Shift Drive",
            "engineering": engineering,
            "experimental": experimental,
        },
        fsd_booster={"bonus_ly": booster},
        unladen_mass_t=unladen,
        cargo_mass_t=cargo,
        fuel_main_t=fuel_main,
        fuel_reservoir_t=fuel_res,
    )


class JumpRangeEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = config.config._settings.copy()
        config.config._settings["jump_range_include_reservoir_mass"] = True
        config.config._settings["jump_range_engineering_enabled"] = True
        config.config._settings["jump_range_rounding"] = 2

    def tearDown(self) -> None:
        config.config._settings = self._orig

    def test_compute_jump_range_current_success(self) -> None:
        result = compute_jump_range_current(_ship_state(), _modules_data())

        self.assertTrue(result.ok)
        self.assertEqual(result.error, None)
        self.assertEqual(result.jump_range_limited_by, "fuel")
        self.assertAlmostEqual(result.jump_range_fuel_needed_t, 4.0, places=4)
        self.assertAlmostEqual(result.jump_range_ly, 60.0, places=2)
        self.assertFalse(result.details.get("engineering_applied"))

    def test_compute_jump_range_current_requires_reservoir_when_enabled(self) -> None:
        ship = _ship_state(fuel_res=None)
        result = compute_jump_range_current(ship, _modules_data())

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "missing_reservoir_mass")
        self.assertEqual(result.jump_range_ly, None)

    def test_engineering_modifiers_override_fsd_params(self) -> None:
        ship = _ship_state(
            engineering={
                "Modifiers": [
                    {"Label": "FSD Optimal Mass", "Value": 1500.0},
                    {"Label": "FSD Max Fuel Per Jump", "Value": 6.0},
                ]
            },
            fuel_main=8.0,
            fuel_res=0.5,
        )
        result = compute_jump_range_current(ship, _modules_data())

        self.assertTrue(result.ok)
        self.assertEqual(result.details.get("engineering_applied"), True)
        self.assertEqual(result.details.get("engineering_source"), "modifiers")
        self.assertEqual(result.jump_range_limited_by, "mass")
        self.assertAlmostEqual(result.jump_range_fuel_needed_t, 6.0, places=4)

    def test_mass_manager_experimental_increases_loadout_range(self) -> None:
        base_ship = _ship_state(experimental=None, booster=0.0, cargo=0.0, fuel_main=5.0, fuel_res=0.0)
        mm_ship = _ship_state(
            experimental="Mass Manager",
            booster=0.0,
            cargo=0.0,
            fuel_main=5.0,
            fuel_res=0.0,
        )

        base = compute_jump_range_loadout_max(base_ship, _modules_data())
        mass_manager = compute_jump_range_loadout_max(mm_ship, _modules_data())

        self.assertTrue(base.ok)
        self.assertTrue(mass_manager.ok)
        self.assertGreater(mass_manager.jump_range_ly, base.jump_range_ly)
        self.assertEqual(mass_manager.details.get("engineering_source"), "experimental")


if __name__ == "__main__":
    unittest.main()
