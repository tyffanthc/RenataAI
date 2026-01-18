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

from typing import Any, Dict, List, Tuple

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
from logic.utils import powiedz


def _build_payload(
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
) -> Dict[str, Any]:
    """
    Buduje payload dla SPANSH /riches/route.
    Nazwy pól są dopasowane do semantyki R2R (2025):

    - from / to
    - range (LY)
    - radius (LY)
    - max_results          – liczba systemów w trasie
    - max_distance         – max odległość do lądowania (Ls)
    - min_value            – minimalna wartość skanu (Cr)
    - use_mapping_value    – czy liczyć mapped czy tylko odkrycie
    - loop                 – pętla
    - avoid_thargoids      – omijać systemy Thargoid
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
        "use_mapping_value": bool(use_map),
        "avoid_thargoids": bool(avoid_tharg),
    }

    if cel:
        payload["to"] = cel
    # wywal None, żeby nie wysyłać pustych kluczy
    return {k: v for k, v in payload.items() if v is not None}


def _parse_riches_result(result: Any) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Parser wyniku R2R.

    Wejście:
        result – JSON z SPANSH (dict albo lista).

    Wyjście:
        route   – lista nazw systemów (dla config.STATE["trasa"])
        details – dict: {system_name: [linie opisu do GUI]}
    """
    route: List[str] = []
    details: Dict[str, List[str]] = {}

    if not result:
        return route, details

    # Spansh najczęściej zwraca dict z kluczem "route" / "systems"
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
            system_name = (
                seg.get("system")
                or seg.get("name")
                or seg.get("star_system")
            )
            bodies_raw = seg.get("bodies") or seg.get("planets") or []
        else:
            system_name = str(seg)
            bodies_raw = []

        if not system_name:
            continue

        route.append(system_name)

        lines: List[str] = []
        if not bodies_raw:
            details[system_name] = lines
            continue

        for body in bodies_raw:
            if not isinstance(body, dict):
                lines.append(str(body))
                continue

            body_name = body.get("name") or body.get("body") or "???"
            body_type = body.get("type") or body.get("subtype") or ""
            est_value = body.get("value") or body.get("estimated_value")

            line = body_name
            if body_type:
                line += f" ({body_type})"
            if est_value is not None:
                try:
                    val_int = int(est_value)
                    line += f" ~{val_int:,} Cr".replace(",", " ")
                except (ValueError, TypeError):
                    line += f" ~{est_value} Cr"

            lines.append(line)

        details[system_name] = lines

    return route, details


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
) -> Tuple[List[str], Dict[str, List[str]]]:
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
        return [], {}

    jump_range = resolve_planner_jump_range(jump_range, gui_ref=gui_ref, context="riches")

    payload = _build_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_scan=min_scan,
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

    route, details = _parse_riches_result(result)
    if not route:
        spansh_error(
            "RICHES: SPANSH nie zwrócił wyników.",
            gui_ref,
            context="riches",
        )

    return route, details
