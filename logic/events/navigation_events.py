from __future__ import annotations

from typing import Dict

import config
import pyperclip

from logic import utils
from logic.insight_dispatcher import emit_insight
from logic.utils.renata_log import log_event, log_event_throttled
from app.state import app_state
from app.route_manager import route_manager
from logic.events.exploration_fss_events import (
    flush_pending_exit_summary_on_jump,
    reset_fss_progress,
)


def _exc_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _log_nav_fallback(key: str, message: str, exc: Exception, *, interval_ms: int = 5000, **fields) -> None:
    log_event_throttled(
        f"NAV:{key}",
        interval_ms,
        "NAV",
        message,
        error=_exc_text(exc),
        **fields,
    )


def _copy_pending_station_clipboard_on_arrival(current_system: str, gui_ref=None) -> None:
    system_norm = str(current_system or "").strip()
    if not system_norm:
        return

    pending = app_state.get_pending_station_clipboard_snapshot()
    if not bool(pending.get("active")):
        return

    target_system = str(pending.get("target_system") or "").strip()
    station_name = str(pending.get("station_name") or "").strip()
    if not target_system or not station_name:
        app_state.clear_pending_station_clipboard(source="navigation.pending_station.invalid")
        return

    if system_norm.casefold() != target_system.casefold():
        return

    try:
        pyperclip.copy(station_name)
    except Exception as exc:
        _log_nav_fallback(
            "pending_station.copy",
            "failed to copy pending station clipboard on arrival",
            exc,
            interval_ms=7000,
            system=system_norm,
            station=station_name,
        )
        return

    app_state.clear_pending_station_clipboard(source="navigation.pending_station.arrival")
    log_event(
        "CLIPBOARD",
        "pending_station_copied",
        system=system_norm,
        station=station_name,
        source=str(pending.get("source") or ""),
    )
    emit_insight(
        "Skopiowano cel stacyjny po dolocie.",
        gui_ref=gui_ref,
        message_id="MSG.NEXT_HOP_COPIED",
        source="navigation_events",
        event_type="ROUTE_PROGRESS",
        context={
            "system": station_name,
            "risk_status": "RISK_LOW",
            "var_status": "VAR_LOW",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        },
        priority="P2_NORMAL",
        dedup_key=f"target_copy_station:{system_norm}:{station_name}",
        cooldown_scope="entity",
        cooldown_seconds=8.0,
    )


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
    except Exception as exc:
        _log_nav_fallback("next_hop.fsdjump", "auto next-hop update on FSDJump failed", exc)


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
        docked = bool(ev.get("Docked"))
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
        star_pos = ev.get("StarPos")
        if isinstance(star_pos, (list, tuple)) and len(star_pos) >= 3:
            app_state.set_star_pos(star_pos)
        if typ in ("FSDJump", "CarrierJump") and not is_bootstrap_replay:
            try:
                flush_pending_exit_summary_on_jump(gui_ref=gui_ref)
            except Exception as exc:
                _log_nav_fallback(
                    "exploration_summary.flush_on_jump",
                    "failed to flush armed exploration summary on jump",
                    exc,
                )
        # reset FSS + discovery/footfall przy wej+Ťciu do nowego systemu
        reset_fss_progress(preserve_exobio=is_bootstrap_replay)
        app_state.set_system(sysname)
        try:
            app_state.update_spansh_milestone_on_system(sysname)
        except Exception as exc:
            _log_nav_fallback("milestone.update", "failed to update active spansh milestone", exc)
        if not is_bootstrap_replay:
            try:
                app_state.mark_live_system_event()
            except Exception as exc:
                _log_nav_fallback("live_event.mark", "failed to mark live system event", exc)
        _copy_pending_station_clipboard_on_arrival(str(sysname), gui_ref=gui_ref)
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
            except Exception as exc:
                _log_nav_fallback("next_hop.location", "auto next-hop update on Location failed", exc)
        if typ != "Location":
            if is_bootstrap_replay:
                return
            # NAV-NEXT-HOP-SEMANTICS-01:
            # TTS "MSG.NEXT_HOP" should prefer the real next hop from route state.
            # Without active route, announce current jump as "jumped system", not "next hop".
            next_hop = route_manager.get_next_system(str(sysname))
            if next_hop:
                emit_insight(
                    f"Skok: {sysname}",
                    gui_ref=gui_ref,
                    message_id="MSG.NEXT_HOP",
                    source="navigation_events",
                    event_type="ROUTE_PROGRESS",
                    context={
                        "system": next_hop,
                        "risk_status": "RISK_LOW",
                        "var_status": "VAR_LOW",
                        "trust_status": "TRUST_HIGH",
                        "confidence": "high",
                    },
                    priority="P2_NORMAL",
                    dedup_key=f"next_hop:{next_hop}",
                    cooldown_scope="entity",
                    cooldown_seconds=8.0,
                )
            elif config.get("read_system_after_jump", True):
                emit_insight(
                    f"Skok: {sysname}",
                    gui_ref=gui_ref,
                    message_id="MSG.JUMPED_SYSTEM",
                    source="navigation_events",
                    event_type="JUMP_COMPLETED",
                    context={
                        "system": sysname,
                        "risk_status": "RISK_LOW",
                        "var_status": "VAR_LOW",
                        "trust_status": "TRUST_HIGH",
                        "confidence": "high",
                    },
                    priority="P2_NORMAL",
                    dedup_key=f"jumped:{sysname}",
                    cooldown_scope="entity",
                    cooldown_seconds=8.0,
                )
            # AUTO-COPY Cel podr+-+-y (tylko w pierwszym bloku, jak w oryginale)
            try:
                if (gui_ref and hasattr(gui_ref, "state")
                        and getattr(gui_ref.state, "next_travel_target", None) == sysname):
                    obj = (getattr(gui_ref.state, "current_station", None)
                           or getattr(gui_ref.state, "current_body", None))
                    if obj:
                        pyperclip.copy(obj)
                        emit_insight(
                            "Skopiowano cel podr+-+-y",
                            gui_ref=gui_ref,
                            message_id="MSG.NEXT_HOP_COPIED",
                            source="navigation_events",
                            event_type="ROUTE_PROGRESS",
                            context={
                                "system": obj,
                                "risk_status": "RISK_LOW",
                                "var_status": "VAR_LOW",
                                "trust_status": "TRUST_HIGH",
                                "confidence": "high",
                            },
                            priority="P2_NORMAL",
                            dedup_key=f"target_copy:{obj}",
                            cooldown_scope="entity",
                            cooldown_seconds=8.0,
                        )
                    gui_ref.state.next_travel_target = None
            except Exception as exc:
                _log_nav_fallback(
                    "travel_target.copy",
                    "failed to copy travel target after jump",
                    exc,
                    interval_ms=7000,
                )

