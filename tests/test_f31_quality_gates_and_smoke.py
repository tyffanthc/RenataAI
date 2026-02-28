from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F31QualityGatesAndSmokeTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts_a = _iso(now - timedelta(hours=1))
        ts_b = _iso(now - timedelta(hours=3))

        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts_a,
                "StarSystem": "F31_QG_ALPHA",
                "SystemAddress": 901001,
                "SystemId64": 901001,
                "StarPos": [0.0, 0.0, 0.0],
                "StarClass": "N",
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_a,
                "StarSystem": "F31_QG_ALPHA",
                "SystemAddress": 901001,
                "StationName": "Alpha Port",
                "StationType": "Orbis Starport",
                "MarketID": 90100101,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_a,
                "StarSystem": "F31_QG_ALPHA",
                "StationName": "Alpha Port",
                "MarketID": 90100101,
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
                "StarSystem": "F31_QG_BETA",
                "SystemAddress": 901002,
                "SystemId64": 901002,
                "StarPos": [10.0, 0.0, 5.0],
                "StarClass": "H",
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_b,
                "StarSystem": "F31_QG_BETA",
                "SystemAddress": 901002,
                "StationName": "Beta Exchange",
                "StationType": "Coriolis Starport",
                "MarketID": 90100201,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_b,
                "StarSystem": "F31_QG_BETA",
                "StationName": "Beta Exchange",
                "MarketID": 90100201,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000},
                    {"Name_Localised": "Palladium", "BuyPrice": 39000, "SellPrice": 52000},
                ],
            },
            path=db_path,
        )

    def test_quality_gate_f31_contract_strings_present(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "journal_map.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
        for snippet in (
            "TIME_RANGE_SLIDER_VALUES",
            "FRESHNESS_SLIDER_VALUES",
            "_show_star_legend_popup",
            "_hide_star_legend_popup",
            "Wyczysc compare",
            "_on_trade_compare_clear_clicked",
            'columns=("mode", "commodity", "price", "age")',
            "_trade_compare_scope_from_selection",
        ):
            self.assertIn(snippet, content)

    def test_smoke_f31_map_legend_popup_trade_compare_clear(self) -> None:
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
                root.geometry("1320x820")
                root.update()

                frame.layer_trade_var.set(True)
                result = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertTrue(bool(result.get("ok")))
                self.assertGreaterEqual(int(result.get("nodes") or 0), 2)

                node_key = frame._find_node_key_by_system_name("F31_QG_ALPHA")
                self.assertTrue(bool(node_key))
                select_result = frame.select_system_node(str(node_key))
                self.assertTrue(bool(select_result.get("ok")))

                frame._show_star_legend_popup()
                root.update_idletasks()
                self.assertIsNotNone(getattr(frame, "_star_legend_popup", None))
                frame._hide_star_legend_popup(force=True)
                root.update_idletasks()
                self.assertIsNone(getattr(frame, "_star_legend_popup", None))

                frame._set_trade_selected_commodities(["Gold", "Silver"])
                compare = frame._run_trade_compare_multi(["Gold", "Silver"])
                root.update_idletasks()
                self.assertTrue(bool(compare.get("ok")))
                self.assertGreater(len(frame.trade_compare_tree.get_children()), 0)
                self.assertGreaterEqual(len(frame._trade_highlight_node_keys), 1)

                frame._on_trade_compare_clear_clicked()
                root.update_idletasks()
                self.assertEqual(len(frame.trade_compare_tree.get_children()), 0)
                self.assertEqual(len(frame._trade_highlight_node_keys), 0)
                self.assertEqual(str(frame.trade_compare_commodity_var.get() or ""), "")
                self.assertEqual(str(frame.trade_clear_btn.cget("state")), "disabled")
                self.assertTrue(str(frame.map_status_var.get() or "").strip())
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
