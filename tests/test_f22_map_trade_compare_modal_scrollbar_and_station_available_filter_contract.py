from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F22MapTradeCompareModalScrollbarAndStationAvailableFilterContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts_a = _iso(now - timedelta(hours=2))
        ts_b = _iso(now - timedelta(hours=4))

        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts_a,
                "StarSystem": "F22_TRADE_A",
                "SystemAddress": 551001,
                "SystemId64": 551001,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_a,
                "StarSystem": "F22_TRADE_A",
                "SystemAddress": 551001,
                "StationName": "A Market",
                "StationType": "Orbis Starport",
                "MarketID": 55100101,
                "StationServices": ["Commodities"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_a,
                "StarSystem": "F22_TRADE_A",
                "StationName": "A Market",
                "MarketID": 55100101,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 9000, "SellPrice": 12000},
                    {"Name_Localised": "Silver", "BuyPrice": 3000, "SellPrice": 5000},
                ],
            },
            path=db_path,
        )

        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_b,
                "StarSystem": "F22_TRADE_B",
                "SystemAddress": 551002,
                "SystemId64": 551002,
                "StarPos": [12.0, 0.0, 4.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_b,
                "StarSystem": "F22_TRADE_B",
                "SystemAddress": 551002,
                "StationName": "B Exchange",
                "StationType": "Coriolis Starport",
                "MarketID": 55100201,
                "StationServices": ["Commodities"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_b,
                "StarSystem": "F22_TRADE_B",
                "StationName": "B Exchange",
                "MarketID": 55100201,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000},
                    {"Name_Localised": "Palladium", "BuyPrice": 40000, "SellPrice": 52000},
                ],
            },
            path=db_path,
        )

    def test_trade_picker_has_scrollbars_and_station_available_filter(self) -> None:
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
                root.geometry("1280x760")
                root.update()

                frame.layer_trade_var.set(True)
                frame.reload_from_playerdb()
                root.update_idletasks()

                # Select system A -> auto-select station A with its market snapshot context.
                key_a = next(
                    key for key, node in frame._nodes.items() if str(getattr(node, "system_name", "")) == "F22_TRADE_A"
                )
                frame.select_system_node(key_a)
                root.update_idletasks()

                frame._open_trade_commodity_picker()
                root.update_idletasks()

                self.assertIsNotNone(frame._trade_picker_tree)
                self.assertIsNotNone(frame._trade_picker_tree_vsb)
                self.assertIsNotNone(frame._trade_picker_tree_hsb)
                self.assertEqual(str(frame._trade_picker_tree_vsb.cget("orient")), "vertical")
                self.assertEqual(str(frame._trade_picker_tree_hsb.cget("orient")), "horizontal")

                # Baseline list (global known commodities) should include Palladium from station B.
                all_rows = frame._trade_picker_tree.get_children()
                all_commodities = {str(frame._trade_picker_tree.item(iid, "values")[1]) for iid in all_rows}
                self.assertIn("Palladium", all_commodities)

                # Enable station filter -> only commodities from selected station A (Gold/Silver).
                self.assertIsNotNone(frame._trade_picker_station_only_var)
                frame._trade_picker_station_only_var.set(True)
                # Simulate transient loss of station row selection (focus/UI refresh) and ensure picker
                # falls back to the first visible station row for filtering.
                frame.system_stations_tree.selection_remove(*frame.system_stations_tree.selection())
                frame._trade_picker_on_station_only_toggled()
                root.update_idletasks()

                filtered_rows = frame._trade_picker_tree.get_children()
                filtered_commodities = {str(frame._trade_picker_tree.item(iid, "values")[1]) for iid in filtered_rows}
                self.assertIn("Gold", filtered_commodities)
                self.assertIn("Silver", filtered_commodities)
                self.assertNotIn("Palladium", filtered_commodities)

                status = str(frame._trade_picker_station_filter_status_var.get() or "")
                self.assertIn("A Market", status)
                self.assertIn("towary:", status)
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


if __name__ == "__main__":
    unittest.main()
