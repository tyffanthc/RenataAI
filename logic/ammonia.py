# logic/ammonia.py
"""
Ammonia Worlds – backend SPANSH.

Po D1/D3:
- używa centralnego SpanshClient.route(mode=\"ammonia\"),
- payload zgodny z R2R, ale z filtrem na światy amoniakowe,
- max_results / max_distance zamiast starych nazw.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
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
    Payload dla SPANSH /ammonia/route.

    W praktyce Ammonia Worlds to Road to Riches z filtrem typu planety.
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
        # kluczowe: filtr światów amoniakowych
        "body_types": "Ammonia world",
    }

    return {k: v for k, v in payload.items() if v is not None}


def _parse_ammonia_result(result: Any) -> Tuple[List[str], List[dict]]:
    """
    Parser wyniku Ammonia Worlds.

    Struktura bardzo podobna do Road to Riches - system + lista planet.
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


def oblicz_ammonia(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_scan: int,
    loop: bool,
    avoid_tharg: bool,
    gui_ref: Any | None = None,
) -> Tuple[List[str], List[dict]]:
    """
    API dla zakładki Ammonia Worlds.
    """
    start = (start or "").strip()
    cel = (cel or "").strip()

    powiedz(
        f"API: Ammonia Worlds z {start} (radius {radius}Ly)...",
        gui_ref,
    )

    if not start:
        spansh_error(
            "AMMONIA: brak systemu startowego.",
            gui_ref,
            context="ammonia",
        )
        return [], []

    jump_range = resolve_planner_jump_range(jump_range, gui_ref=gui_ref, context="ammonia")

    payload = _build_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_scan=min_scan,
        loop=loop,
        avoid_tharg=avoid_tharg,
    )

    result = client.route(
        mode="riches",
        payload=payload,
        referer="https://spansh.co.uk/ammonia",
        gui_ref=gui_ref,
    )

    route, rows = _parse_ammonia_result(result)
    if not route and not rows:
        spansh_error(
            "AMMONIA: SPANSH nie zwrócił wyników.",
            gui_ref,
            context="ammonia",
        )

    return route, rows
