import unittest

from logic.journal_navigation import (
    extract_navigation_chips,
    resolve_chip_nav_target,
    resolve_entry_nav_target,
    resolve_logbook_nav_target,
)


class NavIntegrationEntryAndChipsTests(unittest.TestCase):
    def test_entry_target_uses_station_body_system_fallback(self) -> None:
        self.assertEqual(
            resolve_entry_nav_target(
                {
                    "location": {
                        "system_name": "Diagaundri",
                        "body_name": "Diagaundri A 1",
                        "station_name": "Ray Gateway",
                    }
                }
            ),
            "Ray Gateway",
        )
        self.assertEqual(
            resolve_entry_nav_target(
                {
                    "location": {
                        "system_name": "Diagaundri",
                        "body_name": "Diagaundri A 1",
                        "station_name": None,
                    }
                }
            ),
            "Diagaundri A 1",
        )
        self.assertEqual(
            resolve_entry_nav_target(
                {"location": {"system_name": "Diagaundri", "body_name": None, "station_name": None}}
            ),
            "Diagaundri",
        )

    def test_logbook_target_uses_station_body_system_fallback(self) -> None:
        self.assertEqual(
            resolve_logbook_nav_target(
                {
                    "system_name": "Colonia",
                    "body_name": "Colonia 1",
                    "station_name": "Jaques Station",
                }
            ),
            "Jaques Station",
        )
        self.assertEqual(
            resolve_logbook_nav_target(
                {
                    "system_name": "Colonia",
                    "body_name": "Colonia 1",
                    "station_name": "",
                }
            ),
            "Colonia 1",
        )
        self.assertEqual(
            resolve_logbook_nav_target({"system_name": "Colonia", "body_name": None, "station_name": None}),
            "Colonia",
        )

    def test_extract_navigation_chips_keeps_only_system_station(self) -> None:
        chips = extract_navigation_chips(
            {
                "chips": [
                    {"kind": "EVENT", "value": "MarketSell"},
                    {"kind": "SYSTEM", "value": "Diagaundri"},
                    {"kind": "STATION", "value": "Ray Gateway"},
                    {"kind": "BODY", "value": "Diagaundri A 1"},
                    {"kind": "SYSTEM", "value": "Diagaundri"},
                ]
            }
        )
        self.assertEqual(
            chips,
            [
                {"kind": "SYSTEM", "value": "Diagaundri"},
                {"kind": "STATION", "value": "Ray Gateway"},
            ],
        )

    def test_chip_target_allows_only_system_or_station(self) -> None:
        self.assertEqual(
            resolve_chip_nav_target({"kind": "SYSTEM", "value": "Achenar"}),
            "Achenar",
        )
        self.assertEqual(
            resolve_chip_nav_target({"kind": "STATION", "value": "Jameson Memorial"}),
            "Jameson Memorial",
        )
        self.assertIsNone(resolve_chip_nav_target({"kind": "BODY", "value": "Achenar 3"}))


if __name__ == "__main__":
    unittest.main()

