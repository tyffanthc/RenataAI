from __future__ import annotations

from typing import Any, Dict, List

import config
from logic.utils import powiedz, MSG_QUEUE
from logic.spansh_client import client, spansh_error
from logic import spansh_payloads
from logic.rows_normalizer import normalize_trade_rows


def _build_payload_trade(
    system: str,
    station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: float,
    flags: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Buduje payload do SPANSH /api/trade/route na podstawie danych z GUI.

    Parametry:
        system      – nazwa systemu startowego
        station     – nazwa stacji startowej (wymagana przez SPANSH Trade)
        capital     – kapitał [Cr]
        max_hop     – maksymalny zasięg pojedynczego skoku [LY]
        cargo       – ładowność [t]
        max_hops    – maksymalna liczba skoków
        max_dta     – maksymalna odległość do stacji [ls]
        max_age     – maksymalny wiek danych [dni] (Maximum Market Age)
        flags       – słownik z checkboxów z GUI:
                      large_pad, planetary, player_owned,
                      restricted, prohibited, avoid_loops, allow_permits
    """
    # Bezpieczne wyciągnięcie flag – domyślnie False
    large_pad = bool(flags.get("large_pad"))
    planetary = bool(flags.get("planetary"))
    player_owned = bool(flags.get("player_owned"))
    restricted = bool(flags.get("restricted"))
    prohibited = bool(flags.get("prohibited"))
    avoid_loops = bool(flags.get("avoid_loops"))
    allow_permits = bool(flags.get("allow_permits"))

    payload: Dict[str, Any] = {
        "max_hops": int(max_hops),
        "max_hop_distance": float(max_hop),
        "system": system,
        "station": station,
        "starting_capital": int(capital),
        "max_cargo": int(cargo),
        "max_system_distance": int(max_dta),
        "requires_large_pad": int(large_pad),
        "allow_prohibited": int(prohibited),
        "allow_planetary": int(planetary),
        "allow_player_owned": int(player_owned),
        "allow_restricted_access": int(restricted),
        # "unique" – SPANSH traktuje to jako „unikalne trasy / unikaj pętli”
        "unique": int(avoid_loops),
        # "permit" – czy dopuszczać systemy na pozwolenie
        "permit": int(allow_permits),
    }

    return payload


def oblicz_trade(
    start_system: str,
    start_station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: float,
    flags: Dict[str, Any],
    gui_ref: Any | None = None,
) -> tuple[list[str], list[dict]]:
    """
    Logika Trade Plannera oparta o SPANSH /api/trade/route.

    Parametry (z GUI):
        start_system - system startowy
        start_station - stacja startowa
        capital      - kapital [Cr]
        max_hop      - max hop distance [LY]
        cargo        - ladownosc [t]
        max_hops     - max liczba skokow
        max_dta      - max distance to arrival [ls]
        max_age      - max wiek danych [dni]
        flags        - slownik z checkboxow

    Zwraca:
        (route, rows) - trasa + wiersze tabeli.
    """
    try:
        system = (start_system or "").strip()
        station = (start_station or "").strip()

        if system and not station:
            raw = system
            parts: list[str] = []

            if "/" in raw:
                parts = [p.strip() for p in raw.split("/", 1)]
            elif "," in raw:
                parts = [p.strip() for p in raw.split(",", 1)]

            if parts:
                if parts[0]:
                    system = parts[0]
                if len(parts) > 1 and parts[1]:
                    station = parts[1]

        if not system:
            spansh_error(
                "TRADE: brak systemu startowego.",
                gui_ref,
                context="trade",
            )
            return [], []

        if not station:
            spansh_error(
                "TRADE: wybierz stacje startowa - SPANSH Trade wymaga system+station.",
                gui_ref,
                context="trade",
            )
            return [], []

        powiedz(
            (
                f"API TRADE: {system} / {station}, kapital={capital} Cr, "
                f"hop={max_hop} LY, ladownosc={cargo} t, max hops={max_hops}"
            ),
            gui_ref,
        )

        payload = spansh_payloads.build_trade_payload(
            start_system=system,
            start_station=station,
            capital=capital,
            max_hop=max_hop,
            cargo=cargo,
            max_hops=max_hops,
            max_dta=max_dta,
            max_age=max_age,
            flags=flags,
        )
        if config.get("features.spansh.debug_payload", False):
            MSG_QUEUE.put(("log", f"[SPANSH TRADE PAYLOAD] {payload.form_fields}"))

        result = client.route(
            mode="trade",
            payload=payload,
            referer="https://spansh.co.uk/trade",
            gui_ref=gui_ref,
        )

        if not result:
            return [], []

        route, rows = normalize_trade_rows(result)

        if not rows:
            spansh_error(
                "TRADE: SPANSH nie zwrocil zadnych propozycji.",
                gui_ref,
                context="trade",
            )
            return [], []

        return route, rows

    except Exception as e:  # noqa: BLE001
        powiedz(f"TRADE error: {e}", gui_ref)
        return [], []
