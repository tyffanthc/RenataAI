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
            {
                "Body_Type": "High Metal Content Planet",
                "Terraformable": "Yes",
                "FSS_Base_Value": 700.0,
                "DSS_Mapped_Value": 1000.0,
                "First_Discovery_Mapped_Value": 2000.0,
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

    def test_saa_scan_complete_upgrades_existing_fss_body_to_dss_value_once(self) -> None:
        scan_fss = {
            "event": "Scan",
            "StarSystem": "TEST_SYS_G",
            "BodyName": "TEST_SYS_G 1",
            "PlanetClass": "Water world",
            "TerraformState": "Terraformable",
            "WasDiscovered": False,
            "WasMapped": False,
        }
        saa_done = {
            "event": "SAAScanComplete",
            "StarSystem": "TEST_SYS_G",
            "BodyName": "TEST_SYS_G 1",
        }

        self.engine.analyze_scan_event(scan_fss)
        stats = self.engine.get_system_stats("TEST_SYS_G")
        self.assertIsNotNone(stats)
        self.assertAlmostEqual(stats.c_cartography, 1000.0, places=3)
        # FSS estimate bonus (1000 * ((3000/1500)-1)) = 1000
        self.assertAlmostEqual(stats.bonus_discovery, 1000.0, places=3)

        self.engine.analyze_dss_scan_complete_event(saa_done)
        stats = self.engine.get_system_stats("TEST_SYS_G")
        self.assertAlmostEqual(stats.c_cartography, 1500.0, places=3)
        self.assertAlmostEqual(stats.bonus_discovery, 1500.0, places=3)

        # Dedupe: repeated SAAScanComplete should not change totals again.
        self.engine.analyze_dss_scan_complete_event(saa_done)
        stats = self.engine.get_system_stats("TEST_SYS_G")
        self.assertAlmostEqual(stats.c_cartography, 1500.0, places=3)
        self.assertAlmostEqual(stats.bonus_discovery, 1500.0, places=3)

    def test_scan_event_maps_high_metal_content_body_alias(self) -> None:
        event = {
            "event": "Scan",
            "StarSystem": "TEST_SYS_H",
            "BodyName": "TEST_SYS_H 3",
            "PlanetClass": "High metal content body",
            "TerraformState": "Terraformable",
            "WasDiscovered": True,
            "WasMapped": False,
        }
        self.engine.analyze_scan_event(event)
        stats = self.engine.get_system_stats("TEST_SYS_H")
        self.assertIsNotNone(stats)
        self.assertAlmostEqual(float(stats.c_cartography or 0.0), 700.0, places=3)

    def test_nan_planet_type_fallback_does_not_poison_totals(self) -> None:
        exo, carto = _science_data()
        carto = pd.concat(
            [
                carto[carto["Body_Type"] != "Planet Type"],
                pd.DataFrame(
                    [
                        {
                            "Body_Type": "Planet Type",
                            "Terraformable": "Terraformable?",
                            "FSS_Base_Value": float("nan"),
                            "DSS_Mapped_Value": float("nan"),
                            "First_Discovery_Mapped_Value": float("nan"),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        engine = SystemValueEngine((exo, carto))
        engine.analyze_scan_event(
            {
                "event": "Scan",
                "StarSystem": "TEST_SYS_I",
                "BodyName": "TEST_SYS_I 1",
                "PlanetClass": "Unknown prototype body",
                "WasDiscovered": False,
                "WasMapped": False,
            }
        )
        stats = engine.get_system_stats("TEST_SYS_I")
        self.assertIsNotNone(stats)
        self.assertEqual(float(stats.c_cartography or 0.0), 0.0)
        self.assertEqual(float(stats.bonus_discovery or 0.0), 0.0)

    def test_scan_event_counts_star_type_with_tier_mapper(self) -> None:
        self.engine.analyze_scan_event(
            {
                "event": "Scan",
                "StarSystem": "TEST_SYS_STAR_A",
                "BodyName": "TEST_SYS_STAR_A",
                "BodyType": "Star",
                "StarType": "K",
                "WasDiscovered": False,
            }
        )
        stats = self.engine.get_system_stats("TEST_SYS_STAR_A")
        self.assertIsNotNone(stats)
        self.assertGreater(float(stats.c_cartography or 0.0), 0.0)
        self.assertGreater(float(stats.bonus_discovery or 0.0), 0.0)
        body = dict((stats.cartography_bodies or {}).get("TEST_SYS_STAR_A") or {})
        self.assertEqual(body.get("valuation_source"), "star_tier")
        self.assertEqual(body.get("mapped_accounted"), True)

    def test_scan_event_unknown_star_type_is_skipped_without_poisoning_totals(self) -> None:
        self.engine.analyze_scan_event(
            {
                "event": "Scan",
                "StarSystem": "TEST_SYS_STAR_B",
                "BodyName": "TEST_SYS_STAR_B",
                "BodyType": "Star",
                "StarType": "Quantum anomaly",
                "WasDiscovered": True,
            }
        )
        stats = self.engine.get_system_stats("TEST_SYS_STAR_B")
        self.assertIsNotNone(stats)
        self.assertEqual(float(stats.c_cartography or 0.0), 0.0)
        diag = self.engine.get_runtime_diagnostics()
        self.assertGreaterEqual(int(diag.get("scan_star_skipped_unmapped") or 0), 1)

if __name__ == "__main__":
    unittest.main()
