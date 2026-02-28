from __future__ import annotations

import unittest
from unittest.mock import patch

from gui.tabs.spansh.trade import TradeTab


class TradeStationPickerSystemNormalizationTests(unittest.TestCase):
    def test_system_name_for_station_lookup_strips_inline_station(self) -> None:
        self.assertEqual(TradeTab._system_name_for_station_lookup("Sol / Abraham Lincoln"), "Sol")
        self.assertEqual(TradeTab._system_name_for_station_lookup("Shinrarta Dezhra, Jameson Memorial"), "Shinrarta Dezhra")
        self.assertEqual(TradeTab._system_name_for_station_lookup("Achenar"), "Achenar")

    def test_load_station_candidates_queries_edsm_with_normalized_system(self) -> None:
        tab = TradeTab.__new__(TradeTab)
        tab._station_cache = {}
        tab._recent_stations = []
        tab._station_autocomplete_by_system = True
        tab._station_lookup_online = False

        with patch("gui.tabs.spansh.trade.is_edsm_enabled", return_value=True), patch(
            "gui.tabs.spansh.trade.edsm_stations_for_system",
            return_value=["Abraham Lincoln"],
        ) as edsm_mock:
            stations = TradeTab._load_station_candidates(tab, "Sol / Abraham Lincoln")

        edsm_mock.assert_called_once_with("Sol")
        self.assertEqual(stations, ["Abraham Lincoln"])


if __name__ == "__main__":
    unittest.main()
