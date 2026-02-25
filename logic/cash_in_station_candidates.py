from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from logic import player_local_db
from logic.spansh_client import client as spansh_client
from logic.utils.renata_log import log_event_throttled
from logic.utils.http_edsm import (
    edsm_nearby_systems,
    edsm_provider_resilience_snapshot,
    edsm_station_details_for_system,
)

_OFFLINE_INDEX_CACHE: dict[str, tuple[float, float, Any]] = {}


def _reset_offline_index_cache_for_tests() -> None:
    _OFFLINE_INDEX_CACHE.clear()


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return float(value)
        except Exception:
            return None
    text = _as_text(value).replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _normalize_type(value: Any) -> str:
    text = _as_text(value).lower()
    if not text:
        return "station"
    if "carrier" in text:
        return "fleet_carrier"
    if "outpost" in text:
        return "outpost"
    if "settlement" in text:
        return "settlement"
    return "station"


def _normalize_service_token(value: Any) -> str:
    raw = _as_text(value).casefold()
    return "".join(ch for ch in raw if ch.isalnum())


def _is_uc_service(value: Any) -> bool:
    token = _normalize_service_token(value)
    if not token:
        return False
    return "universalcartographics" in token or token == "cartographics"


def _is_vista_service(value: Any) -> bool:
    token = _normalize_service_token(value)
    if not token:
        return False
    return "vistagenomics" in token or token == "genomics"


def _extract_services(raw: Dict[str, Any]) -> Dict[str, bool]:
    has_uc = bool(
        raw.get("has_uc")
        or raw.get("hasUc")
        or raw.get("services.has_uc")
    )
    has_vista = bool(
        raw.get("has_vista")
        or raw.get("hasVista")
        or raw.get("services.has_vista")
    )

    services = raw.get("services")
    if isinstance(services, dict):
        has_uc = has_uc or bool(
            services.get("has_uc")
            or services.get("hasUc")
            or services.get("uc")
            or services.get("universal_cartographics")
            or services.get("universalCartographics")
        )
        has_vista = has_vista or bool(
            services.get("has_vista")
            or services.get("hasVista")
            or services.get("vista")
            or services.get("vista_genomics")
            or services.get("vistaGenomics")
        )
        for key, value in services.items():
            if value is True:
                has_uc = has_uc or _is_uc_service(key)
                has_vista = has_vista or _is_vista_service(key)
    elif isinstance(services, list):
        for service in services:
            has_uc = has_uc or _is_uc_service(service)
            has_vista = has_vista or _is_vista_service(service)

    for key in ("otherServices", "stationServices", "services_list", "service_list"):
        values = raw.get(key)
        if not isinstance(values, list):
            continue
        for service in values:
            has_uc = has_uc or _is_uc_service(service)
            has_vista = has_vista or _is_vista_service(service)

    return {
        "has_uc": bool(has_uc),
        "has_vista": bool(has_vista),
    }


def normalize_station_candidate(
    raw: Dict[str, Any] | str,
    *,
    default_system: str = "",
    source_hint: str = "",
    freshness_ts: str = "",
) -> Dict[str, Any] | None:
    if isinstance(raw, str):
        name = _as_text(raw)
        if not name:
            return None
        row: Dict[str, Any] = {"name": name}
    elif isinstance(raw, dict):
        row = dict(raw)
        name = _as_text(
            row.get("name")
            or row.get("station")
            or row.get("station_name")
            or row.get("stationName")
            or row.get("label")
        )
        if not name:
            return None
    else:
        return None

    system_name = _as_text(
        row.get("system_name")
        or row.get("systemName")
        or row.get("system")
        or row.get("starSystem")
        or default_system
    )
    candidate = {
        "name": name,
        "system_name": system_name or default_system or "unknown",
        "type": _normalize_type(
            row.get("type")
            or row.get("station_type")
            or row.get("stationType")
            or row.get("subType")
        ),
        "services": _extract_services(row),
        "distance_ly": _safe_optional_float(
            row.get("distance_ly")
            or row.get("distanceLy")
            or row.get("distance")
            or row.get("distance_from_system_ly")
        ),
        "distance_ls": _safe_optional_float(
            row.get("distance_ls")
            or row.get("distanceLs")
            or row.get("distance_to_arrival")
            or row.get("distanceToArrival")
        ),
        "source": _as_text(row.get("source") or row.get("provider") or source_hint).upper(),
        "freshness_ts": _as_text(
            row.get("freshness_ts")
            or row.get("freshnessTs")
            or row.get("updated_at")
            or row.get("updatedAt")
            or freshness_ts
        ),
    }
    return candidate


