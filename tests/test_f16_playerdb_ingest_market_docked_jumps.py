from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from logic import player_local_db


class F16PlayerDbIngestMarketDockedJumpsTests(unittest.TestCase):
    def test_ingest_location_and_docked_persists_system_coords_and_station_marketid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            location_ev = {
                "event": "Location",
                "timestamp": "2026-02-22T18:00:00Z",
                "StarSystem": "Diagaundri",
                "SystemAddress": 123456789,
                "StarPos": [10.5, -20.25, 30.75],
                "Docked": True,
                "StationName": "Ray Gateway",
                "StationType": "Orbis Starport",
                "MarketID": 424242,
                "DistFromStarLS": 415.0,
                "StationServices": ["Commodities", "UniversalCartographics", "VistaGenomics"],
            }
            docked_ev = {
                "event": "Docked",
                "timestamp": "2026-02-22T18:05:00Z",
                "StarSystem": "Diagaundri",
                "SystemAddress": 123456789,
                "StationName": "Ray Gateway",
                "StationType": "Orbis Starport",
                "MarketID": 424242,
                "DistFromStarLS": 415.0,
            }

            out1 = player_local_db.ingest_journal_event(location_ev, path=db_path)
            out2 = player_local_db.ingest_journal_event(docked_ev, path=db_path)

            self.assertTrue(bool(out1.get("ok")))
            self.assertTrue(bool(out1.get("ingested_system")))
            self.assertTrue(bool(out1.get("ingested_station")))
            self.assertTrue(bool(out2.get("ok")))

            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                sys_row = conn.execute(
                    "SELECT system_name, system_address, system_id64, x, y, z FROM systems WHERE system_name=?;",
                    ("Diagaundri",),
                ).fetchone()
                self.assertIsNotNone(sys_row)
                self.assertEqual(int(sys_row["system_address"]), 123456789)
                self.assertEqual(int(sys_row["system_id64"]), 123456789)
                self.assertAlmostEqual(float(sys_row["x"]), 10.5)
                self.assertAlmostEqual(float(sys_row["y"]), -20.25)
                self.assertAlmostEqual(float(sys_row["z"]), 30.75)

                st_row = conn.execute(
                    """
                    SELECT system_name, system_address, station_name, market_id, distance_ls,
                           distance_ls_confidence, has_uc, has_vista, has_market, services_freshness_ts
                    FROM stations WHERE market_id=?;
                    """,
                    (424242,),
                ).fetchone()
                self.assertIsNotNone(st_row)
                self.assertEqual(st_row["station_name"], "Ray Gateway")
                self.assertEqual(int(st_row["system_address"]), 123456789)
                self.assertEqual(int(st_row["market_id"]), 424242)
                self.assertAlmostEqual(float(st_row["distance_ls"]), 415.0)
                self.assertEqual(str(st_row["distance_ls_confidence"]), "observed")
                self.assertEqual(int(st_row["has_uc"]), 1)
                self.assertEqual(int(st_row["has_vista"]), 1)
                self.assertEqual(int(st_row["has_market"]), 1)
                self.assertTrue(str(st_row["services_freshness_ts"]).startswith("2026-02-22T18:00:00"))
            finally:
                conn.close()

    def test_ingest_market_json_persists_snapshot_items_and_dedupes_by_marketid_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            player_local_db.ingest_journal_event(
                {
                    "event": "Docked",
                    "timestamp": "2026-02-22T19:00:00Z",
                    "StarSystem": "Diaguandri",
                    "StationName": "Ray Gateway",
                    "MarketID": 515151,
                    "StationType": "Orbis Starport",
                },
                path=db_path,
            )

            market_payload = {
                "StationName": "Ray Gateway",
                "MarketID": 515151,
                "Items": [
                    {
                        "Name_Localised": "Gold",
                        "BuyPrice": 7000,
                        "SellPrice": 11000,
                        "Stock": 120,
                        "Demand": 0,
                    },
                    {
                        "Name_Localised": "Silver",
                        "BuyPrice": 4000,
                        "SellPrice": 8000,
                        "Stock": 90,
                        "Demand": 0,
                    },
                ],
            }

            first = player_local_db.ingest_market_json(
                market_payload,
                path=db_path,
                fallback_system_name="Diagaundri",
            )
            second = player_local_db.ingest_market_json(
                market_payload,
                path=db_path,
                fallback_system_name="Diagaundri",
            )

            self.assertTrue(bool(first.get("ok")))
            self.assertFalse(bool(first.get("deduped")))
            self.assertTrue(bool(second.get("ok")))
            self.assertTrue(bool(second.get("deduped")))
            self.assertEqual(first.get("hash_sig"), second.get("hash_sig"))

            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                snap_count = int(conn.execute("SELECT COUNT(*) FROM market_snapshots;").fetchone()[0])
                self.assertEqual(snap_count, 1)

                snap = conn.execute(
                    "SELECT station_market_id, hash_sig, commodities_count FROM market_snapshots LIMIT 1;"
                ).fetchone()
                self.assertEqual(int(snap["station_market_id"]), 515151)
                self.assertEqual(int(snap["commodities_count"]), 2)
                self.assertTrue(bool(str(snap["hash_sig"])))

                item_count = int(conn.execute("SELECT COUNT(*) FROM market_snapshot_items;").fetchone()[0])
                self.assertEqual(item_count, 2)

                station = conn.execute(
                    "SELECT has_market, market_id FROM stations WHERE market_id=?;",
                    (515151,),
                ).fetchone()
                self.assertEqual(int(station["has_market"]), 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

