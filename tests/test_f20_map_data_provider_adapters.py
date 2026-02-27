from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


class F20MapDataProviderAdaptersTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "db", "player_local.db")
        self.provider = MapDataProvider(db_path=self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_baseline(self) -> None:
        # Older system (should be filtered out by 7d)
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-01-01T10:00:00Z",
                "StarSystem": "F20_OLD_SYSTEM",
                "SystemAddress": 9001,
                "SystemId64": 9001,
                "StarPos": [100.0, 0.0, 0.0],
            },
            path=self.db_path,
        )

        # Origin + two nearby target systems / stations
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": "2026-02-22T20:00:00Z",
                "StarSystem": "F20_ORIGIN",
                "SystemAddress": 9100,
                "SystemId64": 9100,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T20:05:00Z",
                "StarSystem": "F20_TGT_A",
                "SystemAddress": 9101,
                "SystemId64": 9101,
                "StarPos": [10.0, 0.0, 0.0],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": "2026-02-22T20:06:00Z",
                "StarSystem": "F20_TGT_A",
                "SystemAddress": 9101,
                "StationName": "Alpha Port",
                "StationType": "Orbis Starport",
                "MarketID": 99101,
                "DistFromStarLS": 500,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=self.db_path,
        )
        player_local_db.ingest_market_json(
            {
                "StationName": "Alpha Port",
                "StarSystem": "F20_TGT_A",
                "MarketID": 99101,
                "timestamp": "2026-02-22T20:07:00Z",
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 8000, "SellPrice": 12000, "Stock": 100},
                    {"Name_Localised": "Silver", "BuyPrice": 4200, "SellPrice": 7200, "Stock": 200},
                ],
            },
            path=self.db_path,
        )

        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T20:10:00Z",
                "StarSystem": "F20_TGT_B",
                "SystemAddress": 9102,
                "SystemId64": 9102,
                "StarPos": [25.0, 0.0, 0.0],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": "2026-02-22T20:11:00Z",
                "StarSystem": "F20_TGT_B",
                "SystemAddress": 9102,
                "StationName": "Beta Exchange",
                "StationType": "Coriolis Starport",
                "MarketID": 99102,
                "DistFromStarLS": 1500,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=self.db_path,
        )
        player_local_db.ingest_market_json(
            {
                "StationName": "Beta Exchange",
                "StarSystem": "F20_TGT_B",
                "MarketID": 99102,
                "timestamp": "2026-02-22T20:12:00Z",
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000, "Stock": 300},
                    {"Name_Localised": "Palladium", "BuyPrice": 40000, "SellPrice": 55000, "Stock": 20},
                ],
            },
            path=self.db_path,
        )

    def test_get_system_nodes_returns_contract_and_time_filter(self) -> None:
        self._seed_baseline()

        rows, meta = self.provider.get_system_nodes(time_range="7d", source_filter="observed_only")

        names = {str(r.get("system_name")) for r in rows}
        self.assertIn("F20_ORIGIN", names)
        self.assertIn("F20_TGT_A", names)
        self.assertIn("F20_TGT_B", names)
        self.assertNotIn("F20_OLD_SYSTEM", names)
        self.assertEqual(str(meta.get("time_range")), "7d")
        self.assertEqual(str(meta.get("source_filter")), "observed_only")
        self.assertGreaterEqual(int(meta.get("count") or 0), 3)
        sample = dict(rows[0])
        self.assertIn("source", sample)
        self.assertIn("confidence", sample)
        self.assertIn("freshness_ts", sample)

    def test_get_system_nodes_supports_1d_and_1y_ranges_with_forever_alias(self) -> None:
        now = datetime.now(timezone.utc)
        ts_old = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        ts_recent = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_old,
                "StarSystem": "F20_RANGE_OLD_2D",
                "SystemAddress": 9201,
                "SystemId64": 9201,
                "StarPos": [1.0, 0.0, 0.0],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_recent,
                "StarSystem": "F20_RANGE_RECENT_2H",
                "SystemAddress": 9202,
                "SystemId64": 9202,
                "StarPos": [2.0, 0.0, 0.0],
            },
            path=self.db_path,
        )

        rows_1d, meta_1d = self.provider.get_system_nodes(time_range="1d", source_filter="observed_only")
        names_1d = {str(r.get("system_name")) for r in rows_1d}
        self.assertNotIn("F20_RANGE_OLD_2D", names_1d)
        self.assertIn("F20_RANGE_RECENT_2H", names_1d)
        self.assertEqual(str(meta_1d.get("time_range")), "1d")

        rows_1y, meta_1y = self.provider.get_system_nodes(time_range="365d", source_filter="observed_only")
        names_1y = {str(r.get("system_name")) for r in rows_1y}
        self.assertIn("F20_RANGE_OLD_2D", names_1y)
        self.assertIn("F20_RANGE_RECENT_2H", names_1y)
        self.assertEqual(str(meta_1y.get("time_range")), "365d")

        rows_forever, meta_forever = self.provider.get_system_nodes(time_range="forever", source_filter="observed_only")
        names_forever = {str(r.get("system_name")) for r in rows_forever}
        self.assertIn("F20_RANGE_OLD_2D", names_forever)
        self.assertIn("F20_RANGE_RECENT_2H", names_forever)
        self.assertEqual(str(meta_forever.get("time_range")), "forever")

    def test_get_edges_returns_contract_meta_even_without_jump_ingest(self) -> None:
        rows, meta = self.provider.get_edges(time_range="all")
        self.assertEqual(rows, [])
        self.assertFalse(bool(meta.get("available")))
        self.assertEqual(str(meta.get("reason") or ""), "playerdb_jumps_not_ingested")

    def test_get_stations_market_last_seen_and_top_prices_contract(self) -> None:
        self._seed_baseline()

        stations, stations_meta = self.provider.get_stations_for_system(system_name="F20_TGT_A")
        self.assertEqual(str(stations_meta.get("system_name") or ""), "F20_TGT_A")
        self.assertEqual(len(stations), 1)
        station = dict(stations[0])
        self.assertEqual(station.get("station_name"), "Alpha Port")
        self.assertTrue(bool((station.get("services") or {}).get("has_uc")))
        self.assertIn("freshness_ts", station)

        snapshots, snap_meta = self.provider.get_market_last_seen(99101, limit=3)
        self.assertEqual(int(snap_meta.get("market_id") or 0), 99101)
        self.assertGreaterEqual(len(snapshots), 1)
        snap = dict(snapshots[0])
        self.assertEqual(snap.get("market_id"), 99101)
        self.assertIn("items", snap)
        self.assertTrue(any(str(x.get("commodity")) == "Gold" for x in (snap.get("items") or [])))
        self.assertIn("freshness_ts", snap)
        self.assertIn("confidence", snap)

        top_sell, meta_sell = self.provider.get_top_prices("Gold", "sell", time_range="all", freshness_filter="any", limit=5)
        self.assertEqual(str(meta_sell.get("mode") or ""), "sell")
        self.assertGreaterEqual(len(top_sell), 2)
        self.assertEqual(str(top_sell[0].get("station_name") or ""), "Alpha Port")  # 12000 > 11000
        self.assertIn("freshness_ts", top_sell[0])
        self.assertIn("confidence", top_sell[0])

        top_buy, meta_buy = self.provider.get_top_prices("Gold", "buy", time_range="all", freshness_filter="any", limit=5)
        self.assertEqual(str(meta_buy.get("mode") or ""), "buy")
        self.assertGreaterEqual(len(top_buy), 2)
        self.assertEqual(str(top_buy[0].get("station_name") or ""), "Beta Exchange")  # 7000 < 8000


if __name__ == "__main__":
    unittest.main()