def handle_docked(ev: Dict[str, object], gui_ref=None):
    """
    Obs+éuga eventu Docked.
    """
    st = ev.get("StationName")
    if st:
        app_state.set_station(st)
        app_state.set_docked(True)
        emit_insight(
            f"Dokowano w {st}",
            gui_ref=gui_ref,
            message_id="MSG.DOCKED",
            source="navigation_events",
            event_type="ROUTE_PROGRESS",
            context={
                "station": st,
                "risk_status": "RISK_LOW",
                "var_status": "VAR_LOW",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key=f"docked:{st}",
            cooldown_scope="entity",
            cooldown_seconds=8.0,
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
    emit_insight(
        "Odlot z portu.",
        gui_ref=gui_ref,
        message_id="MSG.UNDOCKED",
        source="navigation_events",
        event_type="ROUTE_PROGRESS",
        context={
            "risk_status": "RISK_LOW",
            "var_status": "VAR_LOW",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        },
        priority="P2_NORMAL",
        dedup_key="undocked",
        cooldown_scope="message",
        cooldown_seconds=6.0,
    )


def handle_navroute_update(navroute_data: Dict[str, object], gui_ref=None) -> None:
    """
    Ingest NavRoute.json snapshot into app_state.nav_route.
    This is read-only context for route symbiosis and must not overwrite Spansh route state.
    """
    event_name = str(navroute_data.get("event") or "").strip()
    if event_name in {"NavRouteClear", "ClearRoute"}:
        app_state.clear_nav_route(source="navroute_clear")
        try:
            snap = app_state.get_route_awareness_snapshot()
            if snap.get("route_mode") == "awareness":
                app_state.update_route_awareness(
                    route_mode="idle",
                    route_target="",
                    route_progress_percent=0,
                    next_system="",
                    is_off_route=False,
                    source="navroute_clear",
                )
        except Exception as exc:
            _log_nav_fallback("navroute.clear.state", "failed to clear route awareness on NavRouteClear", exc)
        return

    route_items = navroute_data.get("Route")
    if not isinstance(route_items, list):
        route_items = []

    systems: list[str] = []
    for row in route_items:
        if not isinstance(row, dict):
            continue
        system_name = (
            row.get("StarSystem")
            or row.get("SystemName")
            or row.get("StarSystemName")
        )
        if not system_name:
            continue
        system_text = str(system_name).strip()
        if not system_text:
            continue
        if systems and systems[-1].casefold() == system_text.casefold():
            continue
        systems.append(system_text)

    endpoint = str(navroute_data.get("EndSystem") or "").strip() or None

    if not systems and event_name in {"NavRoute", "Route"}:
        app_state.clear_nav_route(source="navroute_empty")
        try:
            snap = app_state.get_route_awareness_snapshot()
            if snap.get("route_mode") == "awareness":
                app_state.update_route_awareness(
                    route_mode="idle",
                    route_target="",
                    route_progress_percent=0,
                    next_system="",
                    is_off_route=False,
                    source="navroute_empty",
                )
        except Exception as exc:
            _log_nav_fallback("navroute.empty.state", "failed to clear route awareness on empty navroute", exc)
        return

    app_state.set_nav_route(endpoint=endpoint, systems=systems, source="navroute_json")
    try:
        has_spansh_route = bool(getattr(route_manager, "route", None))
        has_spansh_milestones = bool(getattr(app_state, "spansh_milestones", None))
        if has_spansh_route or has_spansh_milestones:
            return

        current_norm = " ".join(str(getattr(app_state, "current_system", "") or "").strip().split()).casefold()
        ordered_norm = [" ".join(str(value).strip().split()).casefold() for value in systems]
        next_system = systems[0] if systems else ""
        progress = 0
        if current_norm and current_norm in ordered_norm:
            idx = ordered_norm.index(current_norm)
            if idx + 1 < len(systems):
                next_system = systems[idx + 1]
            else:
                next_system = ""
            if len(systems) <= 1:
                progress = 100
            else:
                progress = int((idx * 100) / max(1, len(systems) - 1))
                progress = max(0, min(100, progress))

        target = endpoint or (systems[-1] if systems else "")
        app_state.update_route_awareness(
            route_mode="awareness",
            route_target=str(target or ""),
            route_progress_percent=progress,
            next_system=str(next_system or ""),
            is_off_route=False,
            source="navroute_json",
        )
    except Exception as exc:
        _log_nav_fallback("navroute.state", "failed to update route awareness from navroute", exc)
