from __future__ import annotations

from typing import Any, Dict, List

from logic.utils import powiedz
from logic.spansh_client import client, spansh_error


def _build_payload_trade(
    system: str,
    station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: int,
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
        max_age     – maksymalny wiek danych [dni] (obecnie nieużywany, ale zostaje
                      jako potencjalny parametr do przyszłych wersji API)
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

    # max_age na razie nie jest używany w payloadzie trade (brak wsparcia w API),
    # ale zostawiamy tutaj miejsce, gdyby SPANSH dodał takie pole w przyszłości.
    # if max_age > 0:
    #     payload["max_age_days"] = int(max_age)

    return payload


def oblicz_trade(
    start_system: str,
    start_station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: int,
    flags: Dict[str, Any],
    gui_ref: Any | None = None,
) -> List[str]:
    """
    Logika Trade Plannera oparta o SPANSH /api/trade/route.

    Parametry (z GUI):
        start_system – system startowy (pole „System”; może zawierać też stację
                       w formacie 'System / Stacja' lub 'System, Stacja')
        start_station – stacja startowa (osobne pole w GUI; jeśli puste, spróbujemy
                        wyciągnąć stację ze start_system)
        capital      – kapitał [Cr]
        max_hop      – max hop distance [LY]
        cargo        – ładowność [t]
        max_hops     – max liczba skoków
        max_dta      – max distance to arrival [ls]
        max_age      – max wiek danych [dni] (obecnie nieużywany w payloadzie)
        flags        – słownik z checkboxów:
                       large_pad, planetary, player_owned,
                       restricted, prohibited, avoid_loops, allow_permits

    Zwraca:
        list[str] – linie tekstu do wyświetlenia w GUI (lista tras/propozycji).
    """
    try:
        system = (start_system or "").strip()
        station = (start_station or "").strip()

        # 1) Jeśli użytkownik wpisał wszystko w jedno pole (jak na stronie Spansh),
        #    czyli np. "Col 285 Sector CS-Z c14-12 / Solanas Palace"
        #    lub "Col 285 Sector CS-Z c14-12, Solanas Palace",
        #    a pole "Stacja" jest puste – rozbij to tutaj.
        if system and not station:
            raw = system
            parts: list[str] = []

            if "/" in raw:
                # priorytet: dokładnie ten format, który pokazuje Spansh
                parts = [p.strip() for p in raw.split("/", 1)]
            elif "," in raw:
                # fallback: stary format z Renaty "System, Stacja"
                parts = [p.strip() for p in raw.split(",", 1)]

            if parts:
                # Pierwsza część to system
                if parts[0]:
                    system = parts[0]
                # Druga (jeśli jest) to stacja
                if len(parts) > 1 and parts[1]:
                    station = parts[1]

        if not system:
            spansh_error(
                "TRADE: brak systemu startowego.",
                gui_ref,
                context="trade",
            )
            return []

        if not station:
            spansh_error(
                "TRADE: wybierz stację startową — SPANSH Trade wymaga system+station.",
                gui_ref,
                context="trade",
            )
            return []

        powiedz(
            (
                f"API TRADE: {system} / {station}, kapitał={capital} Cr, "
                f"hop={max_hop} LY, ładowność={cargo} t, max hops={max_hops}"
            ),
            gui_ref,
        )

        payload = _build_payload_trade(
            system=system,
            station=station,
            capital=capital,
            max_hop=max_hop,
            cargo=cargo,
            max_hops=max_hops,
            max_dta=max_dta,
            max_age=max_age,
            flags=flags,
        )

        result = client.route(
            mode="trade",
            payload=payload,
            referer="https://spansh.co.uk/trade",
            gui_ref=gui_ref,
        )

        if not result:
            # komunikat o błędzie już poszedł z warstwy klienta
            return []

        # --- Parsowanie wyniku ------------------------------------------------
        lines: List[str] = []

        # typowo SPANSH dla trade może zwracać listę „legs”/„hops”
        core = result
        if isinstance(result, dict):
            core = (
                result.get("result")
                or result.get("routes")
                or result.get("legs")
                or result.get("hops")
                or result
            )

        if isinstance(core, list):
            for idx, leg in enumerate(core, start=1):
                if isinstance(leg, dict):
                    frm = (
                        leg.get("from_system")
                        or leg.get("from")
                        or leg.get("source_system")
                        or ""
                    )
                    to = (
                        leg.get("to_system")
                        or leg.get("to")
                        or leg.get("destination_system")
                        or ""
                    )
                    commodity = leg.get("commodity") or leg.get("item") or ""
                    profit = (
                        leg.get("profit")
                        or leg.get("estimated_profit")
                        or leg.get("profit_per_tonne")
                    )

                    base = f"{idx}. {frm} -> {to}" if frm or to else f"{idx}."
                    if commodity:
                        base += f" ({commodity}"
                        if profit is not None:
                            try:
                                p_int = int(profit)
                                base += f", +{p_int:,} Cr".replace(",", " ")
                            except (ValueError, TypeError):
                                base += f", +{profit} Cr"
                        base += ")"
                    elif profit is not None:
                        try:
                            p_int = int(profit)
                            base += f" (+{p_int:,} Cr)".replace(",", " ")
                        except (ValueError, TypeError):
                            base += f" (+{profit} Cr)"

                    lines.append(base)
                else:
                    lines.append(f"{idx}. {leg}")
        else:
            # fallback – pojedynczy obiekt / cokolwiek
            lines.append(str(core))

        if not lines:
            spansh_error(
                "TRADE: SPANSH nie zwrócił żadnych propozycji.",
                gui_ref,
                context="trade",
            )
            return []

        return lines

    except Exception as e:  # noqa: BLE001
        powiedz(f"TRADE error: {e}", gui_ref)
        return []
