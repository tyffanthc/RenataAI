from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import exploration_fss_events as fss_events


class F28FssDiscoveryScanDoesNotResetProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        fss_events.reset_fss_progress()
        app_state.current_system = "F28_FSS_DISCOVERY_SCAN_RESET_SYSTEM"

    def tearDown(self) -> None:
        fss_events.reset_fss_progress()

    def test_repeated_fss_discovery_scan_keeps_partial_progress(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 19
        fss_events.FSS_DISCOVERED = 17
        fss_events.FSS_SCANNED_BODIES = {f"Body-{i}" for i in range(17)}
        fss_events.FSS_25_WARNED = True
        fss_events.FSS_50_WARNED = True
        fss_events.FSS_75_WARNED = True

        fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 19}, gui_ref=None)

        self.assertEqual(fss_events.FSS_TOTAL_BODIES, 19)
        self.assertEqual(fss_events.FSS_DISCOVERED, 17)
        self.assertEqual(len(fss_events.FSS_SCANNED_BODIES), 17)
        self.assertTrue(fss_events.FSS_25_WARNED)
        self.assertTrue(fss_events.FSS_50_WARNED)
        self.assertTrue(fss_events.FSS_75_WARNED)

    def test_repeated_fss_discovery_scan_can_update_total_without_resetting_progress(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 9
        fss_events.FSS_DISCOVERED = 6
        fss_events.FSS_SCANNED_BODIES = {f"Body-{i}" for i in range(6)}

        fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 10}, gui_ref=None)

        self.assertEqual(fss_events.FSS_TOTAL_BODIES, 10)
        self.assertEqual(fss_events.FSS_DISCOVERED, 6)
        self.assertEqual(len(fss_events.FSS_SCANNED_BODIES), 6)

    def test_rejects_inconsistent_bodycount_lower_than_discovered_progress(self) -> None:
        fss_events.FSS_TOTAL_BODIES = 0
        fss_events.FSS_DISCOVERED = 5
        fss_events.FSS_SCANNED_BODIES = {f"Body-{i}" for i in range(5)}
        fss_events.FSS_25_WARNED = False
        fss_events.FSS_50_WARNED = False
        fss_events.FSS_75_WARNED = False

        with patch("logic.events.exploration_fss_events.log_event_throttled") as log_mock:
            fss_events.handle_fss_discovery_scan({"event": "FSSDiscoveryScan", "BodyCount": 2}, gui_ref=None)

        self.assertEqual(fss_events.FSS_TOTAL_BODIES, 0)
        self.assertEqual(fss_events.FSS_DISCOVERED, 5)
        self.assertEqual(len(fss_events.FSS_SCANNED_BODIES), 5)
        log_mock.assert_called_once()
        self.assertIn("body_count_inconsistent", str(log_mock.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()
