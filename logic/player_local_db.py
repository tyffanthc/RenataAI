from __future__ import annotations

import os
import sqlite3
import json
import hashlib
import math
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

PLAYERDB_SCHEMA_VERSION = 1
PLAYERDB_SCHEMA_NAME_V1 = "player_local_db_v1"
DEFAULT_FIXTURE_PREFIXES: tuple[str, ...] = (
    "F19_",
    "F20_",
    "F21_",
    "F22_",
    "F23_",
    "F24_",
    "F25_",
    "F26_",
    "F27_",
    "F28_",
    "F29_",
    "SMOKE_",
    "QG_",
    "TEST_",
)


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


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))
    except Exception:
        return None


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            return float(int(value))
        text = str(value).strip().replace(",", ".")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _safe_ts(value: Any) -> str:
    text = _as_text(value)
    return text or _utc_now_iso()


def _parse_iso_ts(value: Any) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _norm_service_token(value: Any) -> str:
    raw = _as_text(value).casefold()
    return "".join(ch for ch in raw if ch.isalnum())


def _services_flags_from_list(values: Any) -> dict[str, int]:
    has_uc = 0
    has_vista = 0
    has_market = 0
    if isinstance(values, list):
        for item in values:
            token = _norm_service_token(item)
            if not token:
                continue
            if "universalcartographics" in token or token == "cartographics":
                has_uc = 1
            if "vistagenomics" in token or token == "genomics":
                has_vista = 1
            if "commoditymarket" in token or token == "commodities" or token == "market":
                has_market = 1
    return {"has_uc": has_uc, "has_vista": has_vista, "has_market": has_market}


def _journal_system_name(ev: dict[str, Any]) -> str:
    return _as_text(ev.get("StarSystem") or ev.get("SystemName") or ev.get("StarSystemName"))


def _journal_system_address(ev: dict[str, Any]) -> int | None:
    return _as_optional_int(
        ev.get("SystemAddress")
        or ev.get("SystemAddress64")
        or ev.get("SystemId64")
        or ev.get("StarSystemAddress")
    )


def _journal_system_id64(ev: dict[str, Any], *, fallback_address: int | None = None) -> int | None:
    return _as_optional_int(
        ev.get("SystemId64")
        or ev.get("SystemAddress64")
        or ev.get("SystemAddress")
        or fallback_address
    )


def _journal_station_name(ev: dict[str, Any]) -> str:
    return _as_text(ev.get("StationName") or ev.get("Station") or ev.get("StationName_Localised"))


