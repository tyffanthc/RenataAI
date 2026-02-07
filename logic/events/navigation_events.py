from __future__ import annotations

from typing import Dict

import config
import pyperclip

from logic.utils import powiedz
from logic import utils
from logic.utils.renata_log import log_event
from app.state import app_state
from app.route_manager import route_manager
from logic.events.exploration_fss_events import reset_fss_progress


def handle_fsd_jump_autoschowek(ev: Dict[str, object], gui_ref=None):
    """
    S1-LOGIC-04 ÔÇö GLOBALNY AUTO-SCHOWEK PO FSDJump.

    Przeniesione 1:1 z EventHandler.handle_event (sekcja FSDJump).
    """
    # 1. Pobierz aktualny system z eventu
    current_system = (
        ev.get("StarSystem")
        or ev.get("SystemName")
        or ev.get("StarSystemName")
    )
    log_event("JOURNAL", "fsd_jump", system=current_system)

    # 2. Przesu+ä tras¦Ö w RouteManagerze
    route_manager.advance_route(current_system)

    # 3. Auto-clipboard NEXT_HOP (konfigurowalny)
    try:
        from gui import common as gui_common  # type: ignore

        stepper_enabled = config.get("features.clipboard.next_hop_stepper", True)
        log_event(
            "CLIPBOARD",
            "next_hop_trigger",
            trigger="fsdjump",
            enabled=stepper_enabled,
            system=current_system,
        )
        if stepper_enabled:
            gui_common.update_next_hop_on_system(
                str(current_system) if current_system is not None else None,
                "fsdjump",
                source="auto_clipboard",
            )
    except Exception:
        pass


def handle_location_fsdjump_carrier(ev: Dict[str, object], gui_ref=None):
    """
    Obs+éuga event+-w:
    - Location
    - FSDJump
    - CarrierJump

    Przeniesione z bloku "pozycja gracza" w EventHandler.handle_event.
    NAV-NEXT-HOP-DUPLICATE-01: pojedyncza obsluga komunikatu skoku na event.
    """
    typ = ev.get("event")
    is_bootstrap_replay = bool(getattr(app_state, "bootstrap_replay", False))

    # D3c: inicjalizacja docked/station z eventu Location (je+Ťli dost¦Öpne)
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
        # reset FSS + discovery/footfall przy wej+Ťciu do nowego systemu
        reset_fss_progress()
        app_state.set_system(sysname)
        if not is_bootstrap_replay:
            try:
                app_state.mark_live_system_event()
            except Exception:
                pass
        if typ == "Location":
            try:
                from gui import common as gui_common  # type: ignore

                stepper_enabled = config.get("features.clipboard.next_hop_stepper", True)
                log_event(
                    "CLIPBOARD",
                    "next_hop_trigger",
                    trigger="location",
                    enabled=stepper_enabled,
                    system=sysname,
                )
                if stepper_enabled:
                    gui_common.update_next_hop_on_system(
                        str(sysname) if sysname is not None else None,
                        "location",
                        source="auto_clipboard",
                    )
            except Exception:
                pass
        if typ != "Location":
            if is_bootstrap_replay:
                return
            # NAV-NEXT-HOP-SEMANTICS-01:
            # TTS "MSG.NEXT_HOP" should prefer the real next hop from route state.
            # Without active route, announce current jump as "jumped system", not "next hop".
            next_hop = route_manager.get_next_system(str(sysname))
            if next_hop:
                powiedz(
                    f"Skok: {sysname}",
                    gui_ref,
                    message_id="MSG.NEXT_HOP",
                    context={"system": next_hop},
                )
            elif config.get("read_system_after_jump", True):
                powiedz(
                    f"Skok: {sysname}",
                    gui_ref,
                    message_id="MSG.JUMPED_SYSTEM",
                    context={"system": sysname},
                )
            # AUTO-COPY Cel podr+-+-y (tylko w pierwszym bloku, jak w oryginale)
            try:
                if (gui_ref and hasattr(gui_ref, "state")
                        and getattr(gui_ref.state, "next_travel_target", None) == sysname):
                    obj = (getattr(gui_ref.state, "current_station", None)
                           or getattr(gui_ref.state, "current_body", None))
                    if obj:
                        pyperclip.copy(obj)
                        powiedz(
                            "Skopiowano cel podr+-+-y",
                            gui_ref,
                            message_id="MSG.NEXT_HOP_COPIED",
                            context={"system": obj},
                        )
                    gui_ref.state.next_travel_target = None
            except Exception:
                pass

def handle_docked(ev: Dict[str, object], gui_ref=None):
    """
    Obs+éuga eventu Docked.
    """
    st = ev.get("StationName")
    if st:
        app_state.set_station(st)
        app_state.set_docked(True)
        powiedz(
            f"Dokowano w {st}",
            gui_ref,
            message_id="MSG.DOCKED",
            context={"station": st},
        )
    else:
        # nawet je+Ťli z jakiego+Ť powodu brak nazwy stacji, sam event Docked
        # oznacza, +-e jeste+Ťmy zadokowani
        app_state.set_docked(True)


def handle_undocked(ev: Dict[str, object], gui_ref=None):
    """
    Obs+éuga eventu Undocked.
    """
    app_state.set_docked(False)
    powiedz("Odlot z portu.", gui_ref, message_id="MSG.UNDOCKED")
