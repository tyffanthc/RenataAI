import unittest

from logic.risk_rebuy_contract import build_risk_rebuy_contract


class RiskRebuyWidgetContractTests(unittest.TestCase):
    def test_low_threshold_from_exploration_value(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 50_000_000.0,
                "exobio_value_estimated": 0.0,
                "credits": 2_000_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.risk_label, "LOW")
        self.assertEqual(contract.rebuy_label, "Rebuy OK")

    def test_med_threshold_from_exobio_value(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 20_000_000.0,
                "exobio_value_estimated": 250_000_000.0,
                "credits": 2_000_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.risk_label, "MED")
        self.assertEqual(contract.value_risk_label, "MED")

    def test_high_threshold_covers_very_high_bucket(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 200_000_000.0,
                "exobio_value_estimated": 0.0,
                "credits": 2_000_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.risk_label, "HIGH")

    def test_critical_threshold_from_exobio_value(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 20_000_000.0,
                "exobio_value_estimated": 1_000_000_000.0,
                "credits": 2_000_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.risk_label, "CRIT")

    def test_no_rebuy_forces_critical(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 0.0,
                "exobio_value_estimated": 0.0,
                "credits": 900_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.rebuy_label, "NO REBUY")
        self.assertEqual(contract.risk_label, "CRIT")

    def test_rebuy_low_escalates_to_high(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 0.0,
                "exobio_value_estimated": 0.0,
                "credits": 1_100_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.rebuy_label, "REBUY LOW")
        self.assertEqual(contract.risk_label, "HIGH")

    def test_source_risk_critical_is_preserved(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_CRITICAL",
                "exploration_value_estimated": 0.0,
                "exobio_value_estimated": 0.0,
                "credits": 5_000_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.source_risk_label, "CRIT")
        self.assertEqual(contract.risk_label, "CRIT")


if __name__ == "__main__":
    unittest.main()
