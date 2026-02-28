from __future__ import annotations

import json
import unittest

from logic.events import exploration_fss_events as fss_events


def _j(event: str, **fields) -> str:
    payload = {"event": event}
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False)


class TestF60BootstrapFssStateRecovery(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()

    def tearDown(self) -> None:
        fss_events.reset_fss_progress()

    def test_restores_latest_system_segment_progress(self) -> None:
        lines = [
            _j("FSDJump", StarSystem="OLD_SYS"),
            _j("FSSDiscoveryScan", BodyCount=4),
            _j("Scan", BodyName="OLD_SYS A 1", BodyID=1, ScanType="Detailed"),
            _j("FSDJump", StarSystem="NEW_SYS"),
            _j("Scan", BodyName="NEW_SYS A", BodyID=11, ScanType="AutoScan"),
            _j("FSSDiscoveryScan", BodyCount=12),
            _j("Scan", BodyName="NEW_SYS B 1", BodyID=12, ScanType="Detailed"),
            _j("Scan", BodyName="NEW_SYS B 2", BodyID=13, ScanType="Detailed"),
        ]

        stats = fss_events.bootstrap_fss_state_from_journal_lines(lines, max_lines=200)

        self.assertTrue(bool(stats.get("restored")))
        self.assertEqual(int(fss_events.FSS_TOTAL_BODIES), 12)
        self.assertEqual(int(fss_events.FSS_DISCOVERED), 3)
        self.assertTrue(bool(fss_events.FSS_HAD_DISCOVERY_SCAN))
        self.assertTrue(bool(fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN))

    def test_deduplicates_scan_entries_by_body_keys(self) -> None:
        lines = [
            _j("Location", StarSystem="DEDUP_SYS"),
            _j("FSSDiscoveryScan", BodyCount=5),
            _j("Scan", BodyName="DEDUP_SYS A 1", BodyID=101, ScanType="Detailed"),
            _j("Scan", BodyName="DEDUP_SYS A 1", BodyID=101, ScanType="Detailed"),
            _j("Scan", BodyName="DEDUP_SYS A 2", BodyID=102, ScanType="Detailed"),
        ]

        stats = fss_events.bootstrap_fss_state_from_journal_lines(lines, max_lines=200)

        self.assertTrue(bool(stats.get("restored")))
        self.assertEqual(int(fss_events.FSS_DISCOVERED), 2)
        self.assertEqual(int(fss_events.FSS_TOTAL_BODIES), 5)

    def test_bootstrap_navbeacon_only_does_not_restore_manual_progress(self) -> None:
        lines = [
            _j("Location", StarSystem="NAVBEACON_SYS"),
            _j("FSSDiscoveryScan", BodyCount=2),
            _j("Scan", BodyName="NAVBEACON_SYS A 1", BodyID=201, ScanType="NavBeaconDetail"),
            _j("Scan", BodyName="NAVBEACON_SYS A 2", BodyID=202, ScanType="NavBeaconDetail"),
        ]

        stats = fss_events.bootstrap_fss_state_from_journal_lines(lines, max_lines=200)

        self.assertTrue(bool(stats.get("restored")))
        self.assertTrue(bool(fss_events.FSS_HAD_DISCOVERY_SCAN))
        self.assertFalse(bool(fss_events.FSS_HAD_MANUAL_PROGRESS_SCAN))
        self.assertEqual(int(fss_events.FSS_DISCOVERED), 2)
        self.assertEqual(int(fss_events.FSS_TOTAL_BODIES), 2)


if __name__ == "__main__":
    unittest.main()
