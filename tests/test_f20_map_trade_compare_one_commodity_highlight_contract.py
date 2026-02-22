from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F20MapTradeCompareOneCommodityHighlightContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts_a = _iso(now - timedelta(hours=2))
        ts_b = _iso(now - timedelta(hours=5))

        # System A: better SELL price for Gold
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts_a,
                "StarSystem": "F20_TRADE_A",
                "SystemAddress": 77101,
                "SystemId64": 77101,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_a,
                "StarSystem": "F20_TRADE_A",
                "SystemAddress": 77101,
                "StationName": "A Market",
                "StationType": "Orbis Starport",
                "MarketID": 7710101,
                "DistFromStarLS": 400,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_a,
                "StarSystem": "F20_TRADE_A",
                "StationName": "A Market",
                "MarketID": 7710101,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 9000, "SellPrice": 13000},
                    {"Name_Localised": "Silver", "BuyPrice": 3000, "SellPrice": 6000},
                ],
            },
            path=db_path,
        )

        # System B: better BUY price for Gold (cheaper buy)
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_b,
                "StarSystem": "F20_TRADE_B",
                "SystemAddress": 77102,
                "SystemId64": 77102,
                "StarPos": [12.0, 0.0, 3.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_b,
                "StarSystem": "F20_TRADE_B",
                "SystemAddress": 77102,
                "StationName": "B Exchange",
                "StationType": "Coriolis Starport",
                "MarketID": 7710201,
                "DistFromStarLS": 1200,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_b,
                "StarSystem": "F20_TRADE_B",
                "StationName": "B Exchange",
                "MarketID": 7710201,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000},
                    {"Name_Localised": "Palladium", "BuyPrice": 40000, "SellPrice": 52000},
                ],
            },
            path=db_path,
        )

    def test_trade_compare_populates_panel_and_highlights_map_nodes(self) -> None:
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

                frame.layer_trade_var.set(True)
                result = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertTrue(bool(result.get("ok")))

                combo_values = tuple(frame.trade_commodity_combo.cget("values") or ())
                combo_values_text = [str(v) for v in combo_values]
                self.assertIn("Gold", combo_values_text)

                frame.trade_compare_commodity_var.set("Gold")
                trade_result = frame._run_trade_compare("Gold")
                root.update_idletasks()

                self.assertTrue(bool(trade_result.get("ok")))
                self.assertGreaterEqual(int(trade_result.get("sell_count") or 0), 2)
                self.assertGreaterEqual(int(trade_result.get("buy_count") or 0), 2)
                self.assertGreaterEqual(int(trade_result.get("highlight_nodes") or 0), 2)

                rows = frame.trade_compare_tree.get_children()
                self.assertGreaterEqual(len(rows), 4)
                first_values = frame.trade_compare_tree.item(rows[0], "values")
                self.assertIn(str(first_values[0]), {"SELL", "BUY"})

                highlighted = set(frame._trade_highlight_node_keys or set())
                self.assertGreaterEqual(len(highlighted), 2)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_trade_highlight")), 0)

                status = str(frame.map_status_var.get() or "").lower()
                self.assertIn("trade compare", status)
                self.assertIn("gold", status)

                # If trade layer is hidden, compare still works but visual highlight disappears.
                frame.layer_trade_var.set(False)
                frame._redraw_scene()
                root.update_idletasks()
                self.assertEqual(len(frame.map_canvas.find_withtag("layer_trade_highlight")), 0)
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
        self.assertIn("get_known_commodities", content)
        self.assertIn("get_top_prices", content)
        self.assertIn("_run_trade_compare", content)
        self.assertIn("layer_trade_highlight", content)


if __name__ == "__main__":
    unittest.main()

