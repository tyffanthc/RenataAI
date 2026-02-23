from __future__ import annotations

import tempfile
import unittest

from logic import player_local_db


class F29PlayerDbFixtureCleanupToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = self._tmp.name + "\\player_local.db"
        player_local_db.ensure_playerdb_schema(path=self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_fixture_and_real_data(self) -> None:
        # Fixture system/station + market snapshot + cashin
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-23T10:00:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "SystemAddress": 19001,
                "SystemId64": 19001,
                "StarPos": [10.0, 20.0, 30.0],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": "2026-02-23T10:05:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "SystemAddress": 19001,
                "StationName": "F19 Smoke Station",
                "MarketID": 1900101,
                "StationType": "Orbis Starport",
                "StationServices": ["Commodity Market", "Universal Cartographics"],
                "DistFromStarLS": 500,
            },
            path=self.db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": "2026-02-23T10:06:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "StationName": "F19 Smoke Station",
                "MarketID": 1900101,
                "Items": [
                    {"Name": "gold", "BuyPrice": 10000, "SellPrice": 9500, "Demand": 100, "Supply": 0},
                    {"Name": "silver", "BuyPrice": 5000, "SellPrice": 4800, "Demand": 50, "Supply": 0},
                ],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "SellExplorationData",
                "timestamp": "2026-02-23T10:07:00Z",
                "StarSystem": "F19_SMOKE_TARGET",
                "SystemAddress": 19001,
                "StationName": "F19 Smoke Station",
                "MarketID": 1900101,
                "TotalEarnings": 123456,
            },
            path=self.db_path,
        )

        # Real system/station should survive cleanup
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-23T11:00:00Z",
                "StarSystem": "NSV 1056",
                "SystemAddress": 424242,
                "SystemId64": 424242,
                "StarPos": [40.0, 50.0, 60.0],
            },
            path=self.db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": "2026-02-23T11:05:00Z",
                "StarSystem": "NSV 1056",
                "SystemAddress": 424242,
                "StationName": "Real Station",
                "MarketID": 42424201,
                "StationType": "Outpost",
                "StationServices": ["Commodity Market"],
            },
            path=self.db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": "2026-02-23T11:06:00Z",
                "StarSystem": "NSV 1056",
                "StationName": "Real Station",
                "MarketID": 42424201,
                "Items": [{"Name": "gold", "BuyPrice": 11111, "SellPrice": 11000}],
            },
            path=self.db_path,
        )

        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            conn.execute(
                """
                INSERT INTO trade_history(event_ts, system_name, station_name, commodity, action, unit_price, amount, total_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "2026-02-23T10:08:00Z",
                    "F19_SMOKE_TARGET",
                    "F19 Smoke Station",
                    "gold",
                    "BUY",
                    10000,
                    1,
                    10000,
                ),
            )
            conn.execute(
                """
                INSERT INTO trade_history(event_ts, system_name, station_name, commodity, action, unit_price, amount, total_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "2026-02-23T11:08:00Z",
                    "NSV 1056",
                    "Real Station",
                    "gold",
                    "SELL",
                    11000,
                    1,
                    11000,
                ),
            )
            conn.commit()

    def test_cleanup_fixture_test_data_dry_run_and_apply(self) -> None:
        self._seed_fixture_and_real_data()

        dry = player_local_db.cleanup_fixture_test_data(path=self.db_path, dry_run=True)
        self.assertTrue(bool(dry.get("ok")))
        self.assertTrue(bool(dry.get("dry_run")))
        counts = dict(dry.get("counts") or {})
        self.assertGreaterEqual(int(counts.get("systems") or 0), 1)
        self.assertGreaterEqual(int(counts.get("stations") or 0), 1)
        self.assertGreaterEqual(int(counts.get("market_snapshots") or 0), 1)
        self.assertGreaterEqual(int(counts.get("market_snapshot_items") or 0), 1)
        self.assertGreaterEqual(int(counts.get("cashin_history") or 0), 1)
        self.assertGreaterEqual(int(counts.get("trade_history") or 0), 1)
        self.assertIn("F19_SMOKE_TARGET", list((dry.get("preview") or {}).get("systems") or []))

        applied = player_local_db.cleanup_fixture_test_data(path=self.db_path, dry_run=False)
        self.assertTrue(bool(applied.get("ok")))
        self.assertFalse(bool(applied.get("dry_run")))

        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            fixture_systems = conn.execute(
                "SELECT COUNT(*) FROM systems WHERE system_name LIKE 'F19_%' COLLATE NOCASE;"
            ).fetchone()[0]
            fixture_stations = conn.execute(
                "SELECT COUNT(*) FROM stations WHERE station_name LIKE 'F19 %' COLLATE NOCASE OR system_name LIKE 'F19_%' COLLATE NOCASE;"
            ).fetchone()[0]
            fixture_cashin = conn.execute(
                "SELECT COUNT(*) FROM cashin_history WHERE system_name LIKE 'F19_%' COLLATE NOCASE;"
            ).fetchone()[0]
            fixture_snapshots = conn.execute(
                "SELECT COUNT(*) FROM market_snapshots WHERE system_name LIKE 'F19_%' COLLATE NOCASE;"
            ).fetchone()[0]
            real_systems = conn.execute(
                "SELECT COUNT(*) FROM systems WHERE system_name = 'NSV 1056';"
            ).fetchone()[0]
            real_stations = conn.execute(
                "SELECT COUNT(*) FROM stations WHERE station_name = 'Real Station';"
            ).fetchone()[0]
            real_snapshots = conn.execute(
                "SELECT COUNT(*) FROM market_snapshots WHERE system_name = 'NSV 1056' AND station_name = 'Real Station';"
            ).fetchone()[0]
            real_trade = conn.execute(
                "SELECT COUNT(*) FROM trade_history WHERE system_name = 'NSV 1056';"
            ).fetchone()[0]

        self.assertEqual(int(fixture_systems), 0)
        self.assertEqual(int(fixture_stations), 0)
        self.assertEqual(int(fixture_cashin), 0)
        self.assertEqual(int(fixture_snapshots), 0)
        self.assertEqual(int(real_systems), 1)
        self.assertEqual(int(real_stations), 1)
        self.assertEqual(int(real_snapshots), 1)
        self.assertEqual(int(real_trade), 1)


if __name__ == "__main__":
    unittest.main()
