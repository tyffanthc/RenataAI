import os
import tempfile
import unittest

from logic.entry_repository import EntryRepository


class F9EntryManualMetadataEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = EntryRepository(path=os.path.join(self._tmp.name, "entries.jsonl"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_manual_metadata_edit_updates_category_and_tags(self) -> None:
        created = self.repo.create_entry(
            {
                "category_path": "Handel/Transakcje",
                "title": "Sprzedaz zlota",
                "body": "Test",
                "tags": ["trade", "auto"],
                "entry_type": "trade_route",
                "source": {
                    "kind": "journal_event",
                    "event_name": "MarketSell",
                    "event_time": "2026-02-17T21:00:00Z",
                },
                "payload": {"score": 87},
            }
        )

        updated = self.repo.update_entry(
            str(created.get("id")),
            {
                "category_path": "Moje/Ulubione",
                "tags": ["auto", "manualny", "manualny"],
            },
        )

        self.assertEqual(updated.get("category_path"), "Moje/Ulubione")
        self.assertEqual(updated.get("tags"), ["auto", "manualny"])
        self.assertEqual(updated.get("entry_type"), created.get("entry_type"))
        self.assertEqual(updated.get("source"), created.get("source"))
        self.assertEqual(updated.get("payload"), created.get("payload"))

    def test_manual_tag_edit_allows_empty_selection(self) -> None:
        created = self.repo.create_entry(
            {
                "category_path": "Eksploracja/Odkrycia",
                "title": "Scan",
                "body": "A 1",
                "tags": ["exploration", "elw"],
            }
        )
        updated = self.repo.update_entry(str(created.get("id")), {"tags": []})
        self.assertEqual(updated.get("tags"), [])
        self.assertEqual(updated.get("category_path"), "Eksploracja/Odkrycia")


if __name__ == "__main__":
    unittest.main()
