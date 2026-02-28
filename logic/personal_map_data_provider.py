from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from logic import player_local_db
from logic.utils.renata_log import log_event_throttled

_TIME_RANGE_DAYS: dict[str, int] = {
    "1d": 1,
    "3d": 3,
    "7d": 7,
    "7": 7,
    "week": 7,
    "1w": 7,
    "14d": 14,
    "2w": 14,
    "30d": 30,
    "30": 30,
    "month": 30,
    "1m": 30,
    "90d": 90,
    "3m": 90,
    "180d": 180,
    "6m": 180,
    "365d": 365,
    "1y": 365,
    "year": 365,
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


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
        log_event_throttled(
            "map_data_provider:parse_iso_ts",
            30.0,
            "map provider timestamp parse failed",
            value=text[:120],
        )
        return None


def _cutoff_for_time_range(value: Any) -> datetime | None:
    text = _as_text(value).lower()
    if not text or text in {"all", "any", "*", "forever"}:
        return None
    now = datetime.now(timezone.utc)
    if text.endswith("h"):
        try:
            return now - timedelta(hours=max(1, int(text[:-1])))
        except Exception:
            return None
    days = _TIME_RANGE_DAYS.get(text)
    if days is None and text.endswith("d"):
        try:
            days = max(1, int(text[:-1]))
        except Exception:
            days = None
    if days is not None:
        return now - timedelta(days=days)
    return None


def _max_age_for_freshness_filter(value: Any) -> timedelta | None:
    text = _as_text(value).lower()
    if not text or text in {"all", "any", "*"}:
        return None
    if "6h" in text:
        return timedelta(hours=6)
    if "24h" in text:
        return timedelta(hours=24)
    if "7d" in text or "7 d" in text:
        return timedelta(days=7)
    return None


def _age_hours(ts: str) -> float | None:
    dt = _parse_iso_ts(ts)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


class MapDataProvider:
    """
    Warstwa adaptera danych dla Personal Galaxy Map.

    Cel:
    - UI mapy nie wykonuje bezposredniego SQL,
    - adapter zwraca rekordy z `source/freshness/confidence`,
    - kontrakt jest zgodny ze spieciem PlayerDB/Cash-In.
    """

    def __init__(self, *, db_path: str | None = None) -> None:
        self.db_path = str(db_path or player_local_db.default_playerdb_path())

    def get_system_nodes(
        self,
        time_range: str = "all",
        source_filter: str = "observed_only",
        *,
        limit: int = 5000,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        cutoff = _cutoff_for_time_range(time_range)
        max_rows = max(1, int(limit or 5000))
        sql = """
            SELECT
                system_name,
                system_address,
                system_id64,
                x, y, z,
                primary_star_type,
                is_neutron,
                is_black_hole,
                source,
                confidence,
                first_seen_ts,
                last_seen_ts
            FROM systems
            WHERE 1=1
        """
        params: list[Any] = []
        if cutoff is not None:
            sql += " AND COALESCE(last_seen_ts, first_seen_ts) >= ?"
            params.append(cutoff.isoformat().replace("+00:00", "Z"))
        # PlayerDB baseline jest observed-only; `include enriched` zostawiamy jako future-ready no-op.
        if _as_text(source_filter).lower() in {"observed_only", "observed-only"}:
            sql += " AND (source IS NULL OR source = '' OR lower(source) IN ('journal','market_json','playerdb'))"
        sql += " ORDER BY COALESCE(last_seen_ts, first_seen_ts) DESC, system_name COLLATE NOCASE LIMIT ?"
        params.append(max_rows)

        rows_out: list[dict[str, Any]] = []
        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            freshness_ts = _as_text(row["last_seen_ts"] or row["first_seen_ts"])
            rows_out.append(
                {
                    "system_name": _as_text(row["system_name"]),
                    "system_address": row["system_address"],
                    "system_id64": row["system_id64"],
                    "x": float(row["x"]) if row["x"] is not None else None,
                    "y": float(row["y"]) if row["y"] is not None else None,
                    "z": float(row["z"]) if row["z"] is not None else None,
                    "primary_star_type": _as_text(row["primary_star_type"]),
                    "is_neutron": int(bool(row["is_neutron"])) if row["is_neutron"] is not None else 0,
                    "is_black_hole": int(bool(row["is_black_hole"])) if row["is_black_hole"] is not None else 0,
                    "first_seen_ts": _as_text(row["first_seen_ts"]),
                    "last_seen_ts": _as_text(row["last_seen_ts"]),
                    "source": _as_text(row["source"]) or "playerdb",
                    "confidence": _as_text(row["confidence"]) or "observed",
                    "freshness_ts": freshness_ts,
                }
            )

        return rows_out, {
            "count": len(rows_out),
            "time_range": _as_text(time_range) or "all",
            "source_filter": _as_text(source_filter) or "observed_only",
            "db_path": self.db_path,
        }

    def get_edges(
        self,
        time_range: str = "all",
        *,
        limit: int = 10000,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        F20-1 kontrakt adaptera:
        - zwraca meta nawet jesli brak danych skokow w aktualnym schema baseline.
        - realny renderer travel edges w F20-3 moze rozszerzyc to o ingest/query jumps.
        """
        _ = (time_range, limit)
        return [], {
            "count": 0,
            "time_range": _as_text(time_range) or "all",
            "available": False,
            "reason": "playerdb_jumps_not_ingested",
            "db_path": self.db_path,
        }

    def get_stations_for_system(
        self,
        system_id: Any = None,
        *,
        system_address: int | None = None,
        system_name: str | None = None,
        limit: int = 200,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        max_rows = max(1, int(limit or 200))
        sys_addr = system_address
        if sys_addr is None and isinstance(system_id, int):
            sys_addr = int(system_id)
        sys_name_text = _as_text(system_name)
        if not sys_name_text and system_id is not None and not isinstance(system_id, int):
            sys_name_text = _as_text(system_id)

        sql = """
            SELECT
                station_name,
                market_id,
                station_type,
                is_fleet_carrier,
                distance_ls,
                distance_ls_confidence,
                has_uc,
                has_vista,
                has_market,
                source,
                confidence,
                first_seen_ts,
                last_seen_ts,
                services_freshness_ts,
                system_name,
                system_address
            FROM stations
            WHERE 1=1
        """
        params: list[Any] = []
        if sys_addr is not None:
            sql += " AND system_address = ?"
            params.append(int(sys_addr))
        elif sys_name_text:
            sql += " AND system_name = ? COLLATE NOCASE"
            params.append(sys_name_text)
        sql += " ORDER BY COALESCE(distance_ls, 1e18), COALESCE(services_freshness_ts, last_seen_ts) DESC, station_name COLLATE NOCASE LIMIT ?"
        params.append(max_rows)

        out: list[dict[str, Any]] = []
        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            freshness_ts = _as_text(row["services_freshness_ts"] or row["last_seen_ts"] or row["first_seen_ts"])
            out.append(
                {
                    "system_name": _as_text(row["system_name"]),
                    "system_address": row["system_address"],
                    "station_name": _as_text(row["station_name"]),
                    "market_id": row["market_id"],
                    "station_type": _as_text(row["station_type"]) or "station",
                    "is_fleet_carrier": bool(int(row["is_fleet_carrier"] or 0)),
                    "distance_ls": float(row["distance_ls"]) if row["distance_ls"] is not None else None,
                    "distance_ls_confidence": _as_text(row["distance_ls_confidence"]) or "unknown",
                    "services": {
                        "has_uc": bool(int(row["has_uc"] or 0)),
                        "has_vista": bool(int(row["has_vista"] or 0)),
                        "has_market": bool(int(row["has_market"] or 0)),
                    },
                    "first_seen_ts": _as_text(row["first_seen_ts"]),
                    "last_seen_ts": _as_text(row["last_seen_ts"]),
                    "services_freshness_ts": _as_text(row["services_freshness_ts"]),
                    "source": _as_text(row["source"]) or "playerdb",
                    "confidence": _as_text(row["confidence"]) or "observed",
                    "freshness_ts": freshness_ts,
                }
            )

        return out, {
            "count": len(out),
            "system_address": sys_addr,
            "system_name": sys_name_text,
            "db_path": self.db_path,
        }

    def get_stations_for_systems(
        self,
        *,
        systems: list[dict[str, Any]] | None = None,
        limit_per_system: int = 200,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """
        Batch drilldown payload dla mapy: stacje per system bez N zapytan per klik.

        Zwraca slownik indeksowany po:
        - `addr:<system_address>` gdy address istnieje,
        - `name:<system_name.casefold()>` jako fallback.
        """
        max_rows_per_system = max(1, int(limit_per_system or 200))
        system_addresses: set[int] = set()
        system_names_cf: set[str] = set()
        for item in systems or []:
            if not isinstance(item, dict):
                continue
            raw_addr = item.get("system_address")
            if raw_addr is not None:
                try:
                    system_addresses.add(int(raw_addr))
                    continue
                except Exception:
                    pass
            name = _as_text(item.get("system_name"))
            if name:
                system_names_cf.add(name.casefold())

        if not system_addresses and not system_names_cf:
            return {}, {
                "count": 0,
                "systems_count": 0,
                "limit_per_system": max_rows_per_system,
                "db_path": self.db_path,
            }

        where_clauses: list[str] = []
        where_params: list[Any] = []
        if system_addresses:
            placeholders = ",".join("?" for _ in system_addresses)
            where_clauses.append(f"system_address IN ({placeholders})")
            where_params.extend(sorted(system_addresses))
        if system_names_cf:
            placeholders = ",".join("?" for _ in system_names_cf)
            where_clauses.append(f"lower(system_name) IN ({placeholders})")
            where_params.extend(sorted(system_names_cf))
        where_sql = " OR ".join(where_clauses) if where_clauses else "1=0"

        sql = f"""
            WITH scoped AS (
                SELECT
                    station_name,
                    market_id,
                    station_type,
                    is_fleet_carrier,
                    distance_ls,
                    distance_ls_confidence,
                    has_uc,
                    has_vista,
                    has_market,
                    source,
                    confidence,
                    first_seen_ts,
                    last_seen_ts,
                    services_freshness_ts,
                    system_name,
                    system_address,
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(CAST(system_address AS TEXT), lower(system_name))
                        ORDER BY
                            COALESCE(distance_ls, 1e18),
                            COALESCE(services_freshness_ts, last_seen_ts) DESC,
                            station_name COLLATE NOCASE
                    ) AS rn
                FROM stations
                WHERE ({where_sql})
            )
            SELECT
                station_name,
                market_id,
                station_type,
                is_fleet_carrier,
                distance_ls,
                distance_ls_confidence,
                has_uc,
                has_vista,
                has_market,
                source,
                confidence,
                first_seen_ts,
                last_seen_ts,
                services_freshness_ts,
                system_name,
                system_address
            FROM scoped
            WHERE rn <= ?
            ORDER BY
                COALESCE(CAST(system_address AS TEXT), lower(system_name)),
                rn
        """
        params: list[Any] = list(where_params)
        params.append(max_rows_per_system)

        grouped: dict[str, dict[str, Any]] = {}
        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            system_name = _as_text(row["system_name"])
            addr_raw = row["system_address"]
            system_address = None
            if addr_raw is not None:
                try:
                    system_address = int(addr_raw)
                except Exception:
                    system_address = None
            primary_key = (
                f"addr:{system_address}"
                if system_address is not None
                else f"name:{system_name.casefold()}"
            )
            bucket = grouped.setdefault(
                primary_key,
                {
                    "rows": [],
                    "meta": {
                        "count": 0,
                        "system_address": system_address,
                        "system_name": system_name,
                        "db_path": self.db_path,
                        "source": "batch",
                    },
                },
            )
            freshness_ts = _as_text(row["services_freshness_ts"] or row["last_seen_ts"] or row["first_seen_ts"])
            bucket["rows"].append(
                {
                    "system_name": system_name,
                    "system_address": system_address,
                    "station_name": _as_text(row["station_name"]),
                    "market_id": row["market_id"],
                    "station_type": _as_text(row["station_type"]) or "station",
                    "is_fleet_carrier": bool(int(row["is_fleet_carrier"] or 0)),
                    "distance_ls": float(row["distance_ls"]) if row["distance_ls"] is not None else None,
                    "distance_ls_confidence": _as_text(row["distance_ls_confidence"]) or "unknown",
                    "services": {
                        "has_uc": bool(int(row["has_uc"] or 0)),
                        "has_vista": bool(int(row["has_vista"] or 0)),
                        "has_market": bool(int(row["has_market"] or 0)),
                    },
                    "first_seen_ts": _as_text(row["first_seen_ts"]),
                    "last_seen_ts": _as_text(row["last_seen_ts"]),
                    "services_freshness_ts": _as_text(row["services_freshness_ts"]),
                    "source": _as_text(row["source"]) or "playerdb",
                    "confidence": _as_text(row["confidence"]) or "observed",
                    "freshness_ts": freshness_ts,
                }
            )

        out: dict[str, dict[str, Any]] = {}
        for payload in grouped.values():
            rows_list = [dict(item) for item in list(payload.get("rows") or []) if isinstance(item, dict)]
            meta = dict(payload.get("meta") or {})
            meta["count"] = len(rows_list)
            item_payload = {"rows": rows_list, "meta": meta}
            system_name = _as_text(meta.get("system_name"))
            system_address = meta.get("system_address")
            if system_address is not None:
                try:
                    out[f"addr:{int(system_address)}"] = {
                        "rows": [dict(r) for r in rows_list],
                        "meta": dict(meta),
                    }
                except Exception:
                    pass
            if system_name:
                out[f"name:{system_name.casefold()}"] = {
                    "rows": [dict(r) for r in rows_list],
                    "meta": dict(meta),
                }
            # Fallback key in edge cases with missing addr+name.
            if system_address is None and not system_name:
                out_key = f"group:{len(out)}"
                out[out_key] = item_payload

        return out, {
            "count": len(out),
            "systems_count": len(system_addresses) + len(system_names_cf),
            "limit_per_system": max_rows_per_system,
            "db_path": self.db_path,
        }

    def get_station_layer_flags_for_systems(
        self,
        *,
        systems: list[dict[str, Any]] | None = None,
        freshness_filter: str = "any",
        limit_per_system: int = 200,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """
        Batch-owe flagi stacji dla warstw mapy (minimalizacja N+1 dla reloadu mapy).

        Zwraca slownik indeksowany po:
        - `addr:<system_address>` gdy address istnieje,
        - `name:<system_name.casefold()>` jako fallback.
        """
        max_rows_per_system = max(1, int(limit_per_system or 200))
        system_addresses: set[int] = set()
        system_names_cf: set[str] = set()
        for item in systems or []:
            if not isinstance(item, dict):
                continue
            raw_addr = item.get("system_address")
            if raw_addr is not None:
                try:
                    system_addresses.add(int(raw_addr))
                    continue
                except Exception:
                    pass
            system_name = _as_text(item.get("system_name"))
            if system_name:
                system_names_cf.add(system_name.casefold())
        if not system_addresses and not system_names_cf:
            return {}, {
                "count": 0,
                "systems_count": 0,
                "freshness_filter": _as_text(freshness_filter) or "any",
                "db_path": self.db_path,
            }

        where_clauses: list[str] = []
        where_params: list[Any] = []
        if system_addresses:
            placeholders = ",".join("?" for _ in system_addresses)
            where_clauses.append(f"system_address IN ({placeholders})")
            where_params.extend(sorted(system_addresses))
        if system_names_cf:
            placeholders = ",".join("?" for _ in system_names_cf)
            where_clauses.append(f"lower(system_name) IN ({placeholders})")
            where_params.extend(sorted(system_names_cf))
        where_sql = " OR ".join(where_clauses) if where_clauses else "1=0"

        max_age = _max_age_for_freshness_filter(freshness_filter)
        freshness_sql = "1=1"
        freshness_params: list[Any] = []
        if max_age is not None:
            cutoff = datetime.now(timezone.utc) - max_age
            cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
            freshness_sql = "COALESCE(services_freshness_ts, last_seen_ts, first_seen_ts) >= ?"
            # expression is repeated in SELECT (count + two boolean aggregates)
            freshness_params.extend([cutoff_iso, cutoff_iso, cutoff_iso])

        sql = f"""
            WITH scoped AS (
                SELECT
                    system_address,
                    system_name,
                    has_uc,
                    has_vista,
                    has_market,
                    first_seen_ts,
                    last_seen_ts,
                    services_freshness_ts,
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(CAST(system_address AS TEXT), lower(system_name))
                        ORDER BY
                            COALESCE(distance_ls, 1e18),
                            COALESCE(services_freshness_ts, last_seen_ts) DESC,
                            station_name COLLATE NOCASE
                    ) AS rn
                FROM stations
                WHERE ({where_sql})
            )
            SELECT
                system_address,
                MIN(system_name) AS system_name,
                SUM(CASE WHEN {freshness_sql} THEN 1 ELSE 0 END) AS stations_count,
                MAX(CASE WHEN {freshness_sql} AND COALESCE(has_market, 0) != 0 THEN 1 ELSE 0 END) AS has_market,
                MAX(
                    CASE
                        WHEN {freshness_sql} AND (COALESCE(has_uc, 0) != 0 OR COALESCE(has_vista, 0) != 0)
                        THEN 1
                        ELSE 0
                    END
                ) AS has_cashin
            FROM scoped
            WHERE rn <= ?
            GROUP BY COALESCE(CAST(system_address AS TEXT), lower(system_name))
        """
        params: list[Any] = list(where_params)
        params.extend(freshness_params)
        params.append(max_rows_per_system)

        out: dict[str, dict[str, Any]] = {}
        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        for row in rows:
            system_name = _as_text(row["system_name"])
            addr_raw = row["system_address"]
            system_address = None
            if addr_raw is not None:
                try:
                    system_address = int(addr_raw)
                except Exception:
                    system_address = None
            payload = {
                "system_name": system_name,
                "system_address": system_address,
                "stations_count": int(row["stations_count"] or 0),
                "has_market": bool(int(row["has_market"] or 0)),
                "has_cashin": bool(int(row["has_cashin"] or 0)),
            }
            if system_address is not None:
                out[f"addr:{system_address}"] = dict(payload)
            if system_name:
                out[f"name:{system_name.casefold()}"] = dict(payload)

        return out, {
            "count": len(out),
            "systems_count": len(system_addresses) + len(system_names_cf),
            "freshness_filter": _as_text(freshness_filter) or "any",
            "limit_per_system": max_rows_per_system,
            "db_path": self.db_path,
        }

    def get_market_last_seen(
        self,
        market_id: int,
        limit: int = 5,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        max_rows = max(1, int(limit or 5))
        market_id_int = int(market_id)
        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            snapshots = conn.execute(
                """
                SELECT id, system_name, station_name, station_market_id, snapshot_ts, freshness_ts,
                       source, confidence, hash_sig, commodities_count
                FROM market_snapshots
                WHERE station_market_id = ?
                ORDER BY snapshot_ts DESC, id DESC
                LIMIT ?;
                """,
                (market_id_int, max_rows),
            ).fetchall()
            snapshot_ids = [int(r["id"]) for r in snapshots]
            items_by_snapshot: dict[int, list[dict[str, Any]]] = {sid: [] for sid in snapshot_ids}
            if snapshot_ids:
                placeholders = ",".join("?" for _ in snapshot_ids)
                item_rows = conn.execute(
                    f"""
                    SELECT snapshot_id, commodity, buy_price, sell_price, stock, supply, demand,
                           mean_price, stock_bracket, supply_bracket, demand_bracket
                    FROM market_snapshot_items
                    WHERE snapshot_id IN ({placeholders})
                    ORDER BY snapshot_id DESC, commodity COLLATE NOCASE;
                    """,
                    tuple(snapshot_ids),
                ).fetchall()
                for row in item_rows:
                    sid = int(row["snapshot_id"])
                    items_by_snapshot.setdefault(sid, []).append(
                        {
                            "commodity": _as_text(row["commodity"]),
                            "buy_price": row["buy_price"],
                            "sell_price": row["sell_price"],
                            "stock": row["stock"],
                            "supply": row["supply"],
                            "demand": row["demand"],
                            "mean_price": row["mean_price"],
                            "stock_bracket": row["stock_bracket"],
                            "supply_bracket": row["supply_bracket"],
                            "demand_bracket": row["demand_bracket"],
                        }
                    )

        out: list[dict[str, Any]] = []
        for row in snapshots:
            sid = int(row["id"])
            out.append(
                {
                    "snapshot_id": sid,
                    "system_name": _as_text(row["system_name"]),
                    "station_name": _as_text(row["station_name"]),
                    "market_id": row["station_market_id"],
                    "snapshot_ts": _as_text(row["snapshot_ts"]),
                    "freshness_ts": _as_text(row["freshness_ts"]),
                    "source": _as_text(row["source"]) or "market_json",
                    "confidence": _as_text(row["confidence"]) or "observed",
                    "commodities_count": int(row["commodities_count"] or 0),
                    "hash_sig": _as_text(row["hash_sig"]),
                    "items": items_by_snapshot.get(sid, []),
                }
            )

        return out, {
            "count": len(out),
            "market_id": market_id_int,
            "db_path": self.db_path,
        }

    def get_top_prices(
        self,
        commodity: str,
        mode: str,
        time_range: str = "all",
        freshness_filter: str = "any",
        *,
        system_name: str | None = None,
        station_market_id: int | None = None,
        station_name: str | None = None,
        limit: int = 5,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        commodity_name = _as_text(commodity)
        mode_norm = _as_text(mode).lower()
        if mode_norm not in {"buy", "sell"}:
            mode_norm = "sell"
        max_rows = max(1, int(limit or 5))
        cutoff = _cutoff_for_time_range(time_range)
        max_age = _max_age_for_freshness_filter(freshness_filter)
        system_filter = _as_text(system_name)
        station_filter = _as_text(station_name)
        market_filter: int | None = None
        try:
            if station_market_id is not None:
                market_filter = int(station_market_id)
        except Exception:
            market_filter = None

        sql = """
            SELECT
                ms.id AS snapshot_id,
                ms.system_name,
                ms.station_name,
                ms.station_market_id,
                ms.snapshot_ts,
                ms.freshness_ts,
                ms.source,
                ms.confidence,
                msi.commodity,
                msi.buy_price,
                msi.sell_price,
                s.distance_ls,
                s.distance_ls_confidence,
                s.has_uc,
                s.has_vista,
                s.has_market
            FROM market_snapshot_items msi
            JOIN market_snapshots ms ON ms.id = msi.snapshot_id
            LEFT JOIN stations s
              ON ms.station_market_id IS NOT NULL AND s.market_id = ms.station_market_id
            WHERE msi.commodity = ? COLLATE NOCASE
        """
        params: list[Any] = [commodity_name]
        if system_filter:
            sql += " AND ms.system_name = ? COLLATE NOCASE"
            params.append(system_filter)
        if market_filter is not None:
            sql += " AND ms.station_market_id = ?"
            params.append(market_filter)
        elif station_filter:
            sql += " AND ms.station_name = ? COLLATE NOCASE"
            params.append(station_filter)
        if cutoff is not None:
            sql += " AND ms.snapshot_ts >= ?"
            params.append(cutoff.isoformat().replace("+00:00", "Z"))
        if mode_norm == "sell":
            sql += " AND msi.sell_price IS NOT NULL"
        else:
            sql += " AND msi.buy_price IS NOT NULL"
        sql += " ORDER BY ms.snapshot_ts DESC, ms.id DESC"

        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        # Last-seen per station (market_id; fallback system+station)
        seen_keys: set[str] = set()
        filtered: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            freshness_ts = _as_text(row["freshness_ts"] or row["snapshot_ts"])
            if max_age is not None:
                dt = _parse_iso_ts(freshness_ts)
                if dt is None or (now - dt) > max_age:
                    continue
            key = (
                f"mid:{int(row['station_market_id'])}"
                if row["station_market_id"] is not None
                else f"{_as_text(row['system_name']).casefold()}::{_as_text(row['station_name']).casefold()}"
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            price_value = row["buy_price"] if mode_norm == "buy" else row["sell_price"]
            filtered.append(
                {
                    "commodity": _as_text(row["commodity"]),
                    "mode": mode_norm,
                    "price": int(price_value or 0),
                    "buy_price": row["buy_price"],
                    "sell_price": row["sell_price"],
                    "system_name": _as_text(row["system_name"]),
                    "station_name": _as_text(row["station_name"]),
                    "market_id": row["station_market_id"],
                    "snapshot_id": int(row["snapshot_id"]),
                    "snapshot_ts": _as_text(row["snapshot_ts"]),
                    "freshness_ts": freshness_ts,
                    "freshness_age_h": _age_hours(freshness_ts),
                    "source": _as_text(row["source"]) or "market_json",
                    "confidence": _as_text(row["confidence"]) or "observed",
                    "distance_ls": float(row["distance_ls"]) if row["distance_ls"] is not None else None,
                    "distance_ls_confidence": _as_text(row["distance_ls_confidence"]) or "unknown",
                    "services": {
                        "has_uc": bool(int(row["has_uc"] or 0)),
                        "has_vista": bool(int(row["has_vista"] or 0)),
                        "has_market": bool(int(row["has_market"] or 0)),
                    },
                }
            )

        if mode_norm == "sell":
            filtered.sort(key=lambda r: (-int(r["price"]), _as_text(r["freshness_ts"]), _as_text(r["station_name"]).casefold()))
        else:
            filtered.sort(key=lambda r: (int(r["price"]) if r["price"] is not None else 10**18, _as_text(r["freshness_ts"]), _as_text(r["station_name"]).casefold()))
        filtered = filtered[:max_rows]

        return filtered, {
            "count": len(filtered),
            "commodity": commodity_name,
            "mode": mode_norm,
            "time_range": _as_text(time_range) or "all",
            "freshness_filter": _as_text(freshness_filter) or "any",
            "system_name": system_filter,
            "station_market_id": market_filter,
            "station_name": station_filter,
            "db_path": self.db_path,
        }

    def get_known_commodities(
        self,
        time_range: str = "all",
        freshness_filter: str = "any",
        *,
        limit: int = 300,
    ) -> tuple[list[str], dict[str, Any]]:
        max_rows = max(1, int(limit or 300))
        cutoff = _cutoff_for_time_range(time_range)
        max_age = _max_age_for_freshness_filter(freshness_filter)

        sql = """
            SELECT msi.commodity, MAX(COALESCE(ms.freshness_ts, ms.snapshot_ts)) AS freshness_ts
            FROM market_snapshot_items msi
            JOIN market_snapshots ms ON ms.id = msi.snapshot_id
            WHERE msi.commodity IS NOT NULL AND trim(msi.commodity) != ''
        """
        params: list[Any] = []
        if cutoff is not None:
            sql += " AND ms.snapshot_ts >= ?"
            params.append(cutoff.isoformat().replace("+00:00", "Z"))
        sql += " GROUP BY lower(msi.commodity), msi.commodity ORDER BY lower(msi.commodity) LIMIT ?"
        params.append(max_rows * 3)  # reserve room before freshness post-filter

        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        out: list[str] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            commodity = _as_text(row["commodity"])
            if not commodity:
                continue
            if max_age is not None:
                dt = _parse_iso_ts(row["freshness_ts"])
                if dt is None or (now - dt) > max_age:
                    continue
            out.append(commodity)
            if len(out) >= max_rows:
                break

        return out, {
            "count": len(out),
            "time_range": _as_text(time_range) or "all",
            "freshness_filter": _as_text(freshness_filter) or "any",
            "db_path": self.db_path,
        }

    def get_system_action_flags(
        self,
        *,
        system_names: list[str] | None = None,
        time_range: str = "all",
        freshness_filter: str = "any",
        limit: int = 5000,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """
        Best-effort aktywnosci systemowe dla warstw mapy (F21-3).

        Aktualny baseline PlayerDB (F16) daje pewne dane tylko dla:
        - Exploration (cash-in UC)
        - Exobio (cash-in Vista)

        Incidents / Combat zostaja future-ready i sa raportowane w meta jako unsupported.
        """
        max_rows = max(1, int(limit or 5000))
        cutoff = _cutoff_for_time_range(time_range)
        max_age = _max_age_for_freshness_filter(freshness_filter)

        names_cf: set[str] = set()
        for item in system_names or []:
            text = _as_text(item)
            if text:
                names_cf.add(text.casefold())

        sql = """
            SELECT
                MIN(system_name) AS system_name,
                MAX(CASE WHEN upper(service) = 'UC' THEN 1 ELSE 0 END) AS has_exploration,
                MAX(CASE WHEN upper(service) = 'VISTA' THEN 1 ELSE 0 END) AS has_exobio,
                MAX(event_ts) AS last_action_ts
            FROM cashin_history
            WHERE system_name IS NOT NULL AND trim(system_name) != ''
        """
        params: list[Any] = []
        if cutoff is not None:
            sql += " AND event_ts >= ?"
            params.append(cutoff.isoformat().replace("+00:00", "Z"))
        if names_cf:
            placeholders = ",".join("?" for _ in names_cf)
            sql += f" AND lower(system_name) IN ({placeholders})"
            params.extend(sorted(names_cf))
        sql += " GROUP BY lower(system_name) ORDER BY MAX(event_ts) DESC LIMIT ?"
        params.append(max_rows)

        with player_local_db.playerdb_connection(path=self.db_path, ensure_schema=True) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        out: dict[str, dict[str, Any]] = {}
        now = datetime.now(timezone.utc)
        for row in rows:
            system_name = _as_text(row["system_name"])
            if not system_name:
                continue
            last_action_ts = _as_text(row["last_action_ts"])
            if max_age is not None:
                dt = _parse_iso_ts(last_action_ts)
                if dt is None or (now - dt) > max_age:
                    continue
            out[system_name.casefold()] = {
                "system_name": system_name,
                "has_exobio": bool(int(row["has_exobio"] or 0)),
                "has_exploration": bool(int(row["has_exploration"] or 0)),
                "has_incident": False,
                "has_combat": False,
                "last_action_ts": last_action_ts,
                "source": "playerdb",
                "confidence": "observed",
            }

        return out, {
            "count": len(out),
            "time_range": _as_text(time_range) or "all",
            "freshness_filter": _as_text(freshness_filter) or "any",
            "supports_exobio": True,
            "supports_exploration": True,
            "supports_incidents": False,
            "supports_combat": False,
            "db_path": self.db_path,
        }
