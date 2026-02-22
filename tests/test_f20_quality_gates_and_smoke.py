from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F20QualityGatesAndSmokeTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts_recent = _iso(now - timedelta(hours=2))
        ts_mid = _iso(now - timedelta(days=2))
        ts_old = _iso(now - timedelta(days=15))

        # Travel systems
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts_recent,
                "StarSystem": "F20_QG_ORIGIN",
                "SystemAddress": 901001,
                "SystemId64": 901001,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_mid,
                "StarSystem": "F20_QG_TARGET_A",
                "SystemAddress": 901002,
                "SystemId64": 901002,
                "StarPos": [10.0, 0.0, 3.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_old,
                "StarSystem": "F20_QG_OLD",
                "SystemAddress": 901003,
                "SystemId64": 901003,
                "StarPos": [28.0, 0.0, 8.0],
            },
            path=db_path,
        )

        # Station A (UC + market)
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_mid,
                "StarSystem": "F20_QG_TARGET_A",
                "SystemAddress": 901002,
                "StationName": "QG Alpha Port",
                "StationType": "Orbis Starport",
                "MarketID": 9902001,
                "DistFromStarLS": 420,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_mid,
                "StarSystem": "F20_QG_TARGET_A",
                "StationName": "QG Alpha Port",
                "MarketID": 9902001,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 8500, "SellPrice": 12500},
                    {"Name_Localised": "Silver", "BuyPrice": 3000, "SellPrice": 5300},
                ],
            },
            path=db_path,
        )

        # Station B (Vista + market) in old system to be filtered by freshness
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_old,
                "StarSystem": "F20_QG_OLD",
                "SystemAddress": 901003,
                "StationName": "QG Old Vista Hub",
                "StationType": "Coriolis Starport",
                "MarketID": 9903001,
                "DistFromStarLS": 1900,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_old,
                "StarSystem": "F20_QG_OLD",
                "StationName": "QG Old Vista Hub",
                "MarketID": 9903001,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11100},
                    {"Name_Localised": "Palladium", "BuyPrice": 45000, "SellPrice": 59000},
                ],
            },
            path=db_path,
        )

    def test_quality_gate_f20_provider_contract_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            self._seed_playerdb(db_path)
            provider = MapDataProvider(db_path=db_path)

            nodes, nodes_meta = provider.get_system_nodes(time_range="all", source_filter="observed_only")
            self.assertGreaterEqual(len(nodes), 3)
            self.assertEqual(str(nodes_meta.get("source_filter") or ""), "observed_only")

            stations, _ = provider.get_stations_for_system(system_name="F20_QG_TARGET_A")
            self.assertGreaterEqual(len(stations), 1)
            self.assertEqual(str(stations[0].get("station_name") or ""), "QG Alpha Port")

            snapshots, _ = provider.get_market_last_seen(9902001, limit=3)
            self.assertGreaterEqual(len(snapshots), 1)
            self.assertTrue(any(str(i.get("commodity") or "") == "Gold" for i in (snapshots[0].get("items") or [])))

            commodities, _ = provider.get_known_commodities(time_range="all", freshness_filter="any", limit=50)
            self.assertIn("Gold", [str(x) for x in commodities])

            top_sell, sell_meta = provider.get_top_prices("Gold", "sell", time_range="all", freshness_filter="any", limit=5)
            self.assertGreaterEqual(len(top_sell), 2)
            self.assertEqual(str(sell_meta.get("mode") or ""), "sell")

    def test_smoke_f20_map_ui_flow_panels_filters_and_trade_highlight(self) -> None:
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
                root.geometry("1280x780")
                root.update()

                # Base load and travel render
                frame.layer_stations_var.set(True)
                frame.layer_trade_var.set(True)
                frame.layer_cashin_var.set(True)
                frame.time_range_var.set("all")
                frame.freshness_var.set("any")
                result = frame.reload_from_playerdb()
                root.update_idletasks()

                self.assertTrue(bool(result.get("ok")))
                self.assertTrue(bool(result.get("travel_enabled")))
                self.assertGreaterEqual(int(result.get("nodes") or 0), 3)
                self.assertEqual(str(result.get("edges_mode") or ""), "sequential_fallback")

                # Drilldown on known system
                target_key = next(
                    (
                        key
                        for key, node in (frame._nodes or {}).items()
                        if str(getattr(node, "system_name", "")) == "F20_QG_TARGET_A"
                    ),
                    None,
                )
                self.assertTrue(bool(target_key))
                sel = frame.select_system_node(str(target_key))
                root.update_idletasks()
                self.assertTrue(bool(sel.get("ok")))
                self.assertGreaterEqual(int(sel.get("stations_count") or 0), 1)
                self.assertIn("QG Alpha Port", str(frame.station_details_var.get() or ""))

                # Trade compare + highlight
                frame.trade_compare_commodity_var.set("Gold")
                trade_result = frame._run_trade_compare("Gold")
                root.update_idletasks()
                self.assertTrue(bool(trade_result.get("ok")))
                self.assertGreaterEqual(int(trade_result.get("rows_inserted") or 0), 2)
                self.assertGreaterEqual(len(frame._trade_highlight_node_keys), 2)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_trade_highlight")), 0)

                # Freshness filter should reduce nodes (old system falls out)
                frame.freshness_var.set("<=24h")
                result_fresh = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertTrue(bool(result_fresh.get("ok")))
                self.assertLess(int(result_fresh.get("nodes") or 0), int(result.get("nodes") or 0))

                # Travel off -> empty, but no crash
                frame.layer_travel_var.set(False)
                result_off = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertFalse(bool(result_off.get("travel_enabled")))
                self.assertIn("warstwa travel jest wylaczona", str(frame.map_status_var.get()).lower())
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

