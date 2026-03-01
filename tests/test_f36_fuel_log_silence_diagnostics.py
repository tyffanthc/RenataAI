from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.events import fuel_events


class F36FuelLogSilenceDiagnosticsTests(unittest.TestCase):
    def test_silent_startup_reasons_use_debug_not_main_log(self) -> None:
        with (
            patch("logic.events.fuel_events.log_event_throttled") as throttled_mock,
            patch("logic.events.fuel_events._FUEL_LOGGER.debug") as debug_mock,
        ):
            fuel_events._log_uncertain_startup_sample_event(reason="missing_fuel_and_capacity", action="ignored")
            fuel_events._log_uncertain_startup_sample_event(reason="zero_without_capacity", action="ignored")
            fuel_events._log_uncertain_startup_sample_event(
                reason="ambiguous_numeric_without_capacity_fallback_applied",
                action="fallback_applied",
            )

        self.assertEqual(throttled_mock.call_count, 0)
        self.assertEqual(debug_mock.call_count, 3)

    def test_non_silent_reason_keeps_throttled_runtime_diagnostic(self) -> None:
        with (
            patch("logic.events.fuel_events.log_event_throttled") as throttled_mock,
            patch("logic.events.fuel_events._FUEL_LOGGER.debug") as debug_mock,
        ):
            fuel_events._log_uncertain_startup_sample_event(
                reason="bootstrap_current_system_unknown",
                action="ignored",
            )

        self.assertEqual(debug_mock.call_count, 0)
        self.assertEqual(throttled_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()

