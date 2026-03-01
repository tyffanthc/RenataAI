from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from logic import player_local_db


class F16PlayerDbSchemaAndMigrationsTests(unittest.TestCase):
    def test_default_playerdb_path_points_to_appdata_renataai_db(self) -> None:
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\Test\AppData\Roaming"}, clear=False):
            path = player_local_db.default_playerdb_path()
        self.assertEqual(
            os.path.normcase(path),
            os.path.normcase(r"C:\Users\Test\AppData\Roaming\RenataAI\db\player_local.db"),
        )

    def test_ensure_schema_creates_tables_and_sets_user_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            result = player_local_db.ensure_playerdb_schema(path=db_path)

            self.assertTrue(os.path.isfile(db_path))
            self.assertEqual(int(result.get("schema_version") or 0), 4)
            self.assertEqual(int(result.get("migrations_count") or 0), 4)

            conn = sqlite3.connect(db_path)
            try:
                user_version = int(conn.execute("PRAGMA user_version;").fetchone()[0])
                self.assertEqual(user_version, 4)

                tables = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table';"
                    ).fetchall()
                }
                expected = {
                    "schema_migrations",
                    "systems",
                    "stations",
                    "market_snapshots",
                    "market_snapshot_items",
                    "trade_history",
                    "cashin_history",
                    "visited_nav_beacons",
                }
                self.assertTrue(expected.issubset(tables))

                systems_cols = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(systems);").fetchall()
                }
                self.assertTrue(
                    {
                        "system_name",
                        "system_address",
                        "system_id64",
                        "x",
                        "y",
                        "z",
                        "primary_star_type",
                        "is_neutron",
                        "is_black_hole",
                        "first_seen_ts",
                        "last_seen_ts",
                    }.issubset(systems_cols)
                )

                stations_cols = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(stations);").fetchall()
                }
                self.assertTrue(
                    {
                        "system_name",
                        "system_address",
                        "station_name",
                        "market_id",
                        "station_type",
                        "distance_ls",
                        "distance_ls_confidence",
                        "has_uc",
                        "has_vista",
                        "has_market",
                        "services_freshness_ts",
                    }.issubset(stations_cols)
                )

                snapshots_cols = {
                    str(row[1]) for row in conn.execute("PRAGMA table_info(market_snapshots);").fetchall()
                }
                self.assertTrue(
                    {
                        "system_name",
                        "station_name",
                        "station_market_id",
                        "snapshot_ts",
                        "freshness_ts",
                        "hash_sig",
                        "commodities_count",
                    }.issubset(snapshots_cols)
                )

                indexes = {
                    str(row[1])
                    for row in conn.execute("PRAGMA index_list(systems);").fetchall()
                }
                self.assertIn("idx_systems_system_address_unique", indexes)

                station_indexes = {
                    str(row[1])
                    for row in conn.execute("PRAGMA index_list(stations);").fetchall()
                }
                self.assertIn("idx_stations_market_id_unique", station_indexes)

                market_snapshot_indexes = {
                    str(row[1])
                    for row in conn.execute("PRAGMA index_list(market_snapshots);").fetchall()
                }
                self.assertIn("idx_market_snapshots_market_id_hash_unique", market_snapshot_indexes)
                self.assertIn("idx_market_snapshots_station_hash_unique_no_marketid", market_snapshot_indexes)
            finally:
                conn.close()

    def test_ensure_schema_is_idempotent_and_does_not_duplicate_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            first = player_local_db.ensure_playerdb_schema(path=db_path)
            second = player_local_db.ensure_playerdb_schema(path=db_path)

            self.assertEqual(int(first.get("schema_version") or 0), 4)
            self.assertEqual(int(second.get("schema_version") or 0), 4)
            self.assertEqual(int(second.get("migrations_count") or 0), 4)

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT COUNT(*) FROM schema_migrations;").fetchone()
                self.assertEqual(int(row[0]), 4)
            finally:
                conn.close()

    def test_playerdb_connection_caches_schema_ensure_per_db_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path_a = os.path.join(tmp, "a.db")
            db_path_b = os.path.join(tmp, "b.db")
            open(db_path_a, "a", encoding="utf-8").close()
            open(db_path_b, "a", encoding="utf-8").close()

            with player_local_db._PLAYERDB_SCHEMA_ENSURED_LOCK:
                saved_cache = set(player_local_db._PLAYERDB_SCHEMA_ENSURED_PATHS)
                player_local_db._PLAYERDB_SCHEMA_ENSURED_PATHS.clear()

            try:
                def _fake_ensure_schema(*, path: str | None = None):
                    with player_local_db._PLAYERDB_SCHEMA_ENSURED_LOCK:
                        player_local_db._PLAYERDB_SCHEMA_ENSURED_PATHS.add(
                            player_local_db._playerdb_schema_cache_key(str(path or ""))
                        )
                    return {"schema_version": 4, "migrations_count": 4}

                with (
                    patch(
                        "logic.player_local_db.ensure_playerdb_schema",
                        side_effect=_fake_ensure_schema,
                    ) as ensure_mock,
                    patch(
                        "logic.player_local_db._connect",
                        side_effect=lambda _path: sqlite3.connect(":memory:"),
                    ),
                ):
                    with player_local_db.playerdb_connection(path=db_path_a, ensure_schema=True):
                        pass
                    with player_local_db.playerdb_connection(path=db_path_a, ensure_schema=True):
                        pass
                    with player_local_db.playerdb_connection(path=db_path_b, ensure_schema=True):
                        pass

                self.assertEqual(ensure_mock.call_count, 2, "ensure_schema should run once per DB path per session")
                called_paths = [str(call.kwargs.get("path") or "") for call in ensure_mock.call_args_list]
                self.assertEqual(called_paths, [db_path_a, db_path_b])
            finally:
                with player_local_db._PLAYERDB_SCHEMA_ENSURED_LOCK:
                    player_local_db._PLAYERDB_SCHEMA_ENSURED_PATHS.clear()
                    player_local_db._PLAYERDB_SCHEMA_ENSURED_PATHS.update(saved_cache)


if __name__ == "__main__":
    unittest.main()
