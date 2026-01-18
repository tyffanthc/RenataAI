from __future__ import annotations

from typing import Any, Iterable, Tuple


def pick_value(entry: dict, keys: Iterable[str]) -> Any:
    for key in keys:
        val = entry.get(key)
        if isinstance(val, dict):
            for nested_key in ("value", "distance", "remaining", "ly", "ls"):
                nested_val = val.get(nested_key)
                if nested_val is not None and nested_val != "":
                    return nested_val
        if val is not None and val != "":
            return val
    return None


def is_terraformable(body: dict) -> bool:
    for key in ("terraformable", "is_terraformable"):
        val = body.get(key)
        if isinstance(val, bool):
            return val
    terra_state = body.get("terraforming_state") or body.get("terraform_state") or ""
    if isinstance(terra_state, str):
        return "terraform" in terra_state.lower()
    return False


def normalize_body_rows(
    result: Any,
    *,
    system_keys: Iterable[str],
    bodies_keys: Iterable[str],
    body_name_keys: Iterable[str],
    subtype_keys: Iterable[str],
    distance_keys: Iterable[str],
    scan_value_keys: Iterable[str],
    map_value_keys: Iterable[str],
    jumps_keys: Iterable[str],
) -> Tuple[list[str], list[dict]]:
    route: list[str] = []
    rows: list[dict] = []

    if not result:
        return route, rows

    if isinstance(result, dict):
        segments = (
            result.get("route")
            or result.get("systems")
            or result.get("result")
            or []
        )
    else:
        segments = result

    for seg in segments or []:
        if isinstance(seg, dict):
            system_name = pick_value(seg, system_keys)
            bodies_raw = pick_value(seg, bodies_keys) or []
        else:
            system_name = str(seg)
            bodies_raw = []

        if not system_name:
            continue

        route.append(system_name)
        jumps_val = pick_value(seg, jumps_keys) if isinstance(seg, dict) else None

        if not bodies_raw:
            rows.append(
                {
                    "system_name": system_name,
                    "body_name": None,
                    "subtype": None,
                    "terraformable": None,
                    "distance_ls": None,
                    "value_scan": None,
                    "value_map": None,
                    "jumps": jumps_val,
                    "done": False,
                }
            )
            continue

        for body in bodies_raw:
            if isinstance(body, dict):
                rows.append(
                    {
                        "system_name": system_name,
                        "body_name": pick_value(body, body_name_keys) or "???",
                        "subtype": pick_value(body, subtype_keys),
                        "terraformable": is_terraformable(body),
                        "distance_ls": pick_value(body, distance_keys),
                        "value_scan": pick_value(body, scan_value_keys),
                        "value_map": pick_value(body, map_value_keys),
                        "jumps": jumps_val,
                        "done": False,
                    }
                )
            else:
                rows.append(
                    {
                        "system_name": system_name,
                        "body_name": str(body),
                        "subtype": None,
                        "terraformable": None,
                        "distance_ls": None,
                        "value_scan": None,
                        "value_map": None,
                        "jumps": jumps_val,
                        "done": False,
                    }
                )

    return route, rows


def normalize_trade_rows(result: Any) -> Tuple[list[str], list[dict]]:
    route: list[str] = []
    rows: list[dict] = []

    if not result:
        return route, rows

    core = result
    if isinstance(result, dict):
        core = (
            result.get("result")
            or result.get("routes")
            or result.get("legs")
            or result.get("hops")
            or result
        )

    if not isinstance(core, list):
        return route, rows

    for leg in core:
        if not isinstance(leg, dict):
            continue
        from_sys = pick_value(leg, ("from_system", "from", "source_system"))
        to_sys = pick_value(leg, ("to_system", "to", "destination_system"))
        commodity = pick_value(leg, ("commodity", "item", "name"))
        profit = pick_value(leg, ("profit", "estimated_profit"))
        profit_per_ton = pick_value(leg, ("profit_per_tonne", "profit_per_ton"))
        jumps = pick_value(leg, ("jumps", "jump_count"))

        if from_sys:
            route.append(str(from_sys))
        if to_sys:
            route.append(str(to_sys))

        rows.append(
            {
                "from_system": from_sys,
                "to_system": to_sys,
                "commodity": commodity,
                "profit": profit,
                "profit_per_ton": profit_per_ton,
                "jumps": jumps,
            }
        )

    return route, rows


def normalize_neutron_rows(details: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for entry in details or []:
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "system_name": entry.get("system"),
                "distance_ly": entry.get("distance"),
                "remaining_ly": entry.get("remaining"),
                "neutron": entry.get("neutron"),
                "jumps": entry.get("jumps"),
            }
        )
    return rows
