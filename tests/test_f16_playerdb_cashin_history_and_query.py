from __future__ import annotations

import os
import tempfile
import unittest

from logic import player_local_db


class F16PlayerDbCashInHistoryAndQueryTests(unittest.TestCase):
    def test_cashin_history_ingest_records_uc_and_vista_with_fallback_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")

            out_uc = player_local_db.ingest_journal_event(
                {
                    "event": "SellExplorationData",
                    "timestamp": "2026-02-22T21:00:00Z",
                    "TotalEarnings": 12500000,
                },
                path=db_path,
                fallback_system_name="Diagaundri",
                fallback_station_name="Ray Gateway",
            )
            out_vista = player_local_db.ingest_journal_event(
                {
                    "event": "SellOrganicData",
                    "timestamp": "2026-02-22T21:05:00Z",
                    "TotalEarnings": 132555000,
                    "StationName": "Fan Survey",
                    "StarSystem": "IC 289 Sector TJ-Q b5-0",
                },
                path=db_path,
                fallback_system_name="IGNORED_SYSTEM",
                fallback_station_name="IGNORED_STATION",
            )

            self.assertTrue(bool(out_uc.get("ok")))
            self.assertTrue(bool(out_uc.get("ingested_cashin")))
            self.assertTrue(bool(out_vista.get("ok")))
            self.assertTrue(bool(out_vista.get("ingested_cashin")))

            all_rows = player_local_db.query_cashin_history(path=db_path, limit=10)
            self.assertEqual(len(all_rows), 2)
            self.assertEqual(all_rows[0]["service"], "VISTA")
            self.assertEqual(all_rows[0]["system_name"], "IC 289 Sector TJ-Q b5-0")
            self.assertEqual(all_rows[0]["station_name"], "Fan Survey")
            self.assertEqual(int(all_rows[0]["total_earnings"]), 132555000)
            self.assertEqual(all_rows[1]["service"], "UC")
            self.assertEqual(all_rows[1]["system_name"], "Diagaundri")
            self.assertEqual(all_rows[1]["station_name"], "Ray Gateway")

            vista_rows = player_local_db.query_cashin_history(path=db_path, service="vista", limit=10)
            self.assertEqual(len(vista_rows), 1)
            self.assertEqual(vista_rows[0]["service"], "VISTA")

    def test_query_nearest_station_candidates_uses_playerdb_coords_and_service_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")

            # Origin system
            player_local_db.ingest_journal_event(
                {
                    "event": "Location",
                    "timestamp": "2026-02-22T22:00:00Z",
                    "StarSystem": "Origin",
                    "SystemAddress": 111,
                    "StarPos": [0.0, 0.0, 0.0],
                },
                path=db_path,
            )

            # Target A (closer, UC)
            player_local_db.ingest_journal_event(
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-22T22:01:00Z",
                    "StarSystem": "Target-A",
                    "SystemAddress": 222,
                    "StarPos": [10.0, 0.0, 0.0],
                },
                path=db_path,
            )
            player_local_db.ingest_journal_event(
                {
                    "event": "Docked",
                    "timestamp": "2026-02-22T22:02:00Z",
                    "StarSystem": "Target-A",
                    "SystemAddress": 222,
                    "StationName": "A Hub",
                    "MarketID": 2222,
                    "DistFromStarLS": 350,
                    "StationServices": ["Universal Cartographics"],
                },
                path=db_path,
            )

            # Target B (farther, UC + Vista)
            player_local_db.ingest_journal_event(
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-22T22:03:00Z",
                    "StarSystem": "Target-B",
                    "SystemAddress": 333,
                    "StarPos": [30.0, 0.0, 0.0],
                },
                path=db_path,
            )
            player_local_db.ingest_journal_event(
                {
                    "event": "Docked",
                    "timestamp": "2026-02-22T22:04:00Z",
                    "StarSystem": "Target-B",
                    "SystemAddress": 333,
                    "StationName": "B Vista",
                    "MarketID": 3333,
                    "StationServices": ["Universal Cartographics", "Vista Genomics", "Commodities"],
                },
                path=db_path,
            )

            candidates_uc, meta_uc = player_local_db.query_nearest_station_candidates(
                path=db_path,
                origin_system_name="Origin",
                service="uc",
                limit=5,
            )
            self.assertEqual(meta_uc["query_mode"], "nearest")
            self.assertTrue(bool(meta_uc["origin_coords_used"]))
            self.assertEqual([c["name"] for c in candidates_uc[:2]], ["A Hub", "B Vista"])
            self.assertAlmostEqual(float(candidates_uc[0]["distance_ly"]), 10.0)
            self.assertAlmostEqual(float(candidates_uc[1]["distance_ly"]), 30.0)
            self.assertEqual(candidates_uc[0]["source"], "PLAYERDB")
            self.assertTrue(bool(candidates_uc[0]["services"]["has_uc"]))

            candidates_vista, meta_vista = player_local_db.query_nearest_station_candidates(
                path=db_path,
                origin_system_name="Origin",
                service="vista",
                limit=5,
            )
            self.assertEqual(meta_vista["count"], 1)
            self.assertEqual(candidates_vista[0]["name"], "B Vista")
            self.assertTrue(bool(candidates_vista[0]["services"]["has_vista"]))

    def test_cashin_event_without_earnings_value_is_rejected_and_not_saved_as_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            out = player_local_db.ingest_journal_event(
                {
                    "event": "SellExplorationData",
                    "timestamp": "2026-02-22T23:00:00Z",
                    # Intentionally missing TotalEarnings/Earnings/Value/Total
                    "StationName": "Ray Gateway",
                    "StarSystem": "Diagaundri",
                },
                path=db_path,
            )

            self.assertFalse(bool(out.get("ok")))
            self.assertEqual(str(out.get("reason") or ""), "missing_earnings_value")
            self.assertEqual(str(out.get("service") or ""), "UC")

            if not os.path.exists(db_path):
                return

            history = player_local_db.query_cashin_history(path=db_path, limit=10)
            self.assertEqual(history, [])


if __name__ == "__main__":
    unittest.main()
