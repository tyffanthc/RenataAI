from __future__ import annotations

from typing import Dict

import pyperclip

from logic.utils import powiedz
from logic import utils
from app.state import app_state
from app.route_manager import route_manager
from logic.events.exploration_fss_events import reset_fss_progress


def handle_fsd_jump_autoschowek(ev: Dict[str, object], gui_ref=None):
    """
    S1-LOGIC-04 — GLOBALNY AUTO-SCHOWEK PO FSDJump.

    Przeniesione 1:1 z EventHandler.handle_event (sekcja FSDJump).
    """
    # 1. Pobierz aktualny system z eventu
    current_system = (
        ev.get("StarSystem")
        or ev.get("SystemName")
        or ev.get("StarSystemName")
    )

    # 2. Przesuń trasę w RouteManagerze
    route_manager.advance_route(current_system)

    # 3. Pobierz następny system
    next_system = route_manager.get_next_system(current_system)

    # 4. Sprawdź checkbox Auto-Schowek z zakładki Spansh (przez gui_ref)
    auto_copy_enabled = False
    if gui_ref is not None:
        try:
            auto_copy_enabled = getattr(gui_ref.tab_spansh, "auto_copy_var").get()
        except Exception:
            auto_copy_enabled = False

    # 5. Jeśli Auto-Schowek włączony i trasa istnieje → kopiujemy
    if auto_copy_enabled and next_system:
        try:
            pyperclip.copy(next_system)
            utils.MSG_QUEUE.put(
                ("log", f"[AUTO-SCHOWEK] Skok wykryty — skopiowano: {next_system}")
            )
        except Exception as e:
            utils.MSG_QUEUE.put(
                ("log", f"[AUTO-SCHOWEK] Błąd kopiowania: {e}")
            )
    elif auto_copy_enabled and not next_system:
        utils.MSG_QUEUE.put(
            ("log", "[AUTO-SCHOWEK] Brak kolejnego systemu.")
        )


def handle_location_fsdjump_carrier(ev: Dict[str, object], gui_ref=None):
    """
    Obsługa eventów:
    - Location
    - FSDJump
    - CarrierJump

    Przeniesione z bloku 'pozycja gracza' w EventHandler.handle_event.
    Zachowuje nawet podwójny reset/powiedz (jak w oryginale), żeby nie zmieniać zachowania.
    """
    typ = ev.get("event")

    # D3c: inicjalizacja docked/station z eventu Location (jeśli dostępne)
    if typ == "Location":
        try:
            docked = bool(ev.get("Docked"))
        except Exception:
            docked = False
        app_state.set_docked(docked)
        if docked:
            st = ev.get("StationName")
            if st:
                app_state.set_station(st)

    sysname = (
        ev.get("StarSystem")
        or ev.get("SystemName")
        or ev.get("StarSystemName")
    )
    if sysname:
        # reset FSS + discovery/footfall przy wejściu do nowego systemu
        reset_fss_progress()
        app_state.set_system(sysname)
        if typ != "Location":
            powiedz(f"Skok: {sysname}", gui_ref)
            # AUTO-COPY Cel podróży (tylko w pierwszym bloku, jak w oryginale)
            try:
                if (gui_ref and hasattr(gui_ref, "state")
                        and getattr(gui_ref.state, "next_travel_target", None) == sysname):
                    obj = (getattr(gui_ref.state, "current_station", None)
                           or getattr(gui_ref.state, "current_body", None))
                    if obj:
                        pyperclip.copy(obj)
                        powiedz("Skopiowano cel podróży", gui_ref)
                    gui_ref.state.next_travel_target = None
            except Exception:
                pass

    # Oryginalny kod miał duplikację tego bloku bez auto-copy;
    # zachowujemy ją, aby nie zmieniać zachowania (podwójny powiedz przy FSDJump/CarrierJump).
    sysname = (
        ev.get("StarSystem")
        or ev.get("SystemName")
        or ev.get("StarSystemName")
    )
    if sysname:
        reset_fss_progress()
        app_state.set_system(sysname)
        if typ != "Location":
            powiedz(f"Skok: {sysname}", gui_ref)


def handle_docked(ev: Dict[str, object], gui_ref=None):
    """
    Obsługa eventu Docked.
    """
    st = ev.get("StationName")
    if st:
        app_state.set_station(st)
        app_state.set_docked(True)
        powiedz(f"Dokowano w {st}", gui_ref)
    else:
        # nawet jeśli z jakiegoś powodu brak nazwy stacji, sam event Docked
        # oznacza, że jesteśmy zadokowani
        app_state.set_docked(True)


def handle_undocked(ev: Dict[str, object], gui_ref=None):
    """
    Obsługa eventu Undocked.
    """
    app_state.set_docked(False)
    powiedz("Odlot z portu.", gui_ref)
