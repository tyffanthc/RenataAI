import json
import queue
import unittest

from logic.event_handler import EventHandler
from logic.logbook_feed import (
    build_logbook_feed_item,
    is_captain_journal_event,
)
from logic.utils import MSG_QUEUE


class LogbookJournalFeedWhitelistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._drain_queue()

    def tearDown(self) -> None:
        self._drain_queue()

    def _drain_queue(self) -> list[tuple[str, object]]:
        items: list[tuple[str, object]] = []
        while True:
            try:
                items.append(MSG_QUEUE.get_nowait())
            except queue.Empty:
                break
        return items

    def test_is_captain_journal_event_uses_whitelist(self) -> None:
        self.assertTrue(is_captain_journal_event("MarketSell"))
        self.assertTrue(is_captain_journal_event("FSDJump"))
        self.assertFalse(is_captain_journal_event("Loadout"))
        self.assertFalse(is_captain_journal_event("[APP]"))
        self.assertFalse(is_captain_journal_event("STATE_UPDATE"))

    def test_build_logbook_feed_item_formats_trade_event(self) -> None:
        item = build_logbook_feed_item(
            {
                "event": "MarketSell",
                "timestamp": "2026-02-16T20:00:00Z",
                "StarSystem": "Diagaundri",
                "StationName": "Ray Gateway",
                "Type": "Gold",
                "Count": 256,
                "SellPrice": 11437,
            }
        )
        self.assertIsNotNone(item)
        self.assertEqual((item or {}).get("event_name"), "MarketSell")
        self.assertEqual((item or {}).get("system_name"), "Diagaundri")
        self.assertIn("Sprzedaz", (item or {}).get("summary") or "")
        self.assertEqual((item or {}).get("default_category"), "Handel/Transakcje")
        self.assertIsInstance((item or {}).get("raw_event"), dict)
        chip_kinds = {chip.get("kind") for chip in (item or {}).get("chips") or []}
        self.assertIn("SYSTEM", chip_kinds)
        self.assertIn("STATION", chip_kinds)
        self.assertIn("COMMODITY", chip_kinds)

    def test_build_logbook_feed_item_rejects_non_whitelist(self) -> None:
        self.assertIsNone(build_logbook_feed_item({"event": "Loadout"}))
        self.assertIsNone(build_logbook_feed_item({"event": "[WARN]"}))
        self.assertIsNone(build_logbook_feed_item({"event": "Commander"}))

    def test_event_handler_queues_only_whitelisted_feed_items(self) -> None:
        router = EventHandler()

        router.handle_event(json.dumps({"event": "Loadout", "timestamp": "2026-02-16T20:00:00Z"}))
        router.handle_event(
            json.dumps(
                {
                    "event": "MarketSell",
                    "timestamp": "2026-02-16T20:01:00Z",
                    "StarSystem": "Diagaundri",
                    "StationName": "Ray Gateway",
                    "Type": "Gold",
                    "Count": 32,
                    "SellPrice": 10000,
                }
            )
        )
        router.handle_event("[APP] window chrome color unavailable")

        items = self._drain_queue()
        feed_items = [
            payload for msg_type, payload in items if msg_type == "logbook_journal_feed"
        ]
        self.assertEqual(len(feed_items), 1)
        self.assertEqual(feed_items[0].get("event_name"), "MarketSell")


if __name__ == "__main__":
    unittest.main()
