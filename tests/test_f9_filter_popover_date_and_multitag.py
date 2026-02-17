import os
import tempfile
import unittest

from gui.tabs.logbook import _merge_default_tags, _to_iso_date
from logic.entry_repository import EntryRepository


class F9FilterPopoverDateAndMultiTagTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = EntryRepository(path=os.path.join(self._tmp.name, "entries.jsonl"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_tags_mode_all_vs_any_contract(self) -> None:
        a = self.repo.create_entry(
            {
                "category_path": "Test/A",
                "title": "A",
                "body": "",
                "tags": ["trade", "safe"],
            }
        )
        b = self.repo.create_entry(
            {
                "category_path": "Test/B",
                "title": "B",
                "body": "",
                "tags": ["trade", "risk"],
            }
        )
        c = self.repo.create_entry(
            {
                "category_path": "Test/C",
                "title": "C",
                "body": "",
                "tags": ["exploration"],
            }
        )

        all_mode = self.repo.list_entries(
            filters={"tags": ["trade", "safe"], "tags_mode": "all"},
            sort="title_az",
        )
        any_mode = self.repo.list_entries(
            filters={"tags": ["trade", "safe"], "tags_mode": "any"},
            sort="title_az",
        )

        self.assertEqual([item.get("id") for item in all_mode], [a.get("id")])
        self.assertEqual(
            [item.get("id") for item in any_mode],
            [a.get("id"), b.get("id")],
        )
        self.assertNotIn(c.get("id"), [item.get("id") for item in any_mode])

    def test_date_to_is_end_of_day_inclusive(self) -> None:
        self.repo.create_entry(
            {
                "category_path": "Test/D1",
                "title": "Morning",
                "body": "",
                "created_at": "2026-02-17T08:00:00Z",
                "updated_at": "2026-02-17T08:00:00Z",
            }
        )
        self.repo.create_entry(
            {
                "category_path": "Test/D2",
                "title": "Evening",
                "body": "",
                "created_at": "2026-02-17T22:30:00Z",
                "updated_at": "2026-02-17T22:30:00Z",
            }
        )
        self.repo.create_entry(
            {
                "category_path": "Test/D3",
                "title": "Next day",
                "body": "",
                "created_at": "2026-02-18T00:10:00Z",
                "updated_at": "2026-02-18T00:10:00Z",
            }
        )

        date_from = _to_iso_date("2026-02-17", end_of_day=False)
        date_to = _to_iso_date("2026-02-17", end_of_day=True)
        items = self.repo.list_entries(
            filters={"date_from": date_from, "date_to": date_to},
            sort="title_az",
        )
        self.assertEqual([item.get("title") for item in items], ["Evening", "Morning"])

    def test_default_tag_suggestions_include_trade_and_mining(self) -> None:
        merged = _merge_default_tags([])
        self.assertIn("trade", merged)
        self.assertIn("market", merged)
        self.assertIn("mining", merged)
        self.assertIn("prospecting", merged)


if __name__ == "__main__":
    unittest.main()
