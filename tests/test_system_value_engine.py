import unittest

import pandas as pd

from logic.system_value_engine import SystemValueEngine


def _science_data():
    exobio_df = pd.DataFrame(
        [
            {
                "Species_Name": "Aleoida Arcus",
                "Base_Value": 100.0,
                "First_Discovery_Bonus": 50.0,
                "Total_First_Footfall": 180.0,
            }
        ]
    )
    carto_df = pd.DataFrame(
        [
            {
                "Body_Type": "Water World",
                "Terraformable": "Yes",
                "FSS_Base_Value": 1000.0,
                "DSS_Mapped_Value": 1500.0,
                "First_Discovery_Mapped_Value": 3000.0,
            },
            {
                "Body_Type": "Planet Type",
                "Terraformable": "No",
                "FSS_Base_Value": 100.0,
                "DSS_Mapped_Value": 150.0,
                "First_Discovery_Mapped_Value": 300.0,
            },
        ]
    )
    return exobio_df, carto_df


class SystemValueEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SystemValueEngine(_science_data())

    def test_scan_event_updates_cartography_and_bonus(self) -> None:
        event = {
            "event": "Scan",
            "StarSystem": "TEST_SYS_A",
            "BodyName": "TEST_SYS_A 1",
            "PlanetClass": "Water world",
            "TerraformState": "Terraformable",
            "WasDiscovered": False,
            "WasMapped": True,
        }

        self.engine.analyze_scan_event(event)
        stats = self.engine.get_system_stats("TEST_SYS_A")

        self.assertIsNotNone(stats)
        self.assertAlmostEqual(stats.c_cartography, 1500.0, places=3)
        self.assertAlmostEqual(stats.bonus_discovery, 1500.0, places=3)
        self.assertEqual(stats.total_scanned_bodies, 1)
        self.assertEqual(stats.bodies_first_discovery_count, 1)
        self.assertEqual(stats.system_previously_discovered, False)
        self.assertGreaterEqual(len(stats.high_value_targets), 1)

    def test_scan_event_deduplicates_same_body(self) -> None:
        event = {
            "event": "Scan",
            "StarSystem": "TEST_SYS_B",
            "BodyName": "TEST_SYS_B 1",
            "PlanetClass": "Water world",
            "TerraformState": "Terraformable",
            "WasDiscovered": False,
            "WasMapped": True,
        }

        self.engine.analyze_scan_event(event)
        self.engine.analyze_scan_event(event)
        stats = self.engine.get_system_stats("TEST_SYS_B")

        self.assertEqual(stats.total_scanned_bodies, 1)
        self.assertAlmostEqual(stats.c_cartography, 1500.0, places=3)

    def test_biology_event_adds_base_and_bonuses_once(self) -> None:
        event = {
            "event": "ScanOrganic",
            "StarSystem": "TEST_SYS_C",
            "Species_Localised": "Aleoida Arcus",
            "FirstDiscovery": True,
            "FirstFootfall": True,
        }

        self.engine.analyze_biology_event(event)
        self.engine.analyze_biology_event(event)
        stats = self.engine.get_system_stats("TEST_SYS_C")

        self.assertIsNotNone(stats)
        self.assertAlmostEqual(stats.c_exobiology, 100.0, places=3)
        # 50 (first discovery) + 30 (first footfall extra)
        self.assertAlmostEqual(stats.bonus_discovery, 80.0, places=3)
        self.assertEqual(len(stats.seen_species), 1)

    def test_get_discovery_status_reports_previously_discovered(self) -> None:
        event = {
            "event": "Scan",
            "StarSystem": "TEST_SYS_D",
            "BodyName": "TEST_SYS_D 1",
            "PlanetClass": "Water world",
            "TerraformState": "Terraformable",
            "WasDiscovered": True,
            "WasMapped": False,
        }
        self.engine.analyze_scan_event(event)
        status = self.engine.get_discovery_status("TEST_SYS_D")

        self.assertEqual(status["system_previously_discovered"], True)
        self.assertEqual(status["any_virgin_bodies"], False)
        self.assertEqual(status["is_virgin_system"], False)

    def test_calculate_totals_aggregates_systems(self) -> None:
        self.engine.analyze_scan_event(
            {
                "event": "Scan",
                "StarSystem": "TEST_SYS_E",
                "BodyName": "TEST_SYS_E 1",
                "PlanetClass": "Water world",
                "TerraformState": "Terraformable",
                "WasDiscovered": False,
                "WasMapped": True,
            }
        )
        self.engine.analyze_biology_event(
            {
                "event": "ScanOrganic",
                "StarSystem": "TEST_SYS_F",
                "Species_Localised": "Aleoida Arcus",
                "FirstDiscovery": True,
                "FirstFootfall": True,
            }
        )

        totals = self.engine.calculate_totals()
        self.assertGreater(totals["c_cartography"], 0.0)
        self.assertGreater(totals["c_exobiology"], 0.0)
        self.assertGreater(totals["bonus_discovery"], 0.0)
        self.assertAlmostEqual(
            totals["total"],
            totals["c_cartography"] + totals["c_exobiology"] + totals["bonus_discovery"],
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
