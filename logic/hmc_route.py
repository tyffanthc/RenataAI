"""
High Metal Content Worlds – backend SPANSH.

Po D1/D3:
- używa SpanshClient.route(mode="riches"),
- payload R2R-owy z filtrem HMC,
- max_results / max_distance.
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
    min_scan: int,
    loop: bool,
    avoid_tharg: bool,
) -> Dict[str, Any]:
    """
    Payload dla SPANSH /riches/route z filtrami HMC/Rocky.
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
        # multi-entry body_types: Rocky + HMC
        "body_types": ["Rocky body", "High metal content world"],
    }

    # Usuwamy None, żeby np. puste "to" nie szło jako null.
    return {k: v for k, v in payload.items() if v is not None}


def _parse_hmc_result(result: Any) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Parser wyniku HMC Worlds.
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
            est_value = body.get("value") or body.get("estimated_value")

            line = body_name
            if est_value is not None:
                try:
                    val_int = int(est_value)
                    line += f" ~{val_int:,} Cr".replace(",", " ")
                except (ValueError, TypeError):
                    line += f" ~{est_value} Cr"

            lines.append(line)

        details[system_name] = lines

    return route, details


def oblicz_hmc(
    start: str,
    cel: str,
    jump_range: float,
    radius: float,
    max_sys: int,
    max_dist: int,
    loop: bool,
    avoid_tharg: bool,
    gui_ref: Any | None = None,
) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    API dla zakładki HMC Worlds.

    Uwaga: sygnatura dopasowana do GUI (bez min_scan),
    minimalna wartość skanu ustawiana wewnętrznie.
    """
    # prosty próg minimalnej wartości – 1 Cr
    min_scan = 1

    start = (start or "").strip()
    cel = (cel or "").strip()

    powiedz(
        f"API: HMC Worlds z {start} (radius {radius}Ly)...",
        gui_ref,
    )

    if not start:
        spansh_error("HMC: brak systemu startowego.", gui_ref, context="hmc")
        return [], {}

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
        referer="https://spansh.co.uk/rocky-metal",
        gui_ref=gui_ref,
    )

    route, details = _parse_hmc_result(result)
    if not route:
        spansh_error("HMC: SPANSH nie zwrócił wyników.", gui_ref, context="hmc")

    return route, details
