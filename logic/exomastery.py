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

from logic.spansh_client import client, spansh_error
from logic.utils import powiedz


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
        "min_landmark_value": int(min_landmark_value)
        if min_landmark_value is not None
        else None,
        "loop": bool(loop),
        "avoid_thargoids": bool(avoid_tharg),
    }

    return {k: v for k, v in payload.items() if v is not None}


def _parse_exomastery_result(result: Any) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Parser wyniku Exomastery.

    Zwraca:
        route   – lista systemów
        details – dict: {system: [linie opisu bio]}
    """
    route: List[str] = []
    details: Dict[str, List[str]] = {}

    if not result:
        return route, details

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
            bio_raw = seg.get("landmarks") or seg.get("bio") or []
        else:
            system_name = str(seg)
            bio_raw = []

        if not system_name:
            continue

        route.append(system_name)

        lines: List[str] = []
        if not bio_raw:
            details[system_name] = lines
            continue

        for landmark in bio_raw:
            if not isinstance(landmark, dict):
                lines.append(str(landmark))
                continue

            body_name = (
                landmark.get("body")
                or landmark.get("name")
                or landmark.get("body_name")
                or "???"
            )
            species = landmark.get("species") or landmark.get("type") or ""
            value = (
                landmark.get("value")
                or landmark.get("estimated_value")
                or landmark.get("scan_value")
            )

            line = body_name
            if species:
                line += f" ({species})"
            if value is not None:
                try:
                    val_int = int(value)
                    line += f" ~{val_int:,} Cr".replace(",", " ")
                except (ValueError, TypeError):
                    line += f" ~{value} Cr"

            lines.append(line)

        details[system_name] = lines

    return route, details


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
) -> Tuple[List[str], Dict[str, List[str]]]:
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
        return [], {}

    payload = _build_payload(
        start=start,
        cel=cel,
        jump_range=jump_range,
        radius=radius,
        max_sys=max_sys,
        max_dist=max_dist,
        min_landmark_value=min_landmark_value,
        loop=loop,
        avoid_tharg=avoid_tharg,
    )

    result = client.route(
        mode="exobiology",
        payload=payload,
        referer="https://spansh.co.uk/exobiology",
        gui_ref=gui_ref,
    )

    route, details = _parse_exomastery_result(result)
    if not route:
        spansh_error(
            "EXO: SPANSH nie zwrócił wyników.",
            gui_ref,
            context="exomastery",
        )

    return route, details
