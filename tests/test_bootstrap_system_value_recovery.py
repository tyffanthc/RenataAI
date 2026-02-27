from __future__ import annotations

import json
import unittest

from app.state import app_state
from logic.events.exploration_value_recovery import recover_system_value_from_journal_lines
from logic.exit_summary import ExitSummaryGenerator
from logic.system_value_engine import SystemValueEngine


class BootstrapSystemValueRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_engine = getattr(app_state, "system_value_engine", None)
        self._saved_exit_summary = getattr(app_state, "exit_summary", None)

        src_engine = self._saved_engine
        self.assertIsNotNone(src_engine)
        fresh_engine = SystemValueEngine((src_engine.exobio_df, src_engine.carto_df))
        app_state.system_value_engine = fresh_engine
        app_state.exit_summary = ExitSummaryGenerator(fresh_engine)
        app_state.current_system = "BOOTSTRAP_RECOVERY_SYS"
        fresh_engine.set_current_system("BOOTSTRAP_RECOVERY_SYS")

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.system_value_engine = self._saved_engine
        app_state.exit_summary = self._saved_exit_summary

    def test_recovery_rebuilds_non_zero_value_from_scan_lines(self) -> None:
        lines = [
            json.dumps({"event": "Location", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS A 1",
                    "PlanetClass": "Earth-like world",
                    "TerraformState": "Terraformable",
                    "WasDiscovered": False,
                    "WasMapped": True,
                }
            ),
            json.dumps(
                {
                    "event": "ScanOrganic",
                    "BodyName": "BOOTSTRAP_RECOVERY_BODY",
                    "Species_Localised": "Aleoida Arcus",
                }
            ),
        ]
        stats = recover_system_value_from_journal_lines(lines, max_lines=200)
        totals = app_state.system_value_engine.calculate_totals()

        self.assertTrue(bool(stats.get("recovered")))
        self.assertGreaterEqual(int(stats.get("events") or 0), 2)
        self.assertGreaterEqual(int(stats.get("scan_events") or 0), 1)
        self.assertGreaterEqual(int(stats.get("bio_events") or 0), 1)
        self.assertGreaterEqual(int(stats.get("used_system_fallback") or 0), 1)
        self.assertGreater(float(totals.get("total") or 0.0), 0.0)

    def test_recovery_is_dedup_safe_for_duplicate_scan_lines(self) -> None:
        scan_line = json.dumps(
            {
                "event": "Scan",
                "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                "BodyName": "BOOTSTRAP_RECOVERY_SYS B 1",
                "PlanetClass": "Earth-like world",
                "TerraformState": "Terraformable",
                "WasDiscovered": False,
                "WasMapped": True,
            }
        )
        lines = [
            json.dumps({"event": "Location", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
            scan_line,
            scan_line,
        ]
        recover_system_value_from_journal_lines(lines, max_lines=200)
        stats = app_state.system_value_engine.get_system_stats("BOOTSTRAP_RECOVERY_SYS")
        self.assertIsNotNone(stats)
        self.assertEqual(int(getattr(stats, "total_scanned_bodies", 0)), 1)

    def test_recovery_upgrades_fss_value_when_saa_scan_complete_is_present(self) -> None:
        lines = [
            json.dumps({"event": "Location", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS C 1",
                    "PlanetClass": "Water world",
                    "TerraformState": "Terraformable",
                    "WasDiscovered": False,
                    "WasMapped": False,
                }
            ),
            json.dumps(
                {
                    "event": "SAAScanComplete",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS C 1",
                }
            ),
        ]
        recover_system_value_from_journal_lines(lines, max_lines=200)
        stats = app_state.system_value_engine.get_system_stats("BOOTSTRAP_RECOVERY_SYS")
        self.assertIsNotNone(stats)
        # Water World row in project science data should produce >0 and be upgraded by DSS.
        self.assertGreater(float(getattr(stats, "c_cartography", 0.0) or 0.0), 0.0)
        body_state = dict((getattr(stats, "cartography_bodies", {}) or {}).get("BOOTSTRAP_RECOVERY_SYS C 1") or {})
        self.assertTrue(bool(body_state.get("mapped_accounted")))

    def test_recovery_reports_diagnostics_for_scan_and_dss_outcomes(self) -> None:
        lines = [
            json.dumps({"event": "Location", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS STAR",
                    "BodyType": "Star",
                    "StarType": "K",
                    "WasDiscovered": False,
                    "WasMapped": False,
                }
            ),
            json.dumps(
                {
                    "event": "SAAScanComplete",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS MISSING",
                }
            ),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS D 1",
                    "PlanetClass": "Water world",
                    "TerraformState": "Terraformable",
                    "WasDiscovered": False,
                    "WasMapped": False,
                }
            ),
            json.dumps(
                {
                    "event": "SAAScanComplete",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS D 1",
                }
            ),
        ]
        result = recover_system_value_from_journal_lines(lines, max_lines=500)
        self.assertGreaterEqual(int(result.get("scan_counted") or 0), 1)
        self.assertGreaterEqual(int(result.get("dss_upgrade_applied") or 0), 1)
        self.assertGreaterEqual(int(result.get("dss_skipped_missing_prior_scan") or 0), 1)
        diagnostics = [str(x) for x in list(result.get("diagnostics") or [])]
        self.assertTrue(any("Scan counted" in x for x in diagnostics))
        self.assertTrue(any("DSS upgrade applied" in x for x in diagnostics))
        self.assertTrue(any("missing prior Scan" in x for x in diagnostics))

    def test_recovery_applies_sell_domain_resets_for_carto_and_exobio(self) -> None:
        lines = [
            json.dumps({"event": "Location", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
            json.dumps(
                {
                    "event": "Scan",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "BodyName": "BOOTSTRAP_RECOVERY_SYS SELL 1",
                    "PlanetClass": "Water world",
                    "TerraformState": "Terraformable",
                    "WasDiscovered": False,
                    "WasMapped": True,
                }
            ),
            json.dumps(
                {
                    "event": "ScanOrganic",
                    "StarSystem": "BOOTSTRAP_RECOVERY_SYS",
                    "Species_Localised": "Aleoida Arcus",
                    "FirstDiscovery": True,
                    "FirstFootfall": True,
                }
            ),
            json.dumps({"event": "MultiSellExplorationData", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
            json.dumps({"event": "SellOrganicData", "StarSystem": "BOOTSTRAP_RECOVERY_SYS"}),
        ]

        result = recover_system_value_from_journal_lines(lines, max_lines=500)
        stats = app_state.system_value_engine.get_system_stats("BOOTSTRAP_RECOVERY_SYS")
        self.assertIsNotNone(stats)
        self.assertEqual(float(getattr(stats, "c_cartography", 0.0) or 0.0), 0.0)
        self.assertEqual(float(getattr(stats, "c_exobiology", 0.0) or 0.0), 0.0)
        self.assertEqual(float(getattr(stats, "bonus_discovery", 0.0) or 0.0), 0.0)
        self.assertGreaterEqual(int(result.get("sale_reset_cartography") or 0), 1)
        self.assertGreaterEqual(int(result.get("sale_reset_exobiology") or 0), 1)
        diagnostics = [str(x) for x in list(result.get("diagnostics") or [])]
        self.assertTrue(any("Sell reset cartography" in x for x in diagnostics))
        self.assertTrue(any("Sell reset exobiology" in x for x in diagnostics))


if __name__ == "__main__":
    unittest.main()
