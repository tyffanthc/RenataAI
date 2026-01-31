# logic/events/smuggler_events.py

from __future__ import annotations

from typing import Any, Dict

from logic.utils import powiedz
from logic import utils


# --- SMUGGLER ALERT (S2-LOGIC-07) ---
CARGO_HAS_ILLEGAL = False           # czy na pokładzie jest nielegalny/stolen towar
SMUGGLER_WARNED_TARGETS = set()     # stacje/osady, dla których już padł alert


def update_illegal_cargo(ev: Dict[str, Any]):
    """
    S2-LOGIC-07 — aktualizacja flagi CARGO_HAS_ILLEGAL
    na podstawie eventu Cargo.

    Szukamy w Inventory towarów z flagami typu Illegal / Stolen / IsStolen.

    Przeniesione z EventHandler._update_illegal_cargo.
    """
    global CARGO_HAS_ILLEGAL

    inventory = ev.get("Inventory") or ev.get("Cargo") or []
    if not isinstance(inventory, list):
        return

    has_illegal = False

    for item in inventory:
        if not isinstance(item, dict):
            continue

        # Journal bywa różny, więc sprawdzamy kilka pól
        illegal = item.get("Illegal")
        stolen = item.get("Stolen")
        is_stolen = item.get("IsStolen")

        if illegal or stolen or is_stolen:
            has_illegal = True
            break

    CARGO_HAS_ILLEGAL = has_illegal


def handle_smuggler_alert(ev: Dict[str, Any], gui_ref=None):
    """
    S2-LOGIC-07 — Smuggler Alert (nielegalny ładunek przy zbliżaniu się do stacji).

    Eventy:
    - ApproachSettlement
    - DockingRequested

    Warunek:
    - na pokładzie jest nielegalny ładunek (CARGO_HAS_ILLEGAL == True)
    - dla danej stacji/osady nie padł jeszcze komunikat

    Przeniesione z EventHandler._check_smuggler_alert.
    """
    global CARGO_HAS_ILLEGAL, SMUGGLER_WARNED_TARGETS

    if not CARGO_HAS_ILLEGAL:
        return

    event_name = ev.get("event")
    target_key = None
    target_label = None

    if event_name == "DockingRequested":
        station = ev.get("StationName") or ev.get("Station") or "UNKNOWN_STATION"
        target_key = f"STATION::{station}"
        target_label = station

    elif event_name == "ApproachSettlement":
        settlement = (
            ev.get("Name")
            or ev.get("SettlementName")
            or ev.get("BodyName")
            or "UNKNOWN_SETTLEMENT"
        )
        target_key = f"SETTLEMENT::{settlement}"
        target_label = settlement

    if not target_key:
        return

    # antyspam – tylko jeden komunikat na daną stację/osadę
    if target_key in SMUGGLER_WARNED_TARGETS:
        return

    SMUGGLER_WARNED_TARGETS.add(target_key)

    msg = "Uwaga. Nielegalny ładunek na pokładzie. Zalecam tryb cichego biegu."
    powiedz(
        msg,
        gui_ref,
        message_id="MSG.SMUGGLER_ILLEGAL_CARGO",
        context={"raw_text": msg},
    )

    # dla czytelności wrzucimy też w log Pulpitu
    try:
        utils.MSG_QUEUE.put(
            ("log", f"[SMUGGLER ALERT] {target_label} — wykryto nielegalny ładunek na pokładzie.")
        )
    except Exception:
        pass
