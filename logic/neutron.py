# logic/neutron.py
"""
Neutron Plotter – backend SPANSH (v2025).

Po D3:
- cała komunikacja HTTP idzie przez logic.spansh_client.SpanshClient,
- brak lokalnych timeoutów / URL-i,
- spójna obsługa błędów (spansh_error + powiedz),
- GUI nadal korzysta z oblicz_spansh() i dostaje listę nazw systemów.
"""

from __future__ import annotations

from typing import Any, List

from logic.spansh_client import client, spansh_error
from logic.utils import powiedz


def oblicz_spansh(
    start: str,
    cel: str,
    zasieg: float,
    eff: float,
    gui_ref: Any | None = None,
) -> List[str]:
    """
    API dla zakładki Neutron Plotter.

    Wejście:
        start   – system startowy
        cel     – system docelowy
        zasieg  – zasięg statku (LY)
        eff     – efficiency w %

    Wyjście:
        lista nazw systemów po kolei (jak wcześniej).
    """
    start = (start or "").strip()
    cel = (cel or "").strip()

    powiedz(
        f"API: Trasa neutronowa {start} -> {cel} (Eff: {eff}%).",
        gui_ref,
    )

    if not start or not cel:
        spansh_error(
            "NEUTRON: brak systemu startowego lub docelowego.",
            gui_ref,
            context="neutron",
        )
        return []

    systems = client.neutron_route(
        start_system=start,
        target_system=cel,
        jump_range=zasieg,
        efficiency=eff,
        gui_ref=gui_ref,
    )

    if not systems:
        # szczegółowy komunikat już poszedł ze SpanshClient,
        # tutaj tylko user-friendly fallback
        spansh_error(
            "NEUTRON: SPANSH nie zwrócił żadnej trasy.",
            gui_ref,
            context="neutron",
        )
        return []

    return systems
