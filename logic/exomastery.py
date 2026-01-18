# logic/exomastery.py
"""
Exomastery / Exobiology – backend SPANSH.

Po D1/D3:
- korzysta z SpanshClient.route (mode=\"exobiology\"),
- brak lokalnych timeoutów / URL-i,
- payload zgodny z /exobiology/route (max_results / max_distance),
- parser zwraca listę systemów + szczegóły do GUI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
from logic import spansh_payloads
from logic.utils import powiedz, MSG_QUEUE
import config
from logic.rows_normalizer import normalize_body_rows


def _build_payload(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_landmark_value: int,
    loop: bool,
    avoid_tharg: bool,
) -> Dict[str, Any]:
    """
    Payload dla SPANSH /exobiology/route (Exomastery).
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
        "min_value": int(min_landmark_value) if min_landmark_value is not None else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
    }

    return {k: v for k, v in payload.items() if v is not None}


def _parse_exomastery_result(result: Any) -> Tuple[List[str], List[dict]]:
    """
    Parser wyniku Exomastery.

    Zwraca:
        route   - lista systemow
        rows    - lista wierszy do tabeli
    """
    return normalize_body_rows(
        result,
        system_keys=("system", "name", "star_system"),
        bodies_keys=("landmarks", "bio"),
        body_name_keys=("body", "name", "body_name"),
        subtype_keys=("species", "type"),
        distance_keys=("distance", "distance_ls", "distance_to_arrival", "distance_to_arrival_ls"),
        scan_value_keys=("value", "estimated_value", "scan_value"),
        map_value_keys=("mapping_value", "mapped_value", "estimated_mapping_value"),
        jumps_keys=("jumps", "jump_count", "jumps_remaining"),
    )


def oblicz_exomastery(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    min_landmark_value: int,
    loop: bool,
    avoid_tharg: bool,
    gui_ref: Any | None = None,
) -> Tuple[List[str], List[dict]]:
    """
    API dla zakładki Exomastery.
    """
    start = (start or "").strip()
    cel = (cel or "").strip()

    powiedz(
        f"API: Exomastery z {start} (radius {radius}Ly, min {min_landmark_value} Cr)...",
        gui_ref,
    )

    if not start:
        spansh_error(
            "EXO: brak systemu startowego.",
            gui_ref,
            context="exomastery",
        )
        return [], []

    jump_range = resolve_planner_jump_range(
        jump_range, gui_ref=gui_ref, context="exomastery"
    )

    payload = spansh_payloads.build_exomastery_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_value=min_landmark_value,
        loop=loop,
        avoid_tharg=avoid_tharg,
    )
    if config.get("features.spansh.debug_payload", False):
        MSG_QUEUE.put(("log", f"[SPANSH EXOMASTERY PAYLOAD] {payload.form_fields}"))

    result = client.route(
        mode="exobiology",
        payload=payload,
        referer="https://spansh.co.uk/exobiology",
        gui_ref=gui_ref,
    )

    route, rows = _parse_exomastery_result(result)
    if not route and not rows:
        spansh_error(
            "EXO: SPANSH nie zwrócił wyników.",
            gui_ref,
            context="exomastery",
        )

    return route, rows
