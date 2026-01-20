from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

import config


FormField = Tuple[str, str]


@dataclass(frozen=True)
class SpanshPayload:
    endpoint_path: str
    form_fields: List[FormField]


def bool01(value: Any) -> str:
    return "1" if bool(value) else "0"


def as_str_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return bool01(value)
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return str(number)
    except Exception:
        return str(value)


def _add_field(fields: List[FormField], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return
        fields.append((key, value))
        return
    fields.append((key, as_str_number(value)))


def _add_multi_field(fields: List[FormField], key: str, values: Any) -> None:
    if values is None:
        return
    for item in values:
        if item is None:
            continue
        if isinstance(item, str):
            item = item.strip()
        if not item:
            continue
        fields.append((key, str(item)))


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
    supercharge_mode: str | None = None,
    via: List[str] | None = None,
    app_state: Any | None = None,
    ship_state: Any | None = None,
) -> SpanshPayload:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    fields: List[FormField] = []

    _add_field(fields, "from", start_value)
    _add_field(fields, "to", (cel or "").strip())
    _add_field(fields, "range", as_str_number(range_value) if range_value is not None else None)
    _add_field(fields, "efficiency", as_str_number(eff))

    if config.get("features.spansh.neutron_overcharge_enabled", True):
        mode = (supercharge_mode or "normal").strip().lower()
        multiplier = "6" if mode in ("overcharge", "overcharged", "6") else "4"
        _add_field(fields, "supercharge_multiplier", multiplier)

    if config.get("features.spansh.neutron_via_enabled", True):
        _add_multi_field(fields, "via", via or [])

    return SpanshPayload(endpoint_path="/route", form_fields=fields)


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
) -> SpanshPayload:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    fields: List[FormField] = []

    _add_field(fields, "from", start_value)
    _add_field(fields, "to", (cel or "").strip())
    _add_field(fields, "range", as_str_number(range_value) if range_value is not None else None)
    _add_field(fields, "radius", as_str_number(radius))
    _add_field(fields, "max_results", as_str_number(max_sys))
    _add_field(fields, "max_distance", as_str_number(max_dist))
    _add_field(fields, "min_value", as_str_number(min_value))
    _add_field(fields, "use_mapping_value", bool01(use_map))
    _add_field(fields, "avoid_thargoids", bool01(avoid_tharg))
    _add_field(fields, "loop", bool01(loop))

    return SpanshPayload(endpoint_path="/riches/route", form_fields=fields)


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
) -> SpanshPayload:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    fields: List[FormField] = []

    _add_field(fields, "from", start_value)
    _add_field(fields, "to", (cel or "").strip())
    _add_field(fields, "range", as_str_number(range_value) if range_value is not None else None)
    _add_field(fields, "radius", as_str_number(radius))
    _add_field(fields, "max_results", as_str_number(max_sys))
    _add_field(fields, "max_distance", as_str_number(max_dist))
    _add_field(fields, "min_value", "1")
    _add_field(fields, "loop", bool01(loop))
    _add_field(fields, "avoid_thargoids", bool01(avoid_tharg))
    _add_field(fields, "body_types", "Ammonia world")

    return SpanshPayload(endpoint_path="/riches/route", form_fields=fields)


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
) -> SpanshPayload:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    fields: List[FormField] = []

    _add_field(fields, "from", start_value)
    _add_field(fields, "to", (cel or "").strip())
    _add_field(fields, "range", as_str_number(range_value) if range_value is not None else None)
    _add_field(fields, "radius", as_str_number(radius))
    _add_field(fields, "max_results", as_str_number(max_sys))
    _add_field(fields, "max_distance", as_str_number(max_dist))
    _add_field(fields, "min_value", "1")
    _add_field(fields, "loop", bool01(loop))
    _add_field(fields, "avoid_thargoids", bool01(avoid_tharg))
    _add_field(fields, "body_types", "Earth-like world")

    return SpanshPayload(endpoint_path="/riches/route", form_fields=fields)


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
) -> SpanshPayload:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    fields: List[FormField] = []

    _add_field(fields, "from", start_value)
    _add_field(fields, "to", (cel or "").strip())
    _add_field(fields, "range", as_str_number(range_value) if range_value is not None else None)
    _add_field(fields, "radius", as_str_number(radius))
    _add_field(fields, "max_results", as_str_number(max_sys))
    _add_field(fields, "max_distance", as_str_number(max_dist))
    _add_field(fields, "min_value", "1")
    _add_field(fields, "loop", bool01(loop))
    _add_field(fields, "avoid_thargoids", bool01(avoid_tharg))
    _add_multi_field(fields, "body_types", ["Rocky body", "High metal content world"])

    return SpanshPayload(endpoint_path="/riches/route", form_fields=fields)


def build_exomastery_payload(
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
) -> SpanshPayload:
    start_value = _resolve_start(start, app_state)
    range_value = _resolve_range(jump_range, ship_state)
    fields: List[FormField] = []

    _add_field(fields, "from", start_value)
    _add_field(fields, "to", (cel or "").strip())
    _add_field(fields, "range", as_str_number(range_value) if range_value is not None else None)
    _add_field(fields, "radius", as_str_number(radius))
    _add_field(fields, "max_results", as_str_number(max_sys))
    _add_field(fields, "max_distance", as_str_number(max_dist))
    _add_field(fields, "min_value", as_str_number(min_value))
    _add_field(fields, "loop", bool01(loop))
    _add_field(fields, "avoid_thargoids", bool01(avoid_tharg))

    return SpanshPayload(endpoint_path="/exobiology/route", form_fields=fields)


def build_trade_payload(
    start_system: str,
    start_station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: float,
    flags: dict[str, Any],
    app_state: Any | None = None,
) -> SpanshPayload:
    system_value = _resolve_start(start_system, app_state)
    large_pad = bool(flags.get("large_pad"))
    planetary = bool(flags.get("planetary"))
    player_owned = bool(flags.get("player_owned"))
    restricted = bool(flags.get("restricted"))
    prohibited = bool(flags.get("prohibited"))
    avoid_loops = bool(flags.get("avoid_loops"))
    allow_permits = bool(flags.get("allow_permits"))

    fields: List[FormField] = []
    _add_field(fields, "system", system_value)
    _add_field(fields, "station", start_station)
    _add_field(fields, "starting_capital", as_str_number(capital))
    _add_field(fields, "max_hop_distance", as_str_number(max_hop))
    _add_field(fields, "max_cargo", as_str_number(cargo))
    _add_field(fields, "max_hops", as_str_number(max_hops))
    _add_field(fields, "max_system_distance", as_str_number(max_dta))
    if config.get("features.spansh.trade_market_age_enabled", True):
        _add_field(fields, "max_price_age", as_str_number(max_age))
    _add_field(fields, "requires_large_pad", bool01(large_pad))
    _add_field(fields, "allow_prohibited", bool01(prohibited))
    _add_field(fields, "allow_planetary", bool01(planetary))
    _add_field(fields, "allow_player_owned", bool01(player_owned))
    _add_field(fields, "allow_restricted_access", bool01(restricted))
    _add_field(fields, "unique", bool01(avoid_loops))
    _add_field(fields, "permit", bool01(allow_permits))

    return SpanshPayload(endpoint_path="/trade/route", form_fields=fields)
