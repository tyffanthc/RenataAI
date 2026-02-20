from __future__ import annotations

from typing import Any, Dict, Iterable, List

from logic.spansh_client import client as spansh_client
from logic.utils.http_edsm import edsm_nearby_systems, edsm_station_details_for_system


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
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
                pass

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
            pass
    if include_spansh:
        try:
            rows.extend(spansh_client.stations_for_system_details(system) or [])
        except Exception:
            pass
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
        except Exception:
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
    }
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