def _event_starpos_xyz(ev: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    star_pos = ev.get("StarPos")
    if not isinstance(star_pos, (list, tuple)) or len(star_pos) < 3:
        return (None, None, None)
    return (
        _as_optional_float(star_pos[0]),
        _as_optional_float(star_pos[1]),
        _as_optional_float(star_pos[2]),
    )


def _event_station_type(ev: dict[str, Any]) -> str:
    return _as_text(ev.get("StationType") or ev.get("StationTypeLocalised") or "station") or "station"


def _infer_is_fleet_carrier(station_name: str, station_type: str) -> int:
    st = station_type.casefold()
    nm = station_name.casefold()
    return int(("carrier" in st) or ("fleet carrier" in nm))


def _market_items_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("Items") or data.get("items") or []
    if not isinstance(items, list):
        return []
    return [row for row in items if isinstance(row, dict)]


def _distance_between_coords(
    origin: tuple[float, float, float] | None,
    target: tuple[float, float, float] | None,
) -> float | None:
    if origin is None or target is None:
        return None
    try:
        dx = float(origin[0]) - float(target[0])
        dy = float(origin[1]) - float(target[1])
        dz = float(origin[2]) - float(target[2])
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    except Exception:
        return None


def _cashin_service_for_event(event_name: str) -> str | None:
    if event_name == "SellExplorationData":
        return "UC"
    if event_name == "SellOrganicData":
        return "VISTA"
    return None


def _freshness_confidence_from_station(
    *,
    services_freshness_ts: Any,
    last_seen_ts: Any,
) -> str:
    dt = _parse_iso_ts(services_freshness_ts) or _parse_iso_ts(last_seen_ts)
    if dt is None:
        return "low"
    age_hours = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    if age_hours <= 24.0:
        return "high"
    if age_hours <= 24.0 * 14.0:
        return "mid"
    return "low"


def _commodity_name(item: dict[str, Any]) -> str:
    return _as_text(item.get("Name_Localised") or item.get("Name") or item.get("name"))


def _normalized_market_items_hash(items: list[dict[str, Any]]) -> tuple[str, int]:
    normalized: list[dict[str, Any]] = []
    for row in items:
        commodity = _commodity_name(row)
        if not commodity:
            continue
        normalized.append(
            {
                "commodity": commodity.casefold(),
                "buy_price": _as_optional_int(row.get("BuyPrice") or row.get("buyPrice")),
                "sell_price": _as_optional_int(row.get("SellPrice") or row.get("sellPrice")),
                "stock": _as_optional_int(row.get("Stock") or row.get("stock")),
                "supply": _as_optional_int(row.get("Supply") or row.get("supply")),
                "demand": _as_optional_int(row.get("Demand") or row.get("demand")),
                "mean_price": _as_optional_int(row.get("MeanPrice") or row.get("meanPrice")),
                "stock_bracket": _as_optional_int(row.get("StockBracket") or row.get("stockBracket")),
                "supply_bracket": _as_optional_int(row.get("SupplyBracket") or row.get("supplyBracket")),
                "demand_bracket": _as_optional_int(row.get("DemandBracket") or row.get("demandBracket")),
            }
        )
    normalized.sort(key=lambda x: x["commodity"])
    payload = json.dumps(normalized, separators=(",", ":"), ensure_ascii=True)
    sig = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return sig, len(normalized)


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
            UNIQUE(system_name, station_name)
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
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
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


def _upsert_system_observed(
    conn: sqlite3.Connection,
    *,
    system_name: str,
    system_address: int | None,
    system_id64: int | None,
    x: float | None,
    y: float | None,
    z: float | None,
    seen_ts: str,
    source: str = "journal",
    confidence: str = "observed",
) -> None:
    if not system_name:
        return

    now_ts = _utc_now_iso()
    if system_address is not None:
        row = conn.execute(
            "SELECT id, system_name, first_seen_ts FROM systems WHERE system_address = ? LIMIT 1;",
            (system_address,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, system_name, first_seen_ts FROM systems WHERE system_name = ? COLLATE NOCASE LIMIT 1;",
            (system_name,),
        ).fetchone()

    if row is None:
        conn.execute(
            """
            INSERT INTO systems(
                system_name, system_address, system_id64, x, y, z,
                source, confidence, first_seen_ts, last_seen_ts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                system_name,
                system_address,
                system_id64,
                x,
                y,
                z,
                source,
                confidence,
                seen_ts,
                seen_ts,
                now_ts,
                now_ts,
            ),
        )
        return

    existing_name = _as_text(row["system_name"])
    first_seen_ts = _as_text(row["first_seen_ts"]) or seen_ts
    conn.execute(
        """
        UPDATE systems
        SET system_name = ?,
            system_address = COALESCE(?, system_address),
            system_id64 = COALESCE(?, system_id64),
            x = COALESCE(?, x),
            y = COALESCE(?, y),
            z = COALESCE(?, z),
            source = ?,
            confidence = ?,
            first_seen_ts = COALESCE(first_seen_ts, ?),
            last_seen_ts = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            system_name or existing_name,
            system_address,
            system_id64,
            x,
            y,
            z,
            source,
            confidence,
            first_seen_ts,
            seen_ts,
            now_ts,
            int(row["id"]),
        ),
    )


def _upsert_station_observed(
    conn: sqlite3.Connection,
    *,
    system_name: str,
    system_address: int | None,
    station_name: str,
    market_id: int | None,
    station_type: str | None,
    distance_ls: float | None,
    distance_ls_confidence: str,
    has_uc: int | None,
    has_vista: int | None,
    has_market: int | None,
    seen_ts: str,
    services_freshness_ts: str | None,
    source: str,
    confidence: str,
) -> None:
    if not system_name or not station_name:
        return
    now_ts = _utc_now_iso()
    if market_id is not None:
        row = conn.execute(
            "SELECT id, first_seen_ts FROM stations WHERE market_id = ? LIMIT 1;",
            (market_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, first_seen_ts FROM stations
            WHERE system_name = ? COLLATE NOCASE AND station_name = ? COLLATE NOCASE
            LIMIT 1;
            """,
            (system_name, station_name),
        ).fetchone()

    is_fc = _infer_is_fleet_carrier(station_name, _as_text(station_type or "station"))

    if row is None:
        conn.execute(
            """
            INSERT INTO stations(
                system_name, system_address, station_name, market_id, station_type, is_fleet_carrier,
                distance_ls, distance_ls_confidence,
                has_uc, has_vista, has_market,
                source, confidence, first_seen_ts, last_seen_ts, services_freshness_ts,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                system_name,
                system_address,
                station_name,
                market_id,
                _as_text(station_type or "station") or "station",
                is_fc,
                distance_ls,
                _as_text(distance_ls_confidence or "unknown") or "unknown",
                int(bool(has_uc)),
                int(bool(has_vista)),
                int(bool(has_market)),
                source,
                confidence,
                seen_ts,
                seen_ts,
                services_freshness_ts,
                now_ts,
                now_ts,
            ),
        )
        return

    conn.execute(
        """
        UPDATE stations
        SET system_name = ?,
            system_address = COALESCE(?, system_address),
            station_name = ?,
            market_id = COALESCE(?, market_id),
            station_type = COALESCE(NULLIF(?, ''), station_type),
            is_fleet_carrier = ?,
            distance_ls = COALESCE(?, distance_ls),
            distance_ls_confidence = CASE
                WHEN ? IS NOT NULL THEN ?
                ELSE distance_ls_confidence
            END,
            has_uc = CASE WHEN ? IS NOT NULL THEN ? ELSE has_uc END,
            has_vista = CASE WHEN ? IS NOT NULL THEN ? ELSE has_vista END,
            has_market = CASE WHEN ? IS NOT NULL THEN ? ELSE has_market END,
            source = ?,
            confidence = ?,
            first_seen_ts = COALESCE(first_seen_ts, ?),
            last_seen_ts = ?,
            services_freshness_ts = COALESCE(?, services_freshness_ts),
            updated_at = ?
        WHERE id = ?;
        """,
        (
            system_name,
            system_address,
            station_name,
            market_id,
            _as_text(station_type or ""),
            is_fc,
            distance_ls,
            distance_ls,
            _as_text(distance_ls_confidence or "unknown") or "unknown",
            has_uc,
            int(bool(has_uc)) if has_uc is not None else 0,
            has_vista,
            int(bool(has_vista)) if has_vista is not None else 0,
            has_market,
            int(bool(has_market)) if has_market is not None else 0,
            source,
            confidence,
            seen_ts,
            seen_ts,
            services_freshness_ts,
            now_ts,
            int(row["id"]),
        ),
    )


def ingest_journal_event(
    ev: dict[str, Any] | None,
    *,
    path: str | None = None,
    fallback_system_name: str | None = None,
    fallback_station_name: str | None = None,
) -> dict[str, Any]:
    if not isinstance(ev, dict):
        return {"ok": False, "reason": "invalid_event"}
    event_name = _as_text(ev.get("event"))
    if event_name not in {"Location", "FSDJump", "CarrierJump", "Docked", "SellExplorationData", "SellOrganicData"}:
        return {"ok": False, "reason": "unsupported_event", "event": event_name}

    ts = _safe_ts(ev.get("timestamp"))
    system_name = _journal_system_name(ev) or _as_text(fallback_system_name)
    system_address = _journal_system_address(ev)
    system_id64 = _journal_system_id64(ev, fallback_address=system_address)
    station_name_fallback = _journal_station_name(ev) or _as_text(fallback_station_name)

    # Guard against creating "ghost" station rows under a synthetic UNKNOWN_SYSTEM
    # when we start reading journal mid-session and Docked lacks StarSystem.
    if event_name in {"Location", "Docked"} and bool(ev.get("Docked") or event_name == "Docked"):
        station_name_guard = _as_text(ev.get("StationName"))
        if station_name_guard and not system_name:
            return {
                "ok": False,
                "reason": "missing_system_name",
                "event": event_name,
                "station_name": station_name_guard,
                "system_name": system_name,
            }

    db_path = str(path or default_playerdb_path())
    with playerdb_connection(path=db_path, ensure_schema=True) as conn:
        conn.execute("BEGIN;")
        try:
            touched_system = False
            touched_station = False
            touched_cashin = False
            if event_name in {"Location", "FSDJump", "CarrierJump"} and system_name:
                x, y, z = _event_starpos_xyz(ev)
                _upsert_system_observed(
                    conn,
                    system_name=system_name,
                    system_address=system_address,
                    system_id64=system_id64,
                    x=x,
                    y=y,
                    z=z,
                    seen_ts=ts,
                    source="journal",
                    confidence="observed",
                )
                touched_system = True

            # Location może zawierać dane stacji gdy startujemy już zadokowani.
            if event_name in {"Location", "Docked"} and bool(ev.get("Docked") or event_name == "Docked"):
                station_name = _as_text(ev.get("StationName"))
                if station_name:
                    has_services_list = isinstance(ev.get("StationServices"), list)
                    services = _services_flags_from_list(ev.get("StationServices")) if has_services_list else {}
                    market_id = _as_optional_int(ev.get("MarketID") or ev.get("StationMarketID"))
                    distance_ls = _as_optional_float(
                        ev.get("DistFromStarLS") or ev.get("DistanceFromArrivalLS")
                    )
                    distance_conf = "observed" if distance_ls is not None else "unknown"
                    _upsert_station_observed(
                        conn,
                        system_name=system_name or _as_text(fallback_system_name) or "UNKNOWN_SYSTEM",
                        system_address=system_address,
                        station_name=station_name,
                        market_id=market_id,
                        station_type=_event_station_type(ev),
                        distance_ls=distance_ls,
                        distance_ls_confidence=distance_conf,
                        has_uc=services.get("has_uc") if has_services_list else None,
                        has_vista=services.get("has_vista") if has_services_list else None,
                        has_market=services.get("has_market") if has_services_list else None,
                        seen_ts=ts,
                        services_freshness_ts=ts if (has_services_list and services) else None,
                        source="journal",
                        confidence="observed",
                    )
                    touched_station = True

            service_name = _cashin_service_for_event(event_name)
            if service_name:
                station_name = station_name_fallback
                total_earnings = _as_optional_int(
                    ev.get("TotalEarnings")
                    or ev.get("Earnings")
                    or ev.get("Value")
                    or ev.get("Total")
                )
                if total_earnings is None:
                    total_earnings = 0
                conn.execute(
                    """
                    INSERT INTO cashin_history(
                        event_ts, system_name, station_name, service, total_earnings, source, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ts,
                        system_name or None,
                        station_name or None,
                        service_name,
                        int(total_earnings),
                        "journal",
                        "observed",
                    ),
                )
                touched_cashin = True
                if system_name and station_name:
                    _upsert_station_observed(
                        conn,
                        system_name=system_name,
                        system_address=system_address,
                        station_name=station_name,
                        market_id=_as_optional_int(ev.get("MarketID") or ev.get("StationMarketID")),
                        station_type=_event_station_type(ev),
                        distance_ls=None,
                        distance_ls_confidence="unknown",
                        has_uc=1 if service_name == "UC" else None,
                        has_vista=1 if service_name == "VISTA" else None,
                        has_market=None,
                        seen_ts=ts,
                        services_freshness_ts=None,
                        source="journal",
                        confidence="observed",
                    )
                    touched_station = True
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "ok": True,
        "event": event_name,
        "system_name": system_name,
        "system_address": system_address,
        "ingested_system": bool(touched_system),
        "ingested_station": bool(touched_station),
        "ingested_cashin": bool(touched_cashin),
        "path": db_path,
    }


def ingest_market_json(
    data: dict[str, Any] | None,
    *,
    path: str | None = None,
    fallback_system_name: str | None = None,
    fallback_station_name: str | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"ok": False, "reason": "invalid_market_payload"}

    station_name = _as_text(
        data.get("StationName")
        or data.get("stationName")
        or data.get("Name")
        or fallback_station_name
    )
    system_name = _as_text(data.get("StarSystem") or data.get("SystemName") or fallback_system_name)
    if not station_name or not system_name:
        return {
            "ok": False,
            "reason": "missing_station_or_system",
            "station_name": station_name,
            "system_name": system_name,
        }

    ts = _safe_ts(data.get("timestamp") or data.get("Timestamp") or data.get("updatedAt"))
    market_id = _as_optional_int(data.get("MarketID") or data.get("marketId"))
    items = _market_items_list(data)
    hash_sig, commodities_count = _normalized_market_items_hash(items)
    db_path = str(path or default_playerdb_path())

    with playerdb_connection(path=db_path, ensure_schema=True) as conn:
        conn.execute("BEGIN;")
        try:
            _upsert_station_observed(
                conn,
                system_name=system_name,
                system_address=None,
                station_name=station_name,
                market_id=market_id,
                station_type=_as_text(data.get("StationType") or ""),
                distance_ls=None,
                distance_ls_confidence="unknown",
                has_uc=None,
                has_vista=None,
                has_market=1,
                seen_ts=ts,
                services_freshness_ts=None,
                source="market_json",
                confidence="observed",
            )

            dedupe_row = None
            if hash_sig:
                if market_id is not None:
                    dedupe_row = conn.execute(
                        """
                        SELECT id FROM market_snapshots
                        WHERE station_market_id = ? AND hash_sig = ?
                        ORDER BY id DESC LIMIT 1;
                        """,
                        (market_id, hash_sig),
                    ).fetchone()
                else:
                    dedupe_row = conn.execute(
                        """
                        SELECT id FROM market_snapshots
                        WHERE system_name = ? COLLATE NOCASE
                          AND station_name = ? COLLATE NOCASE
                          AND hash_sig = ?
                        ORDER BY id DESC LIMIT 1;
                        """,
                        (system_name, station_name, hash_sig),
                    ).fetchone()

            if dedupe_row is not None:
                conn.execute(
                    """
                    UPDATE market_snapshots
                    SET freshness_ts = ?, commodities_count = ?, source = ?, confidence = ?
                    WHERE id = ?;
                    """,
                    (ts, commodities_count, "market_json", "observed", int(dedupe_row["id"])),
                )
                conn.commit()
                return {
                    "ok": True,
                    "deduped": True,
                    "snapshot_id": int(dedupe_row["id"]),
                    "commodities_count": commodities_count,
                    "hash_sig": hash_sig,
                    "path": db_path,
                }

            cursor = conn.execute(
                """
                INSERT INTO market_snapshots(
                    system_name, station_name, station_market_id,
                    snapshot_ts, freshness_ts, source, confidence, hash_sig, commodities_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    system_name,
                    station_name,
                    market_id,
                    ts,
                    ts,
                    "market_json",
                    "observed",
                    hash_sig,
                    commodities_count,
                ),
            )
            snapshot_id = int(cursor.lastrowid or 0)
            if snapshot_id and items:
                for item in items:
                    commodity = _commodity_name(item)
                    if not commodity:
                        continue
                    conn.execute(
                        """
                        INSERT INTO market_snapshot_items(
                            snapshot_id, commodity, buy_price, sell_price, stock, supply, demand,
                            mean_price, stock_bracket, supply_bracket, demand_bracket
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            snapshot_id,
                            commodity,
                            _as_optional_int(item.get("BuyPrice") or item.get("buyPrice")),
                            _as_optional_int(item.get("SellPrice") or item.get("sellPrice")),
                            _as_optional_int(item.get("Stock") or item.get("stock")),
                            _as_optional_int(item.get("Supply") or item.get("supply")),
                            _as_optional_int(item.get("Demand") or item.get("demand")),
                            _as_optional_int(item.get("MeanPrice") or item.get("meanPrice")),
                            _as_optional_int(item.get("StockBracket") or item.get("stockBracket")),
                            _as_optional_int(item.get("SupplyBracket") or item.get("supplyBracket")),
                            _as_optional_int(item.get("DemandBracket") or item.get("demandBracket")),
                        ),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "ok": True,
        "deduped": False,
        "snapshot_id": snapshot_id,
        "commodities_count": commodities_count,
        "hash_sig": hash_sig,
        "path": db_path,
    }


def query_cashin_history(
    *,
    path: str | None = None,
    service: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    db_path = str(path or default_playerdb_path())
    svc = _as_text(service).upper()
    max_rows = max(1, int(limit or 20))
    sql = """
        SELECT event_ts, system_name, station_name, service, total_earnings, source, confidence
        FROM cashin_history
    """
    params: list[Any] = []
    if svc in {"UC", "VISTA"}:
        sql += " WHERE service = ?"
        params.append(svc)
    sql += " ORDER BY event_ts DESC, id DESC LIMIT ?"
    params.append(max_rows)

    with playerdb_connection(path=db_path, ensure_schema=True) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "event_ts": _as_text(row["event_ts"]),
                "system_name": _as_text(row["system_name"]),
                "station_name": _as_text(row["station_name"]),
                "service": _as_text(row["service"]).upper(),
                "total_earnings": int(row["total_earnings"] or 0),
                "source": _as_text(row["source"]) or "playerdb",
                "confidence": _as_text(row["confidence"]) or "observed",
            }
        )
    return out


def query_nearest_station_candidates(
    *,
    path: str | None = None,
    origin_system_name: str | None = None,
    origin_coords: tuple[float, float, float] | list[float] | None = None,
    service: str = "uc",
    limit: int = 24,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    db_path = str(path or default_playerdb_path())
    svc = _as_text(service).lower()
    if svc not in {"uc", "vista", "market", "any"}:
        svc = "uc"
    max_rows = max(1, int(limit or 24))

    origin_coords_tuple: tuple[float, float, float] | None = None
    if isinstance(origin_coords, (list, tuple)) and len(origin_coords) >= 3:
        try:
            origin_coords_tuple = (
                float(origin_coords[0]),
                float(origin_coords[1]),
                float(origin_coords[2]),
            )
        except Exception:
            origin_coords_tuple = None

    origin_name = _as_text(origin_system_name)
    used_origin_coords_from_db = False
    with playerdb_connection(path=db_path, ensure_schema=True) as conn:
        if origin_coords_tuple is None and origin_name:
            row = conn.execute(
                """
                SELECT x, y, z FROM systems
                WHERE system_name = ? COLLATE NOCASE
                LIMIT 1;
                """,
                (origin_name,),
            ).fetchone()
            if row is not None and row["x"] is not None and row["y"] is not None and row["z"] is not None:
                origin_coords_tuple = (float(row["x"]), float(row["y"]), float(row["z"]))
                used_origin_coords_from_db = True

        sql = """
            SELECT
                s.station_name,
                s.station_type,
                s.is_fleet_carrier,
                s.distance_ls,
                s.distance_ls_confidence,
                s.has_uc,
                s.has_vista,
                s.has_market,
                s.last_seen_ts AS station_last_seen_ts,
                s.services_freshness_ts,
                s.confidence AS station_confidence,
                s.system_name,
                sys.x, sys.y, sys.z,
                sys.last_seen_ts AS system_last_seen_ts
            FROM stations s
            LEFT JOIN systems sys
              ON s.system_address IS NOT NULL AND sys.system_address = s.system_address
            WHERE 1=1
        """
        params: list[Any] = []
        if svc == "uc":
            sql += " AND s.has_uc = 1"
        elif svc == "vista":
            sql += " AND s.has_vista = 1"
        elif svc == "market":
            sql += " AND s.has_market = 1"
        sql += " ORDER BY COALESCE(s.services_freshness_ts, s.last_seen_ts) DESC, s.system_name, s.station_name LIMIT ?"
        params.append(max_rows * 8)
        rows = conn.execute(sql, tuple(params)).fetchall()

    candidates: list[dict[str, Any]] = []
    coords_missing = 0
    for row in rows:
        target_coords = None
        try:
            if row["x"] is not None and row["y"] is not None and row["z"] is not None:
                target_coords = (float(row["x"]), float(row["y"]), float(row["z"]))
        except Exception:
            target_coords = None
        if target_coords is None:
            coords_missing += 1
        distance_ly = _distance_between_coords(origin_coords_tuple, target_coords)
        candidate_conf = _freshness_confidence_from_station(
            services_freshness_ts=row["services_freshness_ts"],
            last_seen_ts=row["station_last_seen_ts"],
        )
        candidates.append(
            {
                "name": _as_text(row["station_name"]),
                "system_name": _as_text(row["system_name"]),
                "type": "fleet_carrier" if int(row["is_fleet_carrier"] or 0) else _as_text(row["station_type"]) or "station",
                "services": {
                    "has_uc": bool(int(row["has_uc"] or 0)),
                    "has_vista": bool(int(row["has_vista"] or 0)),
                    "has_market": bool(int(row["has_market"] or 0)),
                },
                "distance_ly": distance_ly,
                "distance_ls": _as_optional_float(row["distance_ls"]),
                "distance_ls_confidence": _as_text(row["distance_ls_confidence"]) or "unknown",
                "source": "PLAYERDB",
                "freshness_ts": _as_text(row["services_freshness_ts"] or row["station_last_seen_ts"] or row["system_last_seen_ts"]),
                "confidence": candidate_conf,
                "station_last_seen_ts": _as_text(row["station_last_seen_ts"]),
                "services_freshness_ts": _as_text(row["services_freshness_ts"]),
            }
        )

    # nearest first when coords available; otherwise fallback to freshness/name ordering
    def _sort_key(item: dict[str, Any]) -> tuple[float, float, str, str]:
        dist_ly = item.get("distance_ly")
        dly = float(dist_ly) if isinstance(dist_ly, (int, float)) else 1e18
        dist_ls = item.get("distance_ls")
        dls = float(dist_ls) if isinstance(dist_ls, (int, float)) else 1e18
        return (
            dly,
            dls,
            _as_text(item.get("freshness_ts")),
            f"{_as_text(item.get('system_name')).casefold()}::{_as_text(item.get('name')).casefold()}",
        )

    candidates.sort(key=_sort_key)
    candidates = candidates[:max_rows]
    meta = {
        "service": svc,
        "count": len(candidates),
        "origin_system_name": origin_name,
        "origin_coords_used": bool(origin_coords_tuple),
        "origin_coords_from_playerdb": bool(used_origin_coords_from_db),
        "coords_missing_count": int(coords_missing),
        "query_mode": "nearest" if origin_coords_tuple is not None else "last_seen",
    }
    return candidates, meta


def _prefix_sql_where(columns: list[str], prefixes: list[str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for col in columns:
        parts: list[str] = []
        for pref in prefixes:
            parts.append(f"{col} LIKE ? COLLATE NOCASE")
            params.append(f"{pref}%")
        if parts:
            clauses.append("(" + " OR ".join(parts) + ")")
    if not clauses:
        return ("0=1", [])
    return (" OR ".join(clauses), params)


def _count_query(conn: sqlite3.Connection, sql: str, params: list[Any]) -> int:
    row = conn.execute(sql, tuple(params)).fetchone()
    try:
        return int(row[0] if row is not None else 0)
    except Exception:
        return 0


def cleanup_fixture_test_data(
    *,
    path: str | None = None,
    prefixes: list[str] | tuple[str, ...] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    db_path = str(path or default_playerdb_path())
    prefix_list = [
        _as_text(p).upper()
        for p in (prefixes or DEFAULT_FIXTURE_PREFIXES)
        if _as_text(p)
    ]
    # Normalize to unique, deterministic order.
    prefix_list = sorted(set(prefix_list))
    if not prefix_list:
        return {
            "ok": False,
            "reason": "no_prefixes",
            "path": db_path,
            "dry_run": bool(dry_run),
            "prefixes": [],
        }

    with playerdb_connection(path=db_path, ensure_schema=True) as conn:
        stations_where, stations_params = _prefix_sql_where(
            ["system_name", "station_name"],
            prefix_list,
        )
        systems_where, systems_params = _prefix_sql_where(["system_name"], prefix_list)
        cashin_where, cashin_params = _prefix_sql_where(["system_name", "station_name"], prefix_list)
        trade_where, trade_params = _prefix_sql_where(["system_name", "station_name"], prefix_list)

        fixture_station_rows = conn.execute(
            f"""
            SELECT id, market_id, system_name, station_name
            FROM stations
            WHERE {stations_where};
            """,
            tuple(stations_params),
        ).fetchall()
        station_ids = [int(r["id"]) for r in fixture_station_rows]
        station_market_ids = [int(r["market_id"]) for r in fixture_station_rows if r["market_id"] is not None]

        fixture_snapshot_ids: set[int] = set()
        if station_market_ids:
            placeholders = ",".join(["?"] * len(station_market_ids))
            rows = conn.execute(
                f"SELECT id FROM market_snapshots WHERE station_market_id IN ({placeholders});",
                tuple(station_market_ids),
            ).fetchall()
            fixture_snapshot_ids.update(int(r["id"]) for r in rows)
        rows = conn.execute(
            f"""
            SELECT id FROM market_snapshots
            WHERE {stations_where};
            """,
            tuple(stations_params),
        ).fetchall()
        fixture_snapshot_ids.update(int(r["id"]) for r in rows)

        snapshot_ids = sorted(fixture_snapshot_ids)
        snapshot_item_count = 0
        if snapshot_ids:
            placeholders = ",".join(["?"] * len(snapshot_ids))
            snapshot_item_count = _count_query(
                conn,
                f"SELECT COUNT(*) FROM market_snapshot_items WHERE snapshot_id IN ({placeholders});",
                snapshot_ids,
            )

        report = {
            "ok": True,
            "path": db_path,
            "dry_run": bool(dry_run),
            "prefixes": prefix_list,
            "counts": {
                "systems": _count_query(conn, f"SELECT COUNT(*) FROM systems WHERE {systems_where};", systems_params),
                "stations": len(station_ids),
                "market_snapshots": len(snapshot_ids),
                "market_snapshot_items": int(snapshot_item_count),
                "cashin_history": _count_query(
                    conn,
                    f"SELECT COUNT(*) FROM cashin_history WHERE {cashin_where};",
                    cashin_params,
                ),
                "trade_history": _count_query(
                    conn,
                    f"SELECT COUNT(*) FROM trade_history WHERE {trade_where};",
                    trade_params,
                ),
            },
            "preview": {
                "systems": [
                    _as_text(r["system_name"])
                    for r in conn.execute(
                        f"SELECT system_name FROM systems WHERE {systems_where} ORDER BY system_name LIMIT 10;",
                        tuple(systems_params),
                    ).fetchall()
                ],
                "stations": [
                    {
                        "system_name": _as_text(r["system_name"]),
                        "station_name": _as_text(r["station_name"]),
                    }
                    for r in fixture_station_rows[:10]
                ],
            },
        }
        report["counts"]["total_rows"] = sum(int(v or 0) for v in report["counts"].values())

        if dry_run:
            return report

        conn.execute("BEGIN;")
        try:
            if snapshot_ids:
                placeholders = ",".join(["?"] * len(snapshot_ids))
                # market_snapshot_items are ON DELETE CASCADE, but we also report them explicitly.
                conn.execute(
                    f"DELETE FROM market_snapshots WHERE id IN ({placeholders});",
                    tuple(snapshot_ids),
                )
            conn.execute(f"DELETE FROM cashin_history WHERE {cashin_where};", tuple(cashin_params))
            conn.execute(f"DELETE FROM trade_history WHERE {trade_where};", tuple(trade_params))
            conn.execute(f"DELETE FROM stations WHERE {stations_where};", tuple(stations_params))
            conn.execute(f"DELETE FROM systems WHERE {systems_where};", tuple(systems_params))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return report


def _fixture_cleanup_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m logic.player_local_db",
        description="Cleanup fixture/test records from player_local.db by prefixes (dry-run by default).",
    )
    parser.add_argument("--path", default=None, help="Path to player_local.db (default: runtime APPDATA path)")
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        help="Fixture prefix (repeatable). Defaults include F19_/F20_/.../SMOKE_/QG_/TEST_.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletions. Without this flag, command runs in dry-run mode.",
    )
    args = parser.parse_args(argv)
    report = cleanup_fixture_test_data(
        path=args.path,
        prefixes=args.prefixes,
        dry_run=not bool(args.apply),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


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


if __name__ == "__main__":
    raise SystemExit(_fixture_cleanup_cli())
