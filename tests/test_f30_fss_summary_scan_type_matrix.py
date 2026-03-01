from __future__ import annotations

import json
import unittest

from app.state import app_state
from logic.events import exploration_fss_events as fss_events


def _j(event: str, **fields) -> str:
    payload = {"event": event}
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False)


class F30FssSummaryScanTypeMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()

    def tearDown(self) -> None:
        fss_events.reset_fss_progress()

    def _run_runtime_full_scan(self, system_name: str, scan_type: str | None) -> None:
        app_state.set_system(system_name)
        fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 2}, gui_ref=None)
        first = {"event": "Scan", "BodyName": f"{system_name} A 1", "BodyID": 1}
        second = {"event": "Scan", "BodyName": f"{system_name} A 2", "BodyID": 2}
        if scan_type is not None:
            first["ScanType"] = scan_type
            second["ScanType"] = scan_type
        fss_events.handle_scan(first, gui_ref=None)
        fss_events.handle_scan(second, gui_ref=None)

    def _run_bootstrap_scan_type(self, system_name: str, scan_type: str | None) -> dict:
        line_1 = _j("Location", StarSystem=system_name)
        line_2 = _j("FSSDiscoveryScan", BodyCount=2)
        scan_a = {"BodyName": f"{system_name} A 1", "BodyID": 11}
        scan_b = {"BodyName": f"{system_name} A 2", "BodyID": 12}
        if scan_type is not None:
            scan_a["ScanType"] = scan_type
            scan_b["ScanType"] = scan_type
        line_3 = _j("Scan", **scan_a)
        line_4 = _j("Scan", **scan_b)
        return fss_events.bootstrap_fss_state_from_journal_lines([line_1, line_2, line_3, line_4], max_lines=50)

    def test_runtime_scan_type_matrix_for_manual_gate(self) -> None:
        matrix = [
            ("AutoScan", False, True),
            ("NavBeaconDetail", False, True),
            ("Basic", False, False),
            ("Detailed", True, True),
            ("Analyse", False, False),  # unknown values default to non-manual (safe)
            (None, False, False),
        ]
        for idx, (scan_type, expected_manual, expected_pending) in enumerate(matrix):
            with self.subTest(scan_type=scan_type):
                fss_events.reset_fss_progress()
                self._run_runtime_full_scan(f"F30_MATRIX_RUNTIME_{idx}", scan_type)
                self.assertEqual(bool(fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN), expected_manual)
                self.assertEqual(bool(fss_events.FSS_PENDING_EXIT_SUMMARY), expected_pending)

    def test_runtime_mixed_scans_arms_summary_only_after_detailed(self) -> None:
        system = "F30_MATRIX_RUNTIME_MIXED"
        app_state.set_system(system)
        fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 2}, gui_ref=None)
        fss_events.handle_scan(
            {"event": "Scan", "BodyName": f"{system} A 1", "BodyID": 1, "ScanType": "AutoScan"},
            gui_ref=None,
        )
        self.assertFalse(bool(fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN))
        self.assertFalse(bool(fss_events.FSS_PENDING_EXIT_SUMMARY))
        fss_events.handle_scan(
            {"event": "Scan", "BodyName": f"{system} A 2", "BodyID": 2, "ScanType": "Detailed"},
            gui_ref=None,
        )
        self.assertTrue(bool(fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN))
        self.assertEqual(str(fss_events.FSS_LAST_MANUAL_SCAN_TYPE or ""), "detailed")
        self.assertTrue(bool(fss_events.FSS_PENDING_EXIT_SUMMARY))

    def test_bootstrap_scan_type_matrix_for_manual_gate(self) -> None:
        matrix = [
            ("AutoScan", False),
            ("NavBeaconDetail", False),
            ("Basic", False),
            ("Detailed", True),
            ("Analyse", False),
            (None, False),
        ]
        for idx, (scan_type, expected_manual) in enumerate(matrix):
            with self.subTest(scan_type=scan_type):
                fss_events.reset_fss_progress()
                stats = self._run_bootstrap_scan_type(f"F30_MATRIX_BOOT_{idx}", scan_type)
                self.assertTrue(bool(stats.get("restored")))
                self.assertTrue(bool(fss_events.FSS_HAD_DISCOVERY_SCAN))
                self.assertEqual(bool(fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN), expected_manual)


if __name__ == "__main__":
    unittest.main()
