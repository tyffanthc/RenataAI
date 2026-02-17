from __future__ import annotations

import os
import tempfile
import unittest

from app.state import app_state
from logic.entry_repository import EntryRepository
from logic.entry_templates import build_template_entry
from logic.journal_entry_mapping import (
    MVP_EVENT_CATEGORIES,
    build_mvp_entry_draft,
    is_mvp_journal_event,
)
from logic.journal_navigation import (
    extract_navigation_chips,
    resolve_chip_nav_target,
    resolve_entry_nav_target,
    resolve_logbook_nav_target,
)
from logic.logbook_feed import build_logbook_feed_item, is_captain_journal_event


def _event_fixture(event_name: str) -> dict:
    base = {
        "event": event_name,
        "timestamp": "2026-02-16T22:00:00Z",
        "StarSystem": "Diagaundri",
        "StationName": "Ray Gateway",
        "BodyName": "Diagaundri A 1",
    }
    if event_name in {"MarketBuy", "MarketSell"}:
        base.update({"Type": "Gold", "Count": 64, "BuyPrice": 7000, "SellPrice": 12000})
    if event_name == "FSDJump":
        base.update({"JumpDist": 22.3, "FuelUsed": 1.2})
    if event_name == "Scan":
        base.update({"PlanetClass": "Earth-like world"})
    if event_name == "SAAScanComplete":
        base.update({"SignalsFound": 3})
    if event_name == "ProspectedAsteroid":
        base.update({"Content": "Platinum", "ContentPercent": 18.5})
    return base


class F8QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_awareness = app_state.get_route_awareness_snapshot()

    def tearDown(self) -> None:
        app_state.update_route_awareness(
            route_mode=str(self._saved_awareness.get("route_mode") or "idle"),
            route_target=str(self._saved_awareness.get("route_target") or ""),
            route_progress_percent=int(self._saved_awareness.get("route_progress_percent") or 0),
            next_system=str(self._saved_awareness.get("next_system") or ""),
            is_off_route=bool(self._saved_awareness.get("is_off_route")),
            source="test.f8.quality.restore",
        )

    def test_event_matrix_whitelist_and_mapping_contract(self) -> None:
        for event_name, expected_category in MVP_EVENT_CATEGORIES.items():
            self.assertTrue(is_mvp_journal_event(event_name), event_name)
            self.assertTrue(is_captain_journal_event(event_name), event_name)

            ev = _event_fixture(event_name)
            feed_item = build_logbook_feed_item(ev)
            self.assertIsNotNone(feed_item, event_name)
            self.assertEqual((feed_item or {}).get("default_category"), expected_category)

            draft = build_mvp_entry_draft(ev)
            self.assertIsNotNone(draft, event_name)
            self.assertEqual((draft or {}).get("category_path"), expected_category)
            self.assertEqual(((draft or {}).get("source") or {}).get("event_name"), event_name)

    def test_navigation_from_entry_and_chips_contract(self) -> None:
        feed_item = build_logbook_feed_item(_event_fixture("MarketSell"))
        self.assertIsNotNone(feed_item)
        self.assertEqual(resolve_logbook_nav_target(feed_item), "Ray Gateway")

        chips = extract_navigation_chips(feed_item)
        self.assertEqual(len(chips), 2)
        self.assertEqual(resolve_chip_nav_target(chips[0]), chips[0].get("value"))
        self.assertIn(chips[0].get("kind"), {"SYSTEM", "STATION"})
        self.assertIn(chips[1].get("kind"), {"SYSTEM", "STATION"})

    def test_entry_pinboard_templates_and_intent_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = EntryRepository(path=os.path.join(tmp, "entries.jsonl"))

            mining = build_template_entry(
                "mining_hotspot",
                {
                    "commodity": "Platinum",
                    "system_name": "Colonia",
                    "body_name": "Colonia AB 2 Ring A",
                    "ring_type": "Metallic",
                },
            )
            trade = build_template_entry(
                "trade_route",
                {
                    "from_system": "Diagaundri",
                    "from_station": "Ray Gateway",
                    "to_system": "Achenar",
                    "to_station": "Dawes Hub",
                    "profit_per_t": 12000,
                    "pad_size": "L",
                    "distance_ls": 84,
                    "permit_required": False,
                },
            )

            created_mining = repo.create_entry(mining)
            created_trade = repo.create_entry(trade)
            repo.pin_entry(created_trade["id"], True)

            pinned = repo.list_entries(filters={"is_pinned": True}, sort="updated_desc")
            self.assertEqual(len(pinned), 1)
            self.assertEqual(pinned[0]["id"], created_trade["id"])
            self.assertEqual(pinned[0]["entry_type"], "trade_route")
            self.assertEqual(created_mining.get("entry_type"), "mining_hotspot")

            target = resolve_entry_nav_target(created_trade)
            self.assertEqual(target, "Ray Gateway")

            snap = app_state.set_route_intent(target, source="test.f8.quality.intent")
            self.assertEqual(str(snap.get("route_mode")), "intent")
            self.assertEqual(str(snap.get("route_target") or ""), "Ray Gateway")
            self.assertEqual(int(snap.get("route_progress_percent") or 0), 0)


if __name__ == "__main__":
    unittest.main()

