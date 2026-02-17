import os
import tempfile
import unittest

from logic.entry_repository import EntryRepository, EntryValidationError


class EntryModelAndStorageBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "entries.jsonl")
        self.repo = EntryRepository(path=self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_entry_minimal_contract(self) -> None:
        entry = self.repo.create_entry(
            {
                "category_path": "Handel/Transakcje",
                "title": "Sprzedaz zlota",
                "body": "Sprzedane 256t",
            }
        )
        self.assertTrue(entry.get("id"))
        self.assertEqual(entry.get("schema_version"), 1)
        self.assertEqual(entry.get("category_path"), "Handel/Transakcje")
        self.assertEqual(entry.get("title"), "Sprzedaz zlota")
        self.assertEqual((entry.get("source") or {}).get("kind"), "manual")
        self.assertEqual((entry.get("location") or {}).get("system_name"), None)

    def test_create_requires_required_fields(self) -> None:
        with self.assertRaises(EntryValidationError):
            self.repo.create_entry({"title": "Brak kategorii", "body": "x"})
        with self.assertRaises(EntryValidationError):
            self.repo.create_entry({"category_path": "Eksploracja", "body": "x"})

    def test_update_entry_merges_nested_fields(self) -> None:
        created = self.repo.create_entry(
            {
                "category_path": "Eksploracja/Odkrycia",
                "title": "Scan",
                "body": "Body found",
                "location": {"system_name": "Alpha", "body_name": "A 1"},
            }
        )
        updated = self.repo.update_entry(
            created["id"],
            {
                "title": "Scan update",
                "location": {"station_name": "Ray Gateway"},
                "tags": ["trade", "exploration", "trade"],
            },
        )
        self.assertEqual(updated.get("title"), "Scan update")
        self.assertEqual((updated.get("location") or {}).get("system_name"), "Alpha")
        self.assertEqual((updated.get("location") or {}).get("station_name"), "Ray Gateway")
        self.assertEqual(updated.get("tags"), ["trade", "exploration"])

    def test_delete_entry_removes_record(self) -> None:
        created = self.repo.create_entry(
            {"category_path": "Test", "title": "To delete", "body": ""}
        )
        deleted = self.repo.delete_entry(created["id"])
        self.assertEqual(deleted["id"], created["id"])
        self.assertIsNone(self.repo.get_entry(created["id"]))

    def test_list_filters_and_sorting(self) -> None:
        e1 = self.repo.create_entry(
            {
                "category_path": "Handel/Transakcje",
                "title": "MarketSell Gold",
                "body": "Diagaundri",
                "tags": ["trade", "sell"],
                "location": {"system_name": "Diagaundri", "station_name": "Ray Gateway"},
                "source": {"kind": "journal_event", "event_name": "MarketSell"},
            }
        )
        e2 = self.repo.create_entry(
            {
                "category_path": "Eksploracja/Odkrycia",
                "title": "SAA scan",
                "body": "Earth-like",
                "tags": ["exploration"],
                "location": {"system_name": "Achenar"},
                "source": {"kind": "manual"},
            }
        )
        e3 = self.repo.create_entry(
            {
                "category_path": "Gornictwo/Hotspoty",
                "title": "Prospected",
                "body": "Platinum",
                "tags": ["mining"],
                "location": {"system_name": "Colonia"},
                "source": {"kind": "journal_event", "event_name": "ProspectedAsteroid"},
            }
        )

        text_filtered = self.repo.list_entries(filters={"text": "gold"})
        self.assertEqual(len(text_filtered), 1)
        self.assertEqual(text_filtered[0]["id"], e1["id"])

        tags_filtered = self.repo.list_entries(filters={"tags": ["trade", "sell"]})
        self.assertEqual(len(tags_filtered), 1)
        self.assertEqual(tags_filtered[0]["id"], e1["id"])

        source_filtered = self.repo.list_entries(filters={"source_kind": "journal_event"})
        self.assertEqual({item["id"] for item in source_filtered}, {e1["id"], e3["id"]})

        system_sorted = self.repo.list_entries(sort="system_az")
        self.assertEqual(
            [item["id"] for item in system_sorted],
            [e2["id"], e3["id"], e1["id"]],
        )

    def test_pin_and_tag_helpers(self) -> None:
        created = self.repo.create_entry(
            {"category_path": "Eksploracja", "title": "Pinned", "body": ""}
        )
        pinned = self.repo.pin_entry(created["id"], True)
        self.assertTrue(bool(pinned.get("is_pinned")))
        self.assertTrue(bool(pinned.get("pinned_at")))

        unpinned = self.repo.pin_entry(created["id"], False)
        self.assertFalse(bool(unpinned.get("is_pinned")))
        self.assertIsNone(unpinned.get("pinned_at"))

        tagged = self.repo.add_tags(created["id"], ["A", "b", "a"])
        self.assertEqual(tagged.get("tags"), ["a", "b"])

        cleaned = self.repo.remove_tags(created["id"], ["a"])
        self.assertEqual(cleaned.get("tags"), ["b"])

    def test_create_entry_from_journal_sets_source_and_location(self) -> None:
        entry = self.repo.create_entry_from_journal(
            {
                "event": "Docked",
                "timestamp": "2026-02-16T20:00:00Z",
                "StarSystem": "Diagaundri",
                "StationName": "Ray Gateway",
                "BodyName": "Diagaundri A 1",
            },
            category_path="Ciekawe miejsca/Stacje",
        )
        self.assertEqual((entry.get("source") or {}).get("kind"), "journal_event")
        self.assertEqual((entry.get("source") or {}).get("event_name"), "Docked")
        self.assertEqual((entry.get("location") or {}).get("system_name"), "Diagaundri")
        self.assertEqual((entry.get("location") or {}).get("station_name"), "Ray Gateway")

    def test_persistence_roundtrip_jsonl(self) -> None:
        created = self.repo.create_entry(
            {
                "category_path": "Handel/Trasy",
                "title": "Route",
                "body": "A -> B",
                "tags": ["trade"],
            }
        )
        reloaded = EntryRepository(path=self.path)
        found = reloaded.get_entry(created["id"])
        self.assertIsNotNone(found)
        self.assertEqual((found or {}).get("title"), "Route")


if __name__ == "__main__":
    unittest.main()
