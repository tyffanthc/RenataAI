import copy
import unittest

from logic.journal_entry_mapping import (
    MVP_EVENT_CATEGORIES,
    build_mvp_entry_draft,
    default_category_for_event,
    is_mvp_journal_event,
)


class JournalToEntryMappingActionsTests(unittest.TestCase):
    def test_mvp_event_detection_and_default_categories(self) -> None:
        for event_name, category in MVP_EVENT_CATEGORIES.items():
            self.assertTrue(is_mvp_journal_event(event_name))
            self.assertEqual(default_category_for_event(event_name), category)
        self.assertFalse(is_mvp_journal_event("Loadout"))
        self.assertIsNone(default_category_for_event("Loadout"))

    def test_trade_mapping_is_deterministic(self) -> None:
        event = {
            "event": "MarketSell",
            "timestamp": "2026-02-16T21:00:00Z",
            "StarSystem": "Diagaundri",
            "StationName": "Ray Gateway",
            "Type": "Gold",
            "Count": 256,
            "SellPrice": 11437,
        }
        draft_a = build_mvp_entry_draft(copy.deepcopy(event))
        draft_b = build_mvp_entry_draft(copy.deepcopy(event))
        self.assertEqual(draft_a, draft_b)
        self.assertEqual((draft_a or {}).get("category_path"), "Handel/Transakcje")
        self.assertIn("Sprzedaz", (draft_a or {}).get("title") or "")
        self.assertEqual(((draft_a or {}).get("payload") or {}).get("trade", {}).get("total"), 256 * 11437)
        self.assertEqual(((draft_a or {}).get("source") or {}).get("event_name"), "MarketSell")

    def test_scan_and_mining_mapping_contract(self) -> None:
        scan = build_mvp_entry_draft(
            {
                "event": "Scan",
                "timestamp": "2026-02-16T21:01:00Z",
                "StarSystem": "Achenar",
                "BodyName": "Achenar 1",
                "PlanetClass": "Earth-like world",
            }
        )
        self.assertEqual((scan or {}).get("category_path"), "Eksploracja/Odkrycia")
        self.assertEqual((scan or {}).get("entry_type"), "exploration_scan")
        self.assertIn("scan", (scan or {}).get("tags") or [])

        mining = build_mvp_entry_draft(
            {
                "event": "ProspectedAsteroid",
                "timestamp": "2026-02-16T21:02:00Z",
                "StarSystem": "Colonia",
                "BodyName": "Colonia AB 2 Ring A",
                "Content": "Platinum",
                "ContentPercent": 18.5,
            }
        )
        self.assertEqual((mining or {}).get("category_path"), "Gornictwo/Hotspoty")
        self.assertEqual((mining or {}).get("entry_type"), "mining_hotspot")
        self.assertEqual(
            ((mining or {}).get("payload") or {}).get("mining", {}).get("concentration_percent"),
            18.5,
        )

    def test_unsupported_event_returns_none(self) -> None:
        self.assertIsNone(build_mvp_entry_draft({"event": "Loadout"}))
        self.assertIsNone(build_mvp_entry_draft({"event": "Commander"}))


if __name__ == "__main__":
    unittest.main()

