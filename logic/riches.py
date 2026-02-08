# logic/riches.py
"""
Road to Riches – backend SPANSH.

Po D1/D3:
- cała komunikacja HTTP idzie przez logic.spansh_client.SpanshClient,
- brak lokalnych timeoutów / URL-i,
- błędy raportowane przez spansh_error (via klient) + powiedz(),
- payload zgodny z API /riches/route (max_results, max_distance).
"""

from __future__ import annotations

from typing import Any, List, Tuple

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
from logic import spansh_payloads
from logic.utils import powiedz
from logic.rows_normalizer import normalize_body_rows


def _parse_riches_result(result: Any) -> Tuple[List[str], List[dict]]:
    """
    Parser wyniku R2R.

    Wejscie:
        result - JSON z SPANSH (dict albo lista).

    Wyjscie:
        route   - lista nazw systemow (dla config.STATE["trasa"])
        rows    - lista wierszy do tabeli
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


def oblicz_rtr(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_scan: int,
    loop: bool,
    use_map: bool,
    avoid_tharg: bool,
    gui_ref: Any | None = None,
) -> Tuple[List[str], List[dict]]:
    """
    Główna funkcja API dla zakładki RICHES.

    Interfejs:
    - wejście: parametry z GUI,
    - wyjście: (trasa, szczegóły_dla_GUI)
    """
    start = (start or "").strip()
    cel = (cel or "").strip()

    powiedz(
        f"API: Road to Riches z {start} "
        f"(radius {radius}Ly, min {min_scan} Cr)...",
        gui_ref,
    )

    if not start:
        spansh_error("RICHES: brak systemu startowego.", gui_ref, context="riches")
        return [], []

    jump_range = resolve_planner_jump_range(jump_range, gui_ref=gui_ref, context="riches")

    payload = spansh_payloads.build_riches_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_value=min_scan,
        loop=loop,
        use_map=use_map,
        avoid_tharg=avoid_tharg,
    )

    result = client.route(
        mode="riches",
        payload=payload,
        referer="https://spansh.co.uk/riches",
        gui_ref=gui_ref,
    )

    route, rows = _parse_riches_result(result)
    if not route and not rows:
        spansh_error(
            "RICHES: SPANSH nie zwrócił wyników.",
            gui_ref,
            context="riches",
        )

    return route, rows
