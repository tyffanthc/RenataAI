import os
import tempfile
import unittest

from logic.entry_repository import EntryRepository
from logic.entry_templates import EntryTemplateError, build_template_entry


class PinboardTemplatesBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "entries.jsonl")
        self.repo = EntryRepository(path=self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_pinboard_filter_returns_only_pinned_entries(self) -> None:
        a = self.repo.create_entry(
            {"category_path": "Test/A", "title": "A", "body": ""}
        )
        b = self.repo.create_entry(
            {"category_path": "Test/B", "title": "B", "body": ""}
        )
        self.repo.pin_entry(a["id"], True)

        pinned = self.repo.list_entries(filters={"is_pinned": True})
        self.assertEqual([item["id"] for item in pinned], [a["id"]])

        unpinned = self.repo.list_entries(filters={"is_pinned": False})
        self.assertEqual([item["id"] for item in unpinned], [b["id"]])

    def test_mining_hotspot_template_contract(self) -> None:
        payload = build_template_entry(
            "mining_hotspot",
            {
                "commodity": "Platinum",
                "system_name": "Colonia",
                "body_name": "Colonia AB 2 Ring A",
                "ring_type": "Metallic",
                "hotspot_strength": "High",
                "res_nearby": "HighRES",
            },
        )
        self.assertEqual(payload.get("category_path"), "Gornictwo/Hotspoty")
        self.assertEqual(payload.get("entry_type"), "mining_hotspot")
        self.assertIn("Platinum hotspot - Colonia AB 2 Ring A", payload.get("title") or "")
        self.assertEqual(
            ((payload.get("payload") or {}).get("mining_hotspot") or {}).get("ring_type"),
            "Metallic",
        )

        created = self.repo.create_entry(payload)
        self.assertEqual(created.get("entry_type"), "mining_hotspot")

    def test_trade_route_template_contract(self) -> None:
        payload = build_template_entry(
            "trade_route",
            {
                "from_system": "Diagaundri",
                "from_station": "Ray Gateway",
                "to_system": "Achenar",
                "to_station": "Dawes Hub",
                "profit_per_t": "12890",
                "pad_size": "L",
                "distance_ls": "84",
                "permit_required": False,
            },
        )
        self.assertEqual(payload.get("category_path"), "Handel/Trasy")
        self.assertEqual(payload.get("entry_type"), "trade_route")
        self.assertIn("Ray Gateway -> Dawes Hub", payload.get("title") or "")
        trade_payload = (payload.get("payload") or {}).get("trade_route") or {}
        self.assertEqual(trade_payload.get("from_station"), "Ray Gateway")
        self.assertEqual(trade_payload.get("to_station"), "Dawes Hub")
        self.assertEqual(trade_payload.get("profit_per_t"), 12890.0)

        created = self.repo.create_entry(payload)
        self.assertEqual(created.get("entry_type"), "trade_route")

    def test_template_validation_errors(self) -> None:
        with self.assertRaises(EntryTemplateError):
            build_template_entry("unknown_template", {})
        with self.assertRaises(EntryTemplateError):
            build_template_entry(
                "trade_route",
                {"from_station": "Ray Gateway"},
            )


if __name__ == "__main__":
    unittest.main()

