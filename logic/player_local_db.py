from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

PLAYERDB_SCHEMA_VERSION = 1
PLAYERDB_SCHEMA_NAME_V1 = "player_local_db_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_playerdb_path() -> str:
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if appdata:
        return os.path.join(appdata, "RenataAI", "db", "player_local.db")
    return os.path.join(os.path.expanduser("~"), "RenataAI", "db", "player_local.db")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _connect(path: str) -> sqlite3.Connection:
    _ensure_parent_dir(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _read_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version;").fetchone()
    try:
        return int(row[0] if row is not None else 0)
    except Exception:
        return 0


def _write_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)};")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
        (str(table_name),),
    ).fetchone()
    return bool(row)


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )


def _record_migration(conn: sqlite3.Connection, *, version: int, name: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
        VALUES (?, ?, ?);
        """,
        (int(version), str(name), _utc_now_iso()),
    )


def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS systems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_name TEXT NOT NULL COLLATE NOCASE,
            system_address INTEGER,
            system_id64 INTEGER,
            x REAL,
            y REAL,
            z REAL,
            source TEXT NOT NULL DEFAULT 'journal',
            confidence TEXT NOT NULL DEFAULT 'observed',
            first_seen_ts TEXT,
            last_seen_ts TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE(system_name)
        );
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_systems_system_address_unique ON systems(system_address) WHERE system_address IS NOT NULL;"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_systems_last_seen_ts ON systems(last_seen_ts);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_systems_xyz ON systems(x, y, z);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_name TEXT NOT NULL COLLATE NOCASE,
            system_address INTEGER,
            station_name TEXT NOT NULL COLLATE NOCASE,
            market_id INTEGER,
            station_type TEXT NOT NULL DEFAULT 'station',
            is_fleet_carrier INTEGER NOT NULL DEFAULT 0,
            distance_ls REAL,
            distance_ls_confidence TEXT NOT NULL DEFAULT 'unknown',
            has_uc INTEGER NOT NULL DEFAULT 0,
            has_vista INTEGER NOT NULL DEFAULT 0,
            has_market INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'journal',
            confidence TEXT NOT NULL DEFAULT 'observed',
            first_seen_ts TEXT,
            last_seen_ts TEXT,
            services_freshness_ts TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE(system_name, station_name),
            FOREIGN KEY(system_address) REFERENCES systems(system_address) ON DELETE SET NULL
        );
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_stations_market_id_unique ON stations(market_id) WHERE market_id IS NOT NULL;"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_system ON stations(system_name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_system_address ON stations(system_address);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_last_seen_ts ON stations(last_seen_ts);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_stations_services ON stations(has_uc, has_vista, has_market);"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_name TEXT NOT NULL COLLATE NOCASE,
            station_name TEXT NOT NULL COLLATE NOCASE,
            station_market_id INTEGER,
            snapshot_ts TEXT NOT NULL,
            freshness_ts TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'market_json',
            confidence TEXT NOT NULL DEFAULT 'observed',
            hash_sig TEXT,
            commodities_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            FOREIGN KEY(station_market_id) REFERENCES stations(market_id) ON DELETE SET NULL
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_snapshots_station_ts ON market_snapshots(system_name, station_name, snapshot_ts DESC);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_snapshots_hash_sig ON market_snapshots(hash_sig);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_snapshots_market_id_hash ON market_snapshots(station_market_id, hash_sig, snapshot_ts DESC);"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshot_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            commodity TEXT NOT NULL COLLATE NOCASE,
            buy_price INTEGER,
            sell_price INTEGER,
            stock INTEGER,
            supply INTEGER,
            demand INTEGER,
            mean_price INTEGER,
            stock_bracket INTEGER,
            supply_bracket INTEGER,
            demand_bracket INTEGER,
            FOREIGN KEY(snapshot_id) REFERENCES market_snapshots(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_snapshot_items_snapshot ON market_snapshot_items(snapshot_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_snapshot_items_commodity ON market_snapshot_items(commodity);"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_ts TEXT NOT NULL,
            system_name TEXT,
            station_name TEXT,
            commodity TEXT,
            action TEXT NOT NULL,
            unit_price INTEGER,
            amount INTEGER,
            total_value INTEGER,
            source TEXT NOT NULL DEFAULT 'journal',
            confidence TEXT NOT NULL DEFAULT 'observed',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_event_ts ON trade_history(event_ts DESC);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_history_station ON trade_history(system_name, station_name);"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cashin_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_ts TEXT NOT NULL,
            system_name TEXT,
            station_name TEXT,
            service TEXT NOT NULL,
            total_earnings INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'journal',
            confidence TEXT NOT NULL DEFAULT 'observed',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cashin_history_event_ts ON cashin_history(event_ts DESC);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cashin_history_service ON cashin_history(service, event_ts DESC);"
    )


def ensure_playerdb_schema(*, path: str | None = None) -> dict[str, Any]:
    db_path = str(path or default_playerdb_path())
    created_new_file = not os.path.isfile(db_path)
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN;")
        try:
            _ensure_schema_migrations_table(conn)
            version = _read_user_version(conn)
            if version < 1:
                _migrate_to_v1(conn)
                _record_migration(conn, version=1, name=PLAYERDB_SCHEMA_NAME_V1)
                _write_user_version(conn, 1)
                version = 1
            # Placeholder for future migrations.
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        migrations_count = int(
            (conn.execute("SELECT COUNT(*) FROM schema_migrations;").fetchone() or [0])[0]
        )
        final_version = _read_user_version(conn)
    finally:
        conn.close()

    return {
        "path": db_path,
        "schema_version": int(final_version),
        "created_new_file": bool(created_new_file),
        "migrations_count": migrations_count,
    }


@contextmanager
def playerdb_connection(*, path: str | None = None, ensure_schema: bool = True) -> Iterator[sqlite3.Connection]:
    db_path = str(path or default_playerdb_path())
    if ensure_schema:
        ensure_playerdb_schema(path=db_path)
    conn = _connect(db_path)
    try:
        yield conn
    finally:
        conn.close()
