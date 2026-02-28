from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F31MapTradeCompareProvenanceAndClearContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts_a = _iso(now - timedelta(hours=2))
        ts_b = _iso(now - timedelta(hours=4))

        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts_a,
                "StarSystem": "F31_TRADE_A",
                "SystemAddress": 991001,
                "SystemId64": 991001,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_a,
                "StarSystem": "F31_TRADE_A",
                "SystemAddress": 991001,
                "StationName": "A Market",
                "StationType": "Orbis Starport",
                "MarketID": 99100101,
                "StationServices": ["Commodities"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_a,
                "StarSystem": "F31_TRADE_A",
                "StationName": "A Market",
                "MarketID": 99100101,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 9000, "SellPrice": 12000},
                    {"Name_Localised": "Silver", "BuyPrice": 3200, "SellPrice": 6000},
                ],
            },
            path=db_path,
        )

        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_b,
                "StarSystem": "F31_TRADE_B",
                "SystemAddress": 991002,
                "SystemId64": 991002,
                "StarPos": [13.0, 0.0, 5.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_b,
                "StarSystem": "F31_TRADE_B",
                "SystemAddress": 991002,
                "StationName": "B Exchange",
                "StationType": "Coriolis Starport",
                "MarketID": 99100201,
                "StationServices": ["Commodities"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_b,
                "StarSystem": "F31_TRADE_B",
                "StationName": "B Exchange",
                "MarketID": 99100201,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000},
                    {"Name_Localised": "Palladium", "BuyPrice": 39000, "SellPrice": 52000},
                ],
            },
            path=db_path,
        )

    def test_trade_compare_rows_include_system_station_and_clear_resets_state(self) -> None:
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
                result = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertTrue(bool(result.get("ok")))

                columns = tuple(frame.trade_compare_tree["columns"] or ())
                self.assertEqual(columns, ("mode", "commodity", "price", "age"))

                node_key = frame._find_node_key_by_system_name("F31_TRADE_A")
                self.assertTrue(bool(node_key))
                select_result = frame.select_system_node(str(node_key))
                self.assertTrue(bool(select_result.get("ok")))

                frame._set_trade_selected_commodities(["Gold", "Silver"])
                compare_result = frame._run_trade_compare_multi(["Gold", "Silver"])
                root.update_idletasks()
                self.assertTrue(bool(compare_result.get("ok")))

                rows = frame.trade_compare_tree.get_children()
                self.assertGreaterEqual(len(rows), 4)
                first_values = tuple(frame.trade_compare_tree.item(rows[0], "values") or ())
                self.assertGreaterEqual(len(first_values), 4)
                self.assertEqual(
                    {str((row or {}).get("system_name") or "") for row in (frame._trade_compare_rows or [])},
                    {"F31_TRADE_A"},
                )
                self.assertEqual(
                    {str((row or {}).get("station_name") or "") for row in (frame._trade_compare_rows or [])},
                    {"A Market"},
                )

                self.assertGreaterEqual(len(frame._trade_highlight_node_keys), 1)
                self.assertEqual(str(frame.trade_clear_btn.cget("state")), "normal")

                frame._on_trade_compare_clear_clicked()
                root.update_idletasks()

                self.assertEqual(len(frame.trade_compare_tree.get_children()), 0)
                self.assertEqual(list(frame._trade_selected_commodities or []), [])
                self.assertEqual(str(frame.trade_compare_commodity_var.get() or ""), "")
                self.assertEqual(len(frame._trade_compare_rows_by_iid), 0)
                self.assertEqual(len(frame._trade_highlight_node_keys), 0)
                self.assertEqual(str(frame.trade_clear_btn.cget("state")), "disabled")
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
