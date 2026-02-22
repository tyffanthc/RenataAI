from __future__ import annotations

import os
import tempfile
import unittest

from logic.logbook_feed_cache import (
    append_logbook_feed_cache_item,
    clear_logbook_feed_cache,
    load_logbook_feed_cache,
)


class F19LogbookFeedCachePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self._tmp.name, "logbook", "feed.jsonl")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _item(self, idx: int) -> dict:
        return {
            "timestamp": f"2026-02-22T20:{idx:02d}:00Z",
            "event_name": "FSDJump",
            "system_name": f"SYS-{idx}",
            "summary": f"Skok {idx}",
            "raw_event": {"event": "FSDJump", "StarSystem": f"SYS-{idx}"},
        }

    def test_append_and_restore_keeps_recent_items_with_retention(self) -> None:
        for idx in range(5):
            ok = append_logbook_feed_cache_item(self._item(idx), path=self.cache_path, limit=3)
            self.assertTrue(ok)

        rows = load_logbook_feed_cache(path=self.cache_path, limit=3)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row.get("system_name") for row in rows], ["SYS-2", "SYS-3", "SYS-4"])

    def test_load_tolerates_corrupted_tail_line(self) -> None:
        append_logbook_feed_cache_item(self._item(1), path=self.cache_path, limit=10)
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "a", encoding="utf-8") as handle:
            handle.write("{\"event_name\": \"FSDJump\"")
            handle.write("\n")

        rows = load_logbook_feed_cache(path=self.cache_path, limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("system_name"), "SYS-1")

    def test_clear_removes_cache_file(self) -> None:
        append_logbook_feed_cache_item(self._item(1), path=self.cache_path, limit=10)
        self.assertTrue(os.path.isfile(self.cache_path))
        clear_logbook_feed_cache(path=self.cache_path)
        self.assertFalse(os.path.exists(self.cache_path))

    def test_append_skips_duplicate_feed_item_signature(self) -> None:
        item = self._item(3)
        ok1 = append_logbook_feed_cache_item(item, path=self.cache_path, limit=10)
        ok2 = append_logbook_feed_cache_item(dict(item), path=self.cache_path, limit=10)
        self.assertTrue(ok1)
        self.assertTrue(ok2)

        rows = load_logbook_feed_cache(path=self.cache_path, limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("system_name"), "SYS-3")


if __name__ == "__main__":
    unittest.main()
