import os
import tempfile
import unittest

from logic.entry_repository import EntryRepository
from logic.journal_navigation import resolve_entry_nav_target, resolve_entry_nav_target_typed


class F9EntryContextMenuActionsAndMoveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = EntryRepository(path=os.path.join(self._tmp.name, "entries.jsonl"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_typed_target_resolver_uses_station_body_system_fallback(self) -> None:
        station = resolve_entry_nav_target_typed(
            {
                "location": {
                    "system_name": "Diagaundri",
                    "body_name": "Diagaundri A 1",
                    "station_name": "Ray Gateway",
                }
            }
        )
        body = resolve_entry_nav_target_typed(
            {
                "location": {
                    "system_name": "Diagaundri",
                    "body_name": "Diagaundri A 1",
                    "station_name": None,
                }
            }
        )
        system = resolve_entry_nav_target_typed(
            {"location": {"system_name": "Diagaundri", "body_name": None, "station_name": None}}
        )

        self.assertEqual(station, ("STATION", "Ray Gateway"))
        self.assertEqual(body, ("BODY", "Diagaundri A 1"))
        self.assertEqual(system, ("SYSTEM", "Diagaundri"))
        self.assertEqual(resolve_entry_nav_target({"location": {"system_name": "Diagaundri"}}), "Diagaundri")

    def test_move_category_keeps_entry_contract_fields(self) -> None:
        created = self.repo.create_entry(
            {
                "category_path": "Handel/Trasy",
                "title": "Trasa A-B",
                "body": "Opis",
                "tags": ["trade", "route"],
                "source": {
                    "kind": "journal_event",
                    "event_name": "MarketSell",
                    "event_time": "2026-02-16T22:00:00Z",
                },
                "payload": {"quality": "high"},
                "location": {
                    "system_name": "Diagaundri",
                    "station_name": "Ray Gateway",
                },
            }
        )
        self.repo.pin_entry(created["id"], True)

        moved = self.repo.update_entry(
            created["id"],
            {
                "category_path": "Eksploracja/Odkrycia",
            },
        )

        self.assertEqual(moved.get("id"), created.get("id"))
        self.assertEqual(moved.get("category_path"), "Eksploracja/Odkrycia")
        self.assertEqual(moved.get("title"), created.get("title"))
        self.assertEqual(moved.get("tags"), created.get("tags"))
        self.assertEqual(moved.get("source"), created.get("source"))
        self.assertEqual(moved.get("payload"), created.get("payload"))
        self.assertTrue(bool(moved.get("is_pinned")))


if __name__ == "__main__":
    unittest.main()
