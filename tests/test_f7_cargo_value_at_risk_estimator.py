from __future__ import annotations

import unittest

import config
from logic import cargo_value_estimator


class CargoValueAtRiskEstimatorTests(unittest.TestCase):
    _CFG_KEYS = (
        "risk.cargo.default_unit_price_cr",
        "risk.cargo.floor_factor.market",
        "risk.cargo.floor_factor.cache",
        "risk.cargo.floor_factor.fallback",
        "risk.cargo.fallback_prices",
    )

    def setUp(self) -> None:
        cargo_value_estimator.reset_runtime()
        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self._saved_settings = {}
        if isinstance(settings, dict):
            for key in self._CFG_KEYS:
                value = settings.get(key)
                if isinstance(value, dict):
                    self._saved_settings[key] = dict(value)
                else:
                    self._saved_settings[key] = value

    def tearDown(self) -> None:
        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        if isinstance(settings, dict):
            for key, value in self._saved_settings.items():
                if value is None:
                    settings.pop(key, None)
                elif isinstance(value, dict):
                    settings[key] = dict(value)
                else:
                    settings[key] = value
        cargo_value_estimator.reset_runtime()

    def test_market_prices_drive_high_confidence_estimate(self) -> None:
        cargo_value_estimator.update_cargo_snapshot(
            {"Inventory": [{"Name": "Gold", "Count": 10}]}
        )
        cargo_value_estimator.update_market_snapshot(
            {
                "Items": [
                    {"Name": "Gold", "SellPrice": 50_000, "BuyPrice": 55_000},
                ]
            }
        )

        estimate = cargo_value_estimator.estimate_cargo_value(cargo_tons=10.0)
        self.assertEqual(estimate.confidence, "HIGH")
        self.assertEqual(estimate.source, "market")
        self.assertEqual(int(round(estimate.cargo_expected_cr)), 500_000)
        self.assertGreater(estimate.cargo_floor_cr, 0.0)
        self.assertLess(estimate.cargo_floor_cr, estimate.cargo_expected_cr)

    def test_cache_prices_are_used_when_current_market_has_no_items(self) -> None:
        cargo_value_estimator.update_cargo_snapshot(
            {"Inventory": [{"Name": "Gold", "Count": 10}]}
        )
        cargo_value_estimator.update_market_snapshot(
            {"Items": [{"Name": "Gold", "SellPrice": 49_000}]}
        )
        cargo_value_estimator.update_market_snapshot({"Items": []})

        estimate = cargo_value_estimator.estimate_cargo_value(cargo_tons=10.0)
        self.assertEqual(estimate.source, "cache")
        self.assertEqual(estimate.confidence, "MED")
        self.assertGreater(estimate.cargo_expected_cr, 0.0)

    def test_fallback_prices_are_used_without_market_and_cache(self) -> None:
        cargo_value_estimator.update_cargo_snapshot(
            {"Inventory": [{"Name": "Unknown Cargo", "Count": 5}]}
        )

        estimate = cargo_value_estimator.estimate_cargo_value(cargo_tons=5.0)
        self.assertEqual(estimate.source, "fallback")
        self.assertEqual(estimate.confidence, "LOW")
        self.assertEqual(int(round(estimate.cargo_expected_cr)), 100_000)
        self.assertGreater(estimate.cargo_floor_cr, 0.0)

    def test_unknown_tons_use_market_median_before_cache_and_fallback(self) -> None:
        cargo_value_estimator.update_market_snapshot(
            {
                "Items": [
                    {"Name": "Gold", "SellPrice": 50_000},
                    {"Name": "Silver", "SellPrice": 30_000},
                ]
            }
        )

        estimate = cargo_value_estimator.estimate_cargo_value(cargo_tons=4.0)
        self.assertEqual(estimate.source, "market")
        self.assertEqual(estimate.confidence, "HIGH")
        self.assertEqual(int(round(estimate.cargo_expected_cr)), 160_000)
        self.assertGreater(estimate.cargo_floor_cr, 0.0)


if __name__ == "__main__":
    unittest.main()

