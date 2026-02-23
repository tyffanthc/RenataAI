from __future__ import annotations

import json
import os
import queue
import tempfile
import unittest
from unittest.mock import patch

from logic.event_handler import EventHandler
from logic.logbook_feed import build_logbook_info_rows, build_logbook_summary_snapshot
from logic.logbook_feed_cache import (
    append_logbook_feed_cache_item,
    load_logbook_feed_cache,
)
from logic import player_local_db
from logic.utils import MSG_QUEUE


class F19QualityGatesAndSmokeTests(unittest.TestCase):
    def _drain_queue(self) -> list[tuple[str, object]]:
        items: list[tuple[str, object]] = []
        while True:
            try:
                items.append(MSG_QUEUE.get_nowait())
            except queue.Empty:
                break
        return items

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "db", "player_local.db")
        self._runtime_db_path = player_local_db.default_playerdb_path()
        self._default_path_patch = patch(
            "logic.player_local_db.default_playerdb_path",
            return_value=self._db_path,
        )
        self._default_path_patch.start()
        self._drain_queue()

    def tearDown(self) -> None:
        self._drain_queue()
        self._default_path_patch.stop()
        self._tmp.cleanup()

    def test_quality_gate_f19_feed_items_have_class_summary_chips_and_raw_event(self) -> None:
        self.assertNotEqual(os.path.abspath(self._db_path), os.path.abspath(self._runtime_db_path))
        router = EventHandler()
        for ev in (
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T22:00:00Z",
                "StarSystem": "F19_QG_SYS_A",
                "JumpDist": 33.9,
            },
            {
                "event": "SellOrganicData",
                "timestamp": "2026-02-22T22:01:00Z",
                "StarSystem": "F19_QG_SYS_A",
                "StationName": "F19 QG Vista",
                "TotalEarnings": 1234567,
            },
            {
                "event": "HullDamage",
                "timestamp": "2026-02-22T22:02:00Z",
                "StarSystem": "F19_QG_SYS_A",
                "Health": 0.92,
            },
        ):
            router.handle_event(json.dumps(ev))

        feed_items = [
            payload for msg_type, payload in self._drain_queue() if msg_type == "logbook_journal_feed"
        ]
        self.assertEqual(len(feed_items), 3)
        for item in feed_items:
            self.assertIsInstance(item, dict)
            self.assertTrue(str(item.get("event_name") or "").strip())
            self.assertTrue(str(item.get("event_class") or "").strip())
            self.assertTrue(str(item.get("summary") or "").strip())
            self.assertIsInstance(item.get("chips"), list)
            self.assertIsInstance(item.get("raw_event"), dict)

    def test_quality_gate_f19_info_rows_and_summary_snapshot_contract(self) -> None:
        items = [
            {
                "timestamp": "2026-02-22T22:10:00Z",
                "event_name": "FSDJump",
                "event_class": "Nawigacja",
                "system_name": "F19_SUMMARY_SYS",
                "summary": "Skok do F19_SUMMARY_SYS",
                "chips": [],
                "raw_event": {"event": "FSDJump", "StarSystem": "F19_SUMMARY_SYS"},
            },
            {
                "timestamp": "2026-02-22T22:11:00Z",
                "event_name": "SellExplorationData",
                "event_class": "Eksploracja",
                "system_name": "F19_SUMMARY_SYS",
                "summary": "Sprzedaz danych eksploracji: 500000 cr",
                "chips": [{"kind": "CR", "value": "500000"}],
                "raw_event": {"event": "SellExplorationData", "TotalEarnings": 500000},
            },
            {
                "timestamp": "2026-02-22T22:12:00Z",
                "event_name": "SellOrganicData",
                "event_class": "Exobio",
                "system_name": "F19_SUMMARY_SYS",
                "summary": "Sprzedaz danych exobio: 1500000 cr",
                "chips": [{"kind": "CR", "value": "1500000"}],
                "raw_event": {"event": "SellOrganicData", "TotalEarnings": 1500000},
            },
        ]

        info_rows = build_logbook_info_rows(items[2])
        labels = {str(row.get("label") or "") for row in info_rows}
        self.assertIn("Klasa", labels)
        self.assertIn("Event", labels)
        self.assertIn("Sprzedaz", labels)

        snapshot = build_logbook_summary_snapshot(items)
        self.assertEqual(int(snapshot.get("total_events") or 0), 3)
        self.assertEqual(int(snapshot.get("jump_count") or 0), 1)
        self.assertEqual(int(snapshot.get("uc_sold_cr") or 0), 500000)
        self.assertEqual(int(snapshot.get("vista_sold_cr") or 0), 1500000)
        self.assertEqual(int(snapshot.get("total_sold_cr") or 0), 2000000)
        self.assertEqual(int((snapshot.get("class_counts") or {}).get("Exobio") or 0), 1)

    def test_smoke_f19_journal_replay_sequence_to_feed_cache_and_summary(self) -> None:
        self.assertNotEqual(os.path.abspath(self._db_path), os.path.abspath(self._runtime_db_path))
        router = EventHandler()
        sequence = [
            {
                "event": "Location",
                "timestamp": "2026-02-22T23:00:00Z",
                "StarSystem": "F19_SMOKE_ORIGIN",
            },
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T23:01:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "JumpDist": 17.4,
            },
            {
                "event": "Touchdown",
                "timestamp": "2026-02-22T23:02:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "Body": "F19_SMOKE_TARGET A 1",
            },
            {
                "event": "ScanOrganic",
                "timestamp": "2026-02-22T23:03:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "Body": "F19_SMOKE_TARGET A 1",
                "Species_Localised": "Stratum Tectonicas",
                "ScanType": "Analyse",
            },
            {
                "event": "HullDamage",
                "timestamp": "2026-02-22T23:04:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "Health": 0.88,
            },
            {
                "event": "Interdicted",
                "timestamp": "2026-02-22T23:05:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "Interdictor": "NPC Pirate",
                "Submitted": False,
            },
            {
                "event": "EscapeInterdiction",
                "timestamp": "2026-02-22T23:05:20Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "Interdictor": "NPC Pirate",
            },
            {
                "event": "Docked",
                "timestamp": "2026-02-22T23:06:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "StationName": "F19 Smoke Station",
            },
            {
                "event": "SellExplorationData",
                "timestamp": "2026-02-22T23:07:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "StationName": "F19 Smoke Station",
                "TotalEarnings": 1200000,
            },
            {
                "event": "SellOrganicData",
                "timestamp": "2026-02-22T23:08:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "StationName": "F19 Smoke Station",
                "TotalEarnings": 3300000,
            },
        ]
        for ev in sequence:
            router.handle_event(json.dumps(ev))

        feed_items = [
            payload for msg_type, payload in self._drain_queue() if msg_type == "logbook_journal_feed"
        ]
        self.assertGreaterEqual(len(feed_items), 9)

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = os.path.join(tmp, "logbook", "feed.jsonl")
            for item in feed_items:
                ok = append_logbook_feed_cache_item(dict(item), path=cache_path, limit=250)
                self.assertTrue(ok)
            restored = load_logbook_feed_cache(path=cache_path, limit=250)

        self.assertEqual(len(restored), len(feed_items))
        snapshot = build_logbook_summary_snapshot(restored)
        self.assertEqual(int(snapshot.get("jump_count") or 0), 1)
        self.assertEqual(int(snapshot.get("landing_count") or 0), 1)
        self.assertEqual(int(snapshot.get("dock_count") or 0), 1)
        self.assertEqual(int(snapshot.get("hull_incidents") or 0), 1)
        self.assertEqual(int(snapshot.get("interdictions") or 0), 1)
        self.assertEqual(int(snapshot.get("interdiction_escapes") or 0), 1)
        self.assertEqual(int(snapshot.get("uc_sold_cr") or 0), 1200000)
        self.assertEqual(int(snapshot.get("vista_sold_cr") or 0), 3300000)
        self.assertEqual(int(snapshot.get("total_sold_cr") or 0), 4500000)


if __name__ == "__main__":
    unittest.main()
