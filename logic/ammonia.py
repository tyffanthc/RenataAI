# logic/ammonia.py
"""
Ammonia Worlds – backend SPANSH.

Po D1/D3:
- używa centralnego SpanshClient.route(mode=\"ammonia\"),
- payload zgodny z R2R, ale z filtrem na światy amoniakowe,
- max_results / max_distance zamiast starych nazw.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
from logic import spansh_payloads
from logic.utils import powiedz
from logic.rows_normalizer import normalize_body_rows


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

    payload = spansh_payloads.build_ammonia_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_value=1,
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
