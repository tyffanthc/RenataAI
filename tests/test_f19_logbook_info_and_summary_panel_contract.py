import os
import unittest

from logic.logbook_feed import (
    build_logbook_feed_item,
    build_logbook_info_rows,
    build_logbook_summary_snapshot,
)


class F19LogbookInfoAndSummaryPanelContractTests(unittest.TestCase):
    def _item(self, event_payload: dict) -> dict:
        item = build_logbook_feed_item(event_payload)
        self.assertIsNotNone(item)
        return dict(item or {})

    def test_info_rows_include_core_fields_and_event_specific_details(self) -> None:
        item = self._item(
            {
                "event": "SellOrganicData",
                "timestamp": "2026-02-22T21:00:00Z",
                "StarSystem": "IC 289 Sector TJ-Q b5-0",
                "StationName": "Fan Survey",
                "TotalEarnings": 132555000,
            }
        )
        rows = build_logbook_info_rows(item)
        labels = {str(row.get("label")) for row in rows}
        self.assertIn("Klasa", labels)
        self.assertIn("Event", labels)
        self.assertIn("System", labels)
        self.assertIn("Stacja", labels)
        self.assertIn("Sprzedaz", labels)
        values_text = " | ".join(str(row.get("value") or "") for row in rows)
        self.assertIn("132555000 cr", values_text)

    def test_summary_snapshot_aggregates_uc_vista_jumps_and_incidents(self) -> None:
        feed_items = [
            self._item(
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-22T21:00:00Z",
                    "StarSystem": "A",
                    "JumpDist": 10.0,
                }
            ),
            self._item(
                {
                    "event": "Touchdown",
                    "timestamp": "2026-02-22T21:01:00Z",
                    "StarSystem": "A",
                    "Body": "A 1",
                }
            ),
            self._item(
                {
                    "event": "HullDamage",
                    "timestamp": "2026-02-22T21:02:00Z",
                    "StarSystem": "A",
                    "Health": 0.85,
                }
            ),
            self._item(
                {
                    "event": "SellExplorationData",
                    "timestamp": "2026-02-22T21:03:00Z",
                    "StarSystem": "A",
                    "TotalEarnings": 1200000,
                }
            ),
            self._item(
                {
                    "event": "SellOrganicData",
                    "timestamp": "2026-02-22T21:04:00Z",
                    "StarSystem": "A",
                    "TotalEarnings": 2500000,
                }
            ),
        ]
        snapshot = build_logbook_summary_snapshot(feed_items)
        self.assertEqual(int(snapshot.get("total_events") or 0), 5)
        self.assertEqual(int(snapshot.get("jump_count") or 0), 1)
        self.assertEqual(int(snapshot.get("landing_count") or 0), 1)
        self.assertEqual(int(snapshot.get("hull_incidents") or 0), 1)
        self.assertEqual(int(snapshot.get("uc_sold_cr") or 0), 1200000)
        self.assertEqual(int(snapshot.get("vista_sold_cr") or 0), 2500000)
        self.assertEqual(int(snapshot.get("total_sold_cr") or 0), 3700000)

    def test_logbook_ui_contains_informacje_and_podsumowanie_panel_contract(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "logbook.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()

        self.assertIn("Informacje (zdarzenie)", content)
        self.assertIn("Podsumowanie (aktualny filtr)", content)
        self.assertIn("logbook_summary_var", content)
        self.assertIn("def _refresh_logbook_info_panel", content)
        self.assertIn("def _refresh_logbook_summary_panel", content)
        self.assertIn("build_logbook_info_rows", content)
        self.assertIn("build_logbook_summary_snapshot", content)


if __name__ == "__main__":
    unittest.main()

