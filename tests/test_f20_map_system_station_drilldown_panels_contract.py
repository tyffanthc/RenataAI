from __future__ import annotations

import os
import tempfile
import unittest

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


class F20MapSystemStationDrilldownPanelsContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": "2026-02-22T11:00:00Z",
                "StarSystem": "F20_DRILL_ORIGIN",
                "SystemAddress": 88100,
                "SystemId64": 88100,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T11:10:00Z",
                "StarSystem": "F20_DRILL_TARGET",
                "SystemAddress": 88101,
                "SystemId64": 88101,
                "StarPos": [12.0, 0.0, 4.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": "2026-02-22T11:12:00Z",
                "StarSystem": "F20_DRILL_TARGET",
                "SystemAddress": 88101,
                "StationName": "Drill Port",
                "StationType": "Orbis Starport",
                "MarketID": 7788101,
                "DistFromStarLS": 432,
                "StationServices": ["Commodities", "Universal Cartographics", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": "2026-02-22T11:13:00Z",
                "StarSystem": "F20_DRILL_TARGET",
                "StationName": "Drill Port",
                "MarketID": 7788101,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 8000, "SellPrice": 12000, "Stock": 50},
                    {"Name_Localised": "Silver", "BuyPrice": 3000, "SellPrice": 5400, "Stock": 150},
                ],
            },
            path=db_path,
        )

    def test_map_drilldown_populates_system_station_and_market_panels(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            from gui.tabs.journal_map import JournalMapTab
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            self._seed_playerdb(db_path)
            provider = MapDataProvider(db_path=db_path)

            frame = None
            try:
                frame = JournalMapTab(root, data_provider=provider)
                frame.pack(fill="both", expand=True)
                root.update_idletasks()
                root.geometry("1200x720")
                root.update()

                result = frame.reload_from_playerdb()
                self.assertTrue(bool(result.get("ok")))
                self.assertGreaterEqual(int(result.get("nodes") or 0), 2)

                target_key = None
                for key, node in (frame._nodes or {}).items():
                    if str(getattr(node, "system_name", "")) == "F20_DRILL_TARGET":
                        target_key = str(key)
                        break
                self.assertTrue(bool(target_key), "expected map node for F20_DRILL_TARGET")

                sel = frame.select_system_node(str(target_key))
                root.update_idletasks()

                self.assertTrue(bool(sel.get("ok")))
                self.assertEqual(str(sel.get("system_name") or ""), "F20_DRILL_TARGET")
                self.assertGreaterEqual(int(sel.get("stations_count") or 0), 1)
                self.assertEqual(str(frame._selected_node_key or ""), str(target_key))

                system_details = str(frame.system_details_var.get() or "")
                self.assertIn("F20_DRILL_TARGET", system_details)
                self.assertIn("Stacje (playerdb):", system_details)

                station_rows = frame.system_stations_tree.get_children()
                self.assertGreaterEqual(len(station_rows), 1)
                station_values = frame.system_stations_tree.item(station_rows[0], "values")
                self.assertEqual(str(station_values[0]), "Drill Port")

                station_details = str(frame.station_details_var.get() or "")
                self.assertIn("Drill Port", station_details)
                self.assertIn("MarketID", station_details)

                market_rows = frame.station_market_tree.get_children()
                self.assertGreaterEqual(len(market_rows), 1)
                market_values = frame.station_market_tree.item(market_rows[0], "values")
                self.assertIn("2026-02-22T11:13:00Z", str(market_values[0]))
                self.assertEqual(str(market_values[1]), "2")

                status = str(frame.map_status_var.get() or "")
                self.assertIn("wybrano system", status.lower())
            finally:
                try:
                    if frame is not None:
                        frame.destroy()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass

    def test_contract_strings_present_in_journal_map_impl(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "journal_map.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as h:
            content = h.read()
        self.assertIn("def select_system_node", content)
        self.assertIn("get_stations_for_system", content)
        self.assertIn("get_market_last_seen", content)
        self.assertIn("<<TreeviewSelect>>", content)


if __name__ == "__main__":
    unittest.main()

