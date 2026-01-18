"""
Earth-like Worlds – backend SPANSH.

Po D1/D3:
- używa SpanshClient.route(mode="riches"),
- payload na bazie R2R (max_results, max_distance),
- filtr na Earth-like Worlds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
from logic import spansh_payloads
from logic.utils import powiedz
from logic.rows_normalizer import normalize_body_rows


def _build_payload(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_scan: int,
    loop: bool,
    avoid_tharg: bool,
) -> Dict[str, Any]:
    """
    Payload dla SPANSH /riches/route z filtrem Earth-like world.
    """
    start = (start or "").strip()
    cel = (cel or "").strip()

    payload: Dict[str, Any] = {
        "from": start,
        "to": cel or None,
        "range": float(jump_range) if jump_range is not None else None,
        "radius": float(radius) if radius is not None else None,
        "max_results": int(max_sys) if max_sys is not None else None,
        "max_distance": int(max_dist) if max_dist is not None else None,
        "min_value": int(min_scan) if min_scan is not None else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
        "body_types": "Earth-like world",
    }

    # Usuwamy None, żeby np. puste "to" nie szło jako null.
    return {k: v for k, v in payload.items() if v is not None}


def _parse_elw_result(result: Any) -> Tuple[List[str], List[dict]]:
    """
    Parser wyniku ELW.
    """
    return normalize_body_rows(
        result,
        system_keys=("system", "name", "star_system"),
        bodies_keys=("bodies", "planets"),
        body_name_keys=("name", "body", "body_name"),
        subtype_keys=("subtype", "type"),
        distance_keys=("distance", "distance_ls", "distance_to_arrival", "distance_to_arrival_ls"),
        scan_value_keys=("value", "estimated_value", "scan_value", "estimated_scan_value"),
        map_value_keys=("mapping_value", "mapped_value", "estimated_mapping_value"),
        jumps_keys=("jumps", "jump_count", "jumps_remaining"),
    )


def oblicz_elw(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    loop: bool,
    avoid_tharg: bool,
    gui_ref: Any | None = None,
) -> Tuple[List[str], List[dict]]:
    """
    API dla zakładki Earth-like Worlds.

    Uwaga: sygnatura dopasowana do GUI (bez min_scan),
    minimalna wartość skanu ustawiana wewnętrznie.
    """
    # prosty próg minimalnej wartości – 1 Cr
    min_scan = 1

    start = (start or "").strip()
    cel = (cel or "").strip()

    powiedz(
        f"API: Earth-like Worlds z {start} (radius {radius}Ly)...",
        gui_ref,
    )

    if not start:
        spansh_error("ELW: brak systemu startowego.", gui_ref, context="elw")
        return [], []

    jump_range = resolve_planner_jump_range(jump_range, gui_ref=gui_ref, context="elw")

    payload = spansh_payloads.build_elw_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_value=min_scan,
        loop=loop,
        avoid_tharg=avoid_tharg,
    )

    result = client.route(
        mode="riches",
        payload=payload,
        referer="https://spansh.co.uk/elw",
        gui_ref=gui_ref,
    )

    route, rows = _parse_elw_result(result)
    if not route and not rows:
        spansh_error(
            "ELW: SPANSH nie zwrócił wyników.",
            gui_ref,
            context="elw",
        )

    return route, rows