def _candidate_key(candidate: Dict[str, Any]) -> str:
    system_name = _as_text(candidate.get("system_name")).casefold()
    station_name = _as_text(candidate.get("name")).casefold()
    return f"{system_name}::{station_name}"


def _candidate_score(candidate: Dict[str, Any]) -> int:
    score = 0
    if _as_text(candidate.get("name")):
        score += 2
    if _as_text(candidate.get("system_name")):
        score += 2
    if _as_text(candidate.get("source")):
        score += 1
    services = candidate.get("services") or {}
    if bool(services.get("has_uc")):
        score += 2
    if bool(services.get("has_vista")):
        score += 2
    if candidate.get("distance_ly") is not None:
        score += 1
    if candidate.get("distance_ls") is not None:
        score += 1
    return score


def _merge_sources(left: str, right: str) -> str:
    l = _as_text(left).upper()
    r = _as_text(right).upper()
    if l and r and l != r:
        parts = sorted(set([l, r]))
        return "+".join(parts)
    return l or r


def _merge_candidate_pair(current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(current)
    if _candidate_score(incoming) > _candidate_score(current):
        out = dict(incoming)
        base = current
    else:
        base = incoming

    out["source"] = _merge_sources(out.get("source"), base.get("source"))

    out_services = dict(out.get("services") or {})
    base_services = dict(base.get("services") or {})
    out_services["has_uc"] = bool(out_services.get("has_uc") or base_services.get("has_uc"))
    out_services["has_vista"] = bool(out_services.get("has_vista") or base_services.get("has_vista"))
    out["services"] = out_services

    for key in ("distance_ly", "distance_ls"):
        if out.get(key) is None and base.get(key) is not None:
            out[key] = base.get(key)
        elif out.get(key) is not None and base.get(key) is not None:
            try:
                out[key] = min(float(out.get(key)), float(base.get(key)))
            except Exception:
                log_event_throttled(
                    "cash_in_candidates_merge_distance_parse",
                    30.0,
                    "WARN",
                    "cash-in candidates: distance merge parse fallback",
                    field=key,
                    out_value=out.get(key),
                    base_value=base.get(key),
                    out_name=_as_text(out.get("name")),
                    out_system=_as_text(out.get("system_name")),
                )

    if not _as_text(out.get("freshness_ts")) and _as_text(base.get("freshness_ts")):
        out["freshness_ts"] = _as_text(base.get("freshness_ts"))
    return out


def merge_station_candidates(
    candidates: Iterable[Dict[str, Any]],
    *,
    limit: int = 24,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = _candidate_key(item)
        if not key or key == "::":
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(item)
        else:
            merged[key] = _merge_candidate_pair(existing, item)

    rows = list(merged.values())

    def _sort_key(row: Dict[str, Any]) -> tuple[float, float, str]:
        dist_ly = row.get("distance_ly")
        dist_ls = row.get("distance_ls")
        ly = float(dist_ly) if dist_ly is not None else 1e18
        ls = float(dist_ls) if dist_ls is not None else 1e18
        return (ly, ls, _as_text(row.get("name")).casefold())

    rows.sort(key=_sort_key)
    if limit > 0:
        rows = rows[:limit]
    return rows


def build_station_candidates(
    raw_candidates: Iterable[Dict[str, Any] | str],
    *,
    default_system: str = "",
    source_hint: str = "",
    freshness_ts: str = "",
    limit: int = 24,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in raw_candidates:
        row = normalize_station_candidate(
            raw,
            default_system=default_system,
            source_hint=source_hint,
            freshness_ts=freshness_ts,
        )
        if row is None:
            continue
        normalized.append(row)
    return merge_station_candidates(normalized, limit=limit)


def station_candidates_for_system_from_providers(
    system_name: str,
    *,
    include_edsm: bool = True,
    include_spansh: bool = True,
    freshness_ts: str = "",
    limit: int = 24,
) -> List[Dict[str, Any]]:
    system = _as_text(system_name)
    if not system:
        return []

    rows: List[Dict[str, Any] | str] = []
    if include_edsm:
        try:
            rows.extend(edsm_station_details_for_system(system) or [])
        except Exception:
            log_event_throttled(
                "cashin.providers.edsm_station_details",
                5000,
                "CASHIN",
                "EDSM station details provider failed",
                system=system,
            )
    if include_spansh:
        try:
            rows.extend(spansh_client.stations_for_system_details(system) or [])
        except Exception:
            log_event_throttled(
                "cashin.providers.spansh_station_details",
                5000,
                "CASHIN",
                "Spansh station details provider failed",
                system=system,
            )
    return build_station_candidates(
        rows,
        default_system=system,
        freshness_ts=freshness_ts,
        limit=limit,
    )


def station_candidates_cross_system_from_providers(
    origin_system: str,
    *,
    service: str = "",
    include_edsm: bool = True,
    include_spansh: bool = True,
    radius_ly: float = 120.0,
    max_systems: int = 12,
    origin_coords: list[float] | tuple[float, float, float] | None = None,
    freshness_ts: str = "",
    limit: int = 24,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Cross-system discovery:
    - znajduje sasiednie systemy (origin-centered),
    - pobiera szczegoly stacji per system,
    - zwraca zunifikowane `StationCandidate` gotowe do rankingu.
    """
    origin = _as_text(origin_system)
    svc = _as_text(service).lower()
    if not origin or max_systems <= 0:
        return [], {
            "systems_requested": 0,
            "systems_with_candidates": 0,
            "service": svc or "any",
            "radius_ly": float(radius_ly or 120.0),
        }

    nearby_rows: list[dict[str, Any]] = []
    nearby_requested_radius_ly = float(radius_ly or 120.0)
    nearby_effective_radius_ly = nearby_requested_radius_ly
    nearby_provider_response_count = 0
    nearby_reason = ""
    if include_edsm:
        try:
            nearby_rows = [
                dict(item)
                for item in edsm_nearby_systems(
                    origin,
                    radius_ly=float(radius_ly or 120.0),
                    limit=max(1, int(max_systems)),
                    origin_coords=origin_coords,
                )
                if isinstance(item, dict)
            ]
            snap = dict(edsm_provider_resilience_snapshot() or {})
            endpoint = dict((snap.get("endpoints") or {}).get("nearby_systems") or {})
            nearby_requested_radius_ly = float(
                endpoint.get("last_requested_radius_ly") or float(radius_ly or 120.0)
            )
            nearby_effective_radius_ly = float(
                endpoint.get("last_effective_radius_ly") or nearby_requested_radius_ly
            )
            nearby_provider_response_count = int(
                endpoint.get("last_provider_response_count") or len(nearby_rows)
            )
            if nearby_requested_radius_ly > nearby_effective_radius_ly:
                nearby_reason = "provider_radius_cap"
            elif nearby_effective_radius_ly >= 100.0 and nearby_provider_response_count == 0:
                nearby_reason = "provider_empty"
        except Exception:
            log_event_throttled(
                "cashin.providers.edsm_nearby",
                5000,
                "CASHIN",
                "EDSM nearby systems provider failed",
                origin=origin,
                radius_ly=radius_ly,
                max_systems=max_systems,
            )
            nearby_rows = []

    systems: list[dict[str, Any]] = []
    seen_systems: set[str] = set()
    origin_key = origin.casefold()
    for item in nearby_rows:
        system_name = _as_text(
            item.get("name")
            or item.get("system_name")
            or item.get("system")
            or item.get("systemName")
        )
        if not system_name:
            continue
        key = system_name.casefold()
        if key == origin_key or key in seen_systems:
            continue
        seen_systems.add(key)
        systems.append(
            {
                "system_name": system_name,
                "distance_ly": _safe_optional_float(
                    item.get("distance_ly")
                    or item.get("distanceLy")
                    or item.get("distance")
                ),
            }
        )
        if len(systems) >= max(1, int(max_systems)):
            break

    aggregate: list[dict[str, Any]] = []
    systems_with_candidates = 0
    for row in systems:
        system_name = _as_text(row.get("system_name"))
        if not system_name:
            continue
        per_system = station_candidates_for_system_from_providers(
            system_name,
            include_edsm=include_edsm,
            include_spansh=include_spansh,
            freshness_ts=freshness_ts,
            limit=max(8, int(limit or 24)),
        )
        if svc in {"uc", "vista"}:
            per_system = filter_candidates_by_service(per_system, service=svc)
        if not per_system:
            continue
        systems_with_candidates += 1
        origin_distance = _safe_optional_float(row.get("distance_ly"))
        for candidate in per_system:
            if not isinstance(candidate, dict):
                continue
            out = dict(candidate)
            out.setdefault("origin_system_name", origin)
            if origin_distance is not None:
                out["origin_distance_ly"] = origin_distance
                current_distance = _safe_optional_float(out.get("distance_ly"))
                if current_distance is None:
                    out["distance_ly"] = float(origin_distance)
                else:
                    out["distance_ly"] = min(float(current_distance), float(origin_distance))
            aggregate.append(out)
        if limit > 0 and len(aggregate) >= (int(limit) * 3):
            break

    candidates = merge_station_candidates(aggregate, limit=limit)
    meta = {
        "systems_requested": len(systems),
        "systems_with_candidates": systems_with_candidates,
        "service": svc or "any",
        "radius_ly": float(radius_ly or 120.0),
        "origin_coords_used": bool(origin_coords),
        "nearby_requested_radius_ly": float(nearby_requested_radius_ly),
        "nearby_effective_radius_ly": float(nearby_effective_radius_ly),
        "nearby_provider_response_count": int(nearby_provider_response_count),
        "nearby_reason": nearby_reason,
    }
    return candidates, meta


def station_candidates_from_playerdb(
    origin_system: str,
    *,
    service: str = "",
    origin_coords: list[float] | tuple[float, float, float] | None = None,
    limit: int = 24,
    db_path: str | None = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Shared provider for Cash-In / Personal Map over local SQLite playerdb.
    Returns StationCandidate-like rows + provider meta.
    """
    system = _as_text(origin_system)
    svc = _as_text(service).lower() or "uc"
    max_rows = max(1, int(limit or 24))
    resolved_db_path = db_path or player_local_db.default_playerdb_path()
    if not os.path.isfile(resolved_db_path):
        return [], {
            "lookup_status": "playerdb_not_found",
            "db_path": resolved_db_path,
            "service": svc,
            "count": 0,
            "query_mode": "none",
            "origin_coords_used": bool(origin_coords),
            "origin_coords_from_playerdb": False,
            "coords_missing_count": 0,
        }
    try:
        rows, meta = player_local_db.query_nearest_station_candidates(
            path=resolved_db_path,
            origin_system_name=system or None,
            origin_coords=origin_coords,
            service=svc,
            limit=max_rows,
        )
    except Exception as exc:
        log_event_throttled(
            "cashin.playerdb.query_nearest",
            5000,
            "CASHIN",
            "PlayerDB nearest station query failed",
            system=system,
            service=svc,
            db_path=resolved_db_path,
            error=f"{type(exc).__name__}: {exc}",
        )
        return [], {
            "lookup_status": "playerdb_error",
            "db_path": resolved_db_path,
            "service": svc,
            "count": 0,
            "query_mode": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "origin_coords_used": bool(origin_coords),
            "origin_coords_from_playerdb": False,
            "coords_missing_count": 0,
        }

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("source", "PLAYERDB")
        item.setdefault("freshness_ts", _as_text(item.get("services_freshness_ts") or item.get("station_last_seen_ts")))
        candidates.append(item)

    out_meta = {
        "lookup_status": "playerdb" if candidates else "playerdb_empty",
        "db_path": resolved_db_path,
        "service": svc,
        "count": len(candidates),
        "query_mode": _as_text(meta.get("query_mode")) or "none",
        "origin_coords_used": bool(meta.get("origin_coords_used")),
        "origin_coords_from_playerdb": bool(meta.get("origin_coords_from_playerdb")),
        "coords_missing_count": int(meta.get("coords_missing_count") or 0),
    }
    return candidates, out_meta


def _safe_coords_triplet(value: Any) -> tuple[float, float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (float(value[0]), float(value[1]), float(value[2]))
        except Exception:
            return None
    if isinstance(value, dict):
        x = _safe_optional_float(value.get("x"))
        y = _safe_optional_float(value.get("y"))
        z = _safe_optional_float(value.get("z"))
        if x is None or y is None or z is None:
            return None
        return (float(x), float(y), float(z))
    return None


def _distance_ly_between_coords(
    origin_coords: tuple[float, float, float] | None,
    target_coords: tuple[float, float, float] | None,
) -> float | None:
    if origin_coords is None or target_coords is None:
        return None
    try:
        dx = float(origin_coords[0]) - float(target_coords[0])
        dy = float(origin_coords[1]) - float(target_coords[1])
        dz = float(origin_coords[2]) - float(target_coords[2])
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    except Exception:
        return None


def _to_iso_date(value: Any) -> str:
    text = _as_text(value)
    if not text:
        return ""
    try:
        if len(text) == 10 and text.count("-") == 2:
            datetime.strptime(text, "%Y-%m-%d")
            return text
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        return ""


def _index_age_days(index_date: str) -> int:
    text = _as_text(index_date)
    if not text:
        return -1
    try:
        dt = datetime.strptime(text, "%Y-%m-%d")
        now = datetime.now(timezone.utc).date()
        delta = now - dt.date()
        return max(0, int(delta.days))
    except Exception:
        return -1


def _load_offline_index_payload(index_path: str) -> tuple[Any | None, str]:
    path = _as_text(index_path)
    if not path:
        return None, "path_missing"
    if not os.path.isfile(path):
        return None, "missing_file"
    try:
        mtime = float(os.path.getmtime(path))
    except Exception:
        mtime = 0.0

    cached = _OFFLINE_INDEX_CACHE.get(path)
    if isinstance(cached, tuple) and len(cached) == 3:
        cached_mtime, _cached_loaded_at, cached_payload = cached
        if abs(float(cached_mtime) - mtime) < 1e-9:
            return cached_payload, "ok_cache"

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None, "load_error"

    _OFFLINE_INDEX_CACHE[path] = (mtime, time.monotonic(), payload)
    return payload, "ok"


def _extract_offline_index_station_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("stations", "station_index", "items", "records", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _extract_offline_index_system_coords(payload: Any) -> dict[str, tuple[float, float, float]]:
    out: dict[str, tuple[float, float, float]] = {}
    if not isinstance(payload, dict):
        return out

    systems_map = payload.get("systems")
    if isinstance(systems_map, dict):
        for system_name, coords in systems_map.items():
            key = _as_text(system_name).casefold()
            if not key:
                continue
            triplet = _safe_coords_triplet(coords)
            if triplet is not None:
                out[key] = triplet

    systems_rows = payload.get("systems_rows")
    if isinstance(systems_rows, list):
        for row in systems_rows:
            if not isinstance(row, dict):
                continue
            name = _as_text(
                row.get("name")
                or row.get("system_name")
                or row.get("system")
            )
            if not name:
                continue
            triplet = _safe_coords_triplet(
                row.get("coords")
                or {
                    "x": row.get("x"),
                    "y": row.get("y"),
                    "z": row.get("z"),
                }
            )
            if triplet is not None:
                out[name.casefold()] = triplet
    return out


def _candidate_coords_from_offline_index(
    row: dict[str, Any],
    *,
    system_coords_map: dict[str, tuple[float, float, float]],
    system_name: str,
) -> tuple[float, float, float] | None:
    for key in ("coords", "system_coords", "star_pos", "starPos"):
        triplet = _safe_coords_triplet(row.get(key))
        if triplet is not None:
            return triplet

    direct_triplet = _safe_coords_triplet(
        {
            "x": row.get("x"),
            "y": row.get("y"),
            "z": row.get("z"),
        }
    )
    if direct_triplet is not None:
        return direct_triplet

    if system_name:
        return system_coords_map.get(system_name.casefold())
    return None


def _resolve_offline_index_date(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    meta = payload.get("meta")
    if isinstance(meta, dict):
        for key in ("index_date", "date", "snapshot_date", "built_at"):
            date_text = _to_iso_date(meta.get(key))
            if date_text:
                return date_text
    for key in ("index_date", "date", "snapshot_date", "built_at"):
        date_text = _to_iso_date(payload.get(key))
        if date_text:
            return date_text
    return ""


def station_candidates_from_offline_index(
    origin_system: str,
    *,
    service: str,
    origin_coords: list[float] | tuple[float, float, float] | None,
    index_path: str,
    freshness_ts: str = "",
    limit: int = 24,
    non_carrier_only: bool = True,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    origin = _as_text(origin_system)
    svc = _as_text(service).lower()
    path = _as_text(index_path)
    index_payload, load_status = _load_offline_index_payload(path)
    index_date = _resolve_offline_index_date(index_payload)
    index_age_days = _index_age_days(index_date)
    origin_triplet = _safe_coords_triplet(origin_coords)

    meta: Dict[str, Any] = {
        "lookup_status": "not_attempted",
        "source": "offline_index",
        "index_path": path,
        "index_date": index_date,
        "index_age_days": index_age_days,
        "rows_total": 0,
        "rows_service_match": 0,
        "rows_coords_match": 0,
        "ignored_carriers": 0,
        "load_status": load_status,
        "origin_coords_used": origin_triplet is not None,
        "service": svc or "any",
    }
    if load_status not in {"ok", "ok_cache"}:
        meta["lookup_status"] = load_status
        return [], meta
    if origin_triplet is None:
        meta["lookup_status"] = "no_origin_coords"
        return [], meta

    rows = _extract_offline_index_station_rows(index_payload)
    system_coords_map = _extract_offline_index_system_coords(index_payload)
    meta["rows_total"] = len(rows)

    candidates_raw: list[dict[str, Any]] = []
    for item in rows:
        row = dict(item)
        name = _as_text(
            row.get("name")
            or row.get("station")
            or row.get("station_name")
            or row.get("stationName")
        )
        system_name = _as_text(
            row.get("system_name")
            or row.get("systemName")
            or row.get("system")
            or row.get("starSystem")
            or origin
        )
        if not name or not system_name:
            continue

        station_type = _normalize_type(
            row.get("type")
            or row.get("station_type")
            or row.get("stationType")
        )
        if non_carrier_only and station_type == "fleet_carrier":
            meta["ignored_carriers"] = int(meta.get("ignored_carriers") or 0) + 1
            continue

        services = _extract_services(row)
        has_uc = bool(services.get("has_uc"))
        has_vista = bool(services.get("has_vista"))
        if svc == "uc" and not has_uc:
            continue
        if svc == "vista" and not has_vista:
            continue
        if svc not in {"uc", "vista"} and not (has_uc or has_vista):
            continue
        meta["rows_service_match"] = int(meta.get("rows_service_match") or 0) + 1

        coords = _candidate_coords_from_offline_index(
            row,
            system_coords_map=system_coords_map,
            system_name=system_name,
        )
        if coords is None:
            continue
        dist_ly = _distance_ly_between_coords(origin_triplet, coords)
        if dist_ly is None:
            continue
        meta["rows_coords_match"] = int(meta.get("rows_coords_match") or 0) + 1

        candidates_raw.append(
            {
                "name": name,
                "system_name": system_name,
                "type": station_type,
                "services": {
                    "has_uc": has_uc,
                    "has_vista": has_vista,
                },
                "distance_ly": float(dist_ly),
                "distance_ls": _safe_optional_float(
                    row.get("distance_ls")
                    or row.get("distanceToArrival")
                ),
                "source": "OFFLINE_INDEX",
                "freshness_ts": _as_text(
                    row.get("freshness_ts")
                    or row.get("updated_at")
                    or row.get("updatedAt")
                    or index_date
                    or freshness_ts
                ),
            }
        )

    candidates = build_station_candidates(
        candidates_raw,
        default_system=origin,
        source_hint="OFFLINE_INDEX",
        freshness_ts=index_date or freshness_ts,
        limit=limit,
    )
    meta["lookup_status"] = "offline_index" if candidates else "no_offline_index_hit"
    return candidates, meta


def filter_candidates_by_service(
    candidates: Iterable[Dict[str, Any]],
    *,
    service: str,
) -> List[Dict[str, Any]]:
    svc = _as_text(service).lower()
    if svc not in {"uc", "vista"}:
        return [dict(item) for item in candidates if isinstance(item, dict)]
    key = "has_uc" if svc == "uc" else "has_vista"
    return [
        dict(item)
        for item in candidates
        if isinstance(item, dict) and bool((item.get("services") or {}).get(key))
    ]
