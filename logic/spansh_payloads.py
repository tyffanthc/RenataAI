# logic/spansh_payloads.py
from __future__ import annotations

from typing import Any, Dict

import config


def _resolve_start(start: str | None, app_state: Any | None) -> str:
    start_value = (start or "").strip()
    if start_value:
        return start_value
    if app_state is not None:
        current = getattr(app_state, "current_system", "") or ""
        current = str(current).strip()
        if current:
            return current
    return ""


def _resolve_range(requested: Any, ship_state: Any | None) -> float | None:
    if not config.get("planner_auto_use_ship_jump_range", True):
        try:
            return float(requested) if requested is not None else None
        except Exception:
            return None

    if requested is not None and config.get("planner_allow_manual_range_override", True):
        try:
            return float(requested)
        except Exception:
            return None

    if ship_state is not None:
        jr = getattr(ship_state, "jump_range_current_ly", None)
    else:
        jr = None

    if jr is not None:
        try:
            return float(jr)
        except Exception:
            return None

    try:
        fallback = float(config.get("planner_fallback_range_ly", 30.0))
    except Exception:
        fallback = 30.0
    return fallback


def build_neutron_payload(
    start: str,
    cel: str,
    jump_range: float | None,
    eff: float,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> Dict[str, Any]:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    payload = {
        "efficiency": str(float(eff)),
        "range": str(float(range_value)) if range_value is not None else None,
        "from": start_value,
        "to": (cel or "").strip(),
    }
    return {k: v for k, v in payload.items() if v is not None}


def build_riches_payload(
    start: str,
    cel: str,
    jump_range: float | None,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_value: int,
    loop: bool,
    use_map: bool,
    avoid_tharg: bool,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> Dict[str, Any]:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    payload: Dict[str, Any] = {
        "from": start_value,
        "to": (cel or "").strip() or None,
        "range": float(range_value) if range_value is not None else None,
        "radius": float(radius) if radius is not None else None,
        "max_results": int(max_sys) if max_sys is not None else None,
        "max_distance": int(max_dist) if max_dist is not None else None,
        "min_value": int(min_value) if min_value is not None else None,
        "loop": bool(loop),
        "use_mapping_value": bool(use_map),
        "avoid_thargoids": bool(avoid_tharg),
    }
    return {k: v for k, v in payload.items() if v is not None}


def build_ammonia_payload(
    start: str,
    cel: str,
    jump_range: float | None,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_value: int,
    loop: bool,
    avoid_tharg: bool,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> Dict[str, Any]:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    payload: Dict[str, Any] = {
        "from": start_value,
        "to": (cel or "").strip() or None,
        "range": float(range_value) if range_value is not None else None,
        "radius": float(radius) if radius is not None else None,
        "max_results": int(max_sys) if max_sys is not None else None,
        "max_distance": int(max_dist) if max_dist is not None else None,
        "min_value": int(min_value) if min_value is not None else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
    }
    return {k: v for k, v in payload.items() if v is not None}


def build_elw_payload(
    start: str,
    cel: str,
    jump_range: float | None,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_value: int,
    loop: bool,
    avoid_tharg: bool,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> Dict[str, Any]:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    payload: Dict[str, Any] = {
        "from": start_value,
        "to": (cel or "").strip() or None,
        "range": float(range_value) if range_value is not None else None,
        "radius": float(radius) if radius is not None else None,
        "max_results": int(max_sys) if max_sys is not None else None,
        "max_distance": int(max_dist) if max_dist is not None else None,
        "min_value": int(min_value) if min_value is not None else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
        "body_types": "Earth-like world",
    }
    return {k: v for k, v in payload.items() if v is not None}


def build_hmc_payload(
    start: str,
    cel: str,
    jump_range: float | None,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_value: int,
    loop: bool,
    avoid_tharg: bool,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> Dict[str, Any]:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    payload: Dict[str, Any] = {
        "from": start_value,
        "to": (cel or "").strip() or None,
        "range": float(range_value) if range_value is not None else None,
        "radius": float(radius) if radius is not None else None,
        "max_results": int(max_sys) if max_sys is not None else None,
        "max_distance": int(max_dist) if max_dist is not None else None,
        "min_value": int(min_value) if min_value is not None else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
        "body_types": ["Rocky body", "High metal content world"],
    }
    return {k: v for k, v in payload.items() if v is not None}


def build_exomastery_payload(
    start: str,
    cel: str,
    jump_range: float | None,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_landmark_value: int,
    loop: bool,
    avoid_tharg: bool,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> Dict[str, Any]:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    payload: Dict[str, Any] = {
        "from": start_value,
        "to": (cel or "").strip() or None,
        "range": float(range_value) if range_value is not None else None,
        "radius": float(radius) if radius is not None else None,
        "max_results": int(max_sys) if max_sys is not None else None,
        "max_distance": int(max_dist) if max_dist is not None else None,
        "min_landmark_value": int(min_landmark_value)
        if min_landmark_value is not None
        else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
    }
    return {k: v for k, v in payload.items() if v is not None}


def build_trade_payload(
    start_system: str,
    start_station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: int,
    flags: Dict[str, Any],
    app_state: Any | None = None,
) -> Dict[str, Any]:
    system_value = _resolve_start(start_system, app_state)
    large_pad = bool(flags.get("large_pad"))
    planetary = bool(flags.get("planetary"))
    player_owned = bool(flags.get("player_owned"))
    restricted = bool(flags.get("restricted"))
    prohibited = bool(flags.get("prohibited"))
    avoid_loops = bool(flags.get("avoid_loops"))
    allow_permits = bool(flags.get("allow_permits"))

    payload: Dict[str, Any] = {
        "max_hops": int(max_hops),
        "max_hop_distance": float(max_hop),
        "system": system_value,
        "station": start_station,
        "starting_capital": int(capital),
        "max_cargo": int(cargo),
        "max_system_distance": int(max_dta),
        "requires_large_pad": int(large_pad),
        "allow_prohibited": int(prohibited),
        "allow_planetary": int(planetary),
        "allow_player_owned": int(player_owned),
        "allow_restricted_access": int(restricted),
        "unique": int(avoid_loops),
        "permit": int(allow_permits),
    }
    return payload
