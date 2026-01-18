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

from typing import Any, List, Tuple, Dict

from logic.spansh_client import client, spansh_error, resolve_planner_jump_range
from logic.utils import powiedz


def oblicz_spansh(
    start: str,
    cel: str,
    zasieg: float,
    eff: float,
    gui_ref: Any | None = None,
    *,
    supercharge_mode: str | None = None,
    via: List[str] | None = None,
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

    zasieg = resolve_planner_jump_range(zasieg, gui_ref=gui_ref, context="neutron")

    systems = client.neutron_route(
        start=start,
        cel=cel,
        zasieg=zasieg,
        eff=eff,
        gui_ref=gui_ref,
        supercharge_mode=supercharge_mode,
        via=via,
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


def oblicz_spansh_with_details(
    start: str,
    cel: str,
    zasieg: float,
    eff: float,
    gui_ref: Any | None = None,
    *,
    supercharge_mode: str | None = None,
    via: List[str] | None = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    API dla zakładki Neutron Plotter z dodatkowymi metadanymi skoków.

    Zwraca:
        (lista_systemów, lista_szczegółów)
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
        return [], []

    zasieg = resolve_planner_jump_range(zasieg, gui_ref=gui_ref, context="neutron")

    systems, details = client.neutron_route(
        start=start,
        cel=cel,
        zasieg=zasieg,
        eff=eff,
        gui_ref=gui_ref,
        return_details=True,
        supercharge_mode=supercharge_mode,
        via=via,
    )

    if not systems:
        spansh_error(
            "NEUTRON: SPANSH nie zwrócił żadnej trasy.",
            gui_ref,
            context="neutron",
        )
        return [], []

    return systems, details
