from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.utils import renata_log


class LogEventThrottledCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        renata_log._THROTTLE_LAST.clear()

    def tearDown(self) -> None:
        renata_log._THROTTLE_LAST.clear()

    def test_new_signature_still_works(self) -> None:
        with patch("logic.utils.renata_log.log_event") as log_mock:
            first = renata_log.log_event_throttled(
                "trade:test:new",
                1000,
                "TRADE",
                "new signature message",
                context="abc",
            )
            second = renata_log.log_event_throttled(
                "trade:test:new",
                1000,
                "TRADE",
                "new signature message",
                context="abc",
            )

        self.assertTrue(first)
        self.assertFalse(second)
        log_mock.assert_called_once()

    def test_legacy_signature_is_supported(self) -> None:
        with patch("logic.utils.renata_log.log_event") as log_mock:
            first = renata_log.log_event_throttled(
                "WARN",
                "TRADE_STATION_PICKER_CHROME_FAILED",
                "Spansh Trade: station picker chrome styling failed",
                cooldown_sec=60.0,
                context="spansh.trade.station_picker.chrome",
            )
            second = renata_log.log_event_throttled(
                "WARN",
                "TRADE_STATION_PICKER_CHROME_FAILED",
                "Spansh Trade: station picker chrome styling failed",
                cooldown_sec=60.0,
                context="spansh.trade.station_picker.chrome",
            )

        self.assertTrue(first)
        self.assertFalse(second)
        log_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
