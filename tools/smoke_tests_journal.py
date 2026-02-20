"""
tools/smoke_tests_journal.py

T2 — Smoke / stress test journala + AppState + DEBOUNCER.

Uruchom z katalogu głównego projektu:
    python tools/smoke_tests_journal.py
"""

from __future__ import annotations

import os
import sys
import json
import traceback
import queue
import time
from typing import Callable, List, Tuple
from types import SimpleNamespace
from unittest.mock import patch

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config  # type: ignore
from logic.utils import MSG_QUEUE, DEBOUNCER  # type: ignore
from logic.event_handler import handler  # type: ignore
from app.state import app_state  # type: ignore
from app.route_manager import route_manager  # type: ignore
from gui import common as gui_common  # type: ignore
from logic.events import exploration_bio_events as bio_events  # type: ignore
from logic.events import fuel_events  # type: ignore
from logic.events import survival_rebuy_awareness as survival_events  # type: ignore
from logic.events import combat_awareness as combat_events  # type: ignore
from logic.events import cash_in_assistant as cash_in_events  # type: ignore
from logic.insight_dispatcher import reset_dispatcher_runtime_state  # type: ignore
from logic.exit_summary import ExitSummaryData  # type: ignore


class TestContext:
    """
    Prosty kontekst dla smoke-testów journala.

    Trzyma referencję do MSG_QUEUE i daje helpery do czyszczenia / odczytu
    komunikatów między testami.
    """

    def __init__(self) -> None:
        self.msg_queue = MSG_QUEUE

    def clear_queue(self) -> None:
        """Czyści globalną kolejkę komunikatów."""
        try:
            while True:
                self.msg_queue.get_nowait()
        except queue.Empty:
            pass

    def drain_queue(self) -> list:
        """Zwraca listę wszystkich komunikatów z kolejki i ją czyści."""
        items = []
        try:
            while True:
                items.append(self.msg_queue.get_nowait())
        except queue.Empty:
            pass
        return items

    def reset_debouncer(self) -> None:
        """Czyści wewnętrzny stan DEBOUNCER-a (cooldowny)."""
        try:
            last = getattr(DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            # Smoke-test: nie panikujemy jeśli coś pójdzie nie tak
            pass


def _ensure_voice_disabled() -> None:
    """
    Na czas smoke-testów wyłączamy TTS, żeby nie odpalać pyttsx3.

    Modyfikujemy tylko stan w pamięci (config.config._settings), nie zapisujemy
    nic do user_settings.json.
    """
    try:
        settings = config.config._settings  # type: ignore[attr-defined]
        if isinstance(settings, dict):
            settings["voice_enabled"] = False
    except Exception:
        # Smoke-test ma być odporny – jeśli się nie uda, trudno, TTS się odpali.
        pass


# --- TESTY -------------------------------------------------------------------


def test_journal_location_and_fsdjump_app_state(ctx: TestContext) -> None:
    """
    Sprawdza, że:
    - Location ustawia system w AppState i config.STATE, ale NIE mówi 'Skok: ...'
    - FSDJump ustawia system + mówi 'Skok: ...'.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    # Location
    sys_loc = "SMOKE_T2_LOC_SYS"
    ev_loc = {
        "event": "Location",
        "StarSystem": sys_loc,
    }
    handler.handle_event(json.dumps(ev_loc), gui_ref=None)
    msgs_loc = ctx.drain_queue()

    assert app_state.current_system == sys_loc, (
        f"AppState.current_system after Location should be {sys_loc}, "
        f"got {app_state.current_system!r}"
    )
    assert config.STATE.get("sys") == sys_loc, (
        f"config.STATE['sys'] after Location should be {sys_loc}, "
        f"got {config.STATE.get('sys')!r}"
    )

    joined_loc = " | ".join(str(m) for m in msgs_loc)
    assert f"[STATE] System = {sys_loc}" in joined_loc, (
        "Expected [STATE] System log after Location, "
        f"got: {joined_loc}"
    )
    assert f"Skok: {sys_loc}" not in joined_loc, (
        "Location should not trigger 'Skok:' voice line, "
        f"but messages were: {joined_loc}"
    )

    # FSDJump
    ctx.clear_queue()
    ctx.reset_debouncer()

    sys_jump = "SMOKE_T2_JUMP_SYS"
    ev_jump = {
        "event": "FSDJump",
        "StarSystem": sys_jump,
    }
    handler.handle_event(json.dumps(ev_jump), gui_ref=None)
    msgs_jump = ctx.drain_queue()

    assert app_state.current_system == sys_jump, (
        f"AppState.current_system after FSDJump should be {sys_jump}, "
        f"got {app_state.current_system!r}"
    )
    assert config.STATE.get("sys") == sys_jump, (
        f"config.STATE['sys'] after FSDJump should be {sys_jump}, "
        f"got {config.STATE.get('sys')!r}"
    )

    joined_jump = " | ".join(str(m) for m in msgs_jump)
    if f"[STATE] System = {sys_jump}" not in joined_jump:
        assert "[JOURNAL] fsd_jump" in joined_jump, (
            "Expected [STATE] System log after FSDJump (or throttled journal log), "
            f"got: {joined_jump}"
        )
    assert f"Skok: {sys_jump}" in joined_jump, (
        "Expected 'Skok:' voice line after FSDJump, "
        f"got: {joined_jump}"
    )


def test_journal_docked_updates_station(ctx: TestContext) -> None:
    """
    Sprawdza, że Docked:
    - ustawia station w AppState i config.STATE,
    - generuje komunikat tekstowy o dokowaniu.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    station = "SMOKE_T2_STATION"
    sysname = "SMOKE_T2_STATION_SYS"

    ev_docked = {
        "event": "Docked",
        "StationName": station,
        "StarSystem": sysname,
    }

    handler.handle_event(json.dumps(ev_docked), gui_ref=None)
    msgs = ctx.drain_queue()

    assert app_state.current_station == station, (
        f"AppState.current_station after Docked should be {station}, "
        f"got {app_state.current_station!r}"
    )
    assert config.STATE.get("station") == station, (
        f"config.STATE['station'] after Docked should be {station}, "
        f"got {config.STATE.get('station')!r}"
    )

    joined = " | ".join(str(m) for m in msgs)
    assert f"[STATE] Station = {station}" in joined, (
        "Expected [STATE] Station log after Docked, "
        f"got: {joined}"
    )
    assert f"Dokowano w {station}" in joined, (
        "Expected 'Dokowano w ...' voice line after Docked, "
        f"got: {joined}"
    )


def test_journal_docked_undocked_updates_is_docked(ctx: TestContext) -> None:
    """
    Sprawdza, że:
    - Docked ustawia is_docked=True w AppState i config.STATE,
    - Undocked ustawia is_docked=False w AppState i config.STATE.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    ev_docked = {
        "event": "Docked",
        "StationName": "SMOKE_T2_DOCK_FLAG_STATION",
        "StarSystem": "SMOKE_T2_DOCK_FLAG_SYS",
    }

    handler.handle_event(json.dumps(ev_docked), gui_ref=None)
    _ = ctx.drain_queue()

    assert app_state.is_docked is True, (
        "AppState.is_docked after Docked should be True, "
        f"got {app_state.is_docked!r}"
    )
    assert config.STATE.get("is_docked") is True, (
        "config.STATE['is_docked'] after Docked should be True, "
        f"got {config.STATE.get('is_docked')!r}"
    )

    ctx.clear_queue()
    ctx.reset_debouncer()

    ev_undocked = {
        "event": "Undocked",
    }

    handler.handle_event(json.dumps(ev_undocked), gui_ref=None)
    _ = ctx.drain_queue()

    assert app_state.is_docked is False, (
        "AppState.is_docked after Undocked should be False, "
        f"got {app_state.is_docked!r}"
    )
    assert config.STATE.get("is_docked") is False, (
        "config.STATE['is_docked'] after Undocked should be False, "
        f"got {config.STATE.get('is_docked')!r}"
    )


def test_debouncer_basic(ctx: TestContext) -> None:
    """
    Prosty test DEBOUNCER-a:
    - pierwszy can_send dla danego (key, context) zwraca True,
    - drugi od razu po nim zwraca False,
    - inny context nadal zwraca True.
    """
    ctx.reset_debouncer()

    key = "SMOKE_T2_TEST_KEY"
    ctx1 = "CTX1"
    ctx2 = "CTX2"

    first = DEBOUNCER.can_send(key, 60.0, context=ctx1)
    second = DEBOUNCER.can_send(key, 60.0, context=ctx1)
    third = DEBOUNCER.can_send(key, 60.0, context=ctx2)

    assert first is True, "First DEBOUNCER.can_send should return True"
    assert second is False, "Second DEBOUNCER.can_send for same context should return False"
    assert third is True, "DEBOUNCER.can_send for different context should return True"


def test_journal_sequence_no_crash(ctx: TestContext) -> None:
    """
    Mała sekwencja różnych eventów z journala, która:
    - przechodzi przez kilka modułów (navigation, bio, misc),
    - nie rzuca wyjątków,
    - kończy z sensownym stanem AppState.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    sys1 = "SMOKE_T2_SEQ_SYS_1"
    sys2 = "SMOKE_T2_SEQ_SYS_2"
    body = "SMOKE_T2_SEQ_BODY"
    station = "SMOKE_T2_SEQ_STATION"

    events = [
        {"event": "Location", "StarSystem": sys1},
        {"event": "Docked", "StarSystem": sys1, "StationName": station},
        {"event": "Undocked"},
        {"event": "FSDJump", "StarSystem": sys2},
        {
            "event": "SAASignalsFound",
            "BodyName": body,
            "Signals": [{"Type": "Biological", "Count": 3}],
        },
        {
            "event": "Footfall",
            "BodyName": body,
            "FirstFootfall": True,
        },
    ]

    for ev in events:
        handler.handle_event(json.dumps(ev), gui_ref=None)

    msgs = ctx.drain_queue()
    assert len(msgs) > 0, "Expected some messages in MSG_QUEUE after journal sequence, got none"

    assert app_state.current_system == sys2, (
        f"After sequence, AppState.current_system should be {sys2}, "
        f"got {app_state.current_system!r}"
    )


def test_route_manager_autoschowek_integration(ctx: TestContext) -> None:
    """
    Sprawdza prostą integrację:
    - ustawiamy krótką trasę w RouteManagerze,
    - wysyłamy FSDJump z pierwszego systemu,
    - oczekujemy, że current_index w RouteManagerze przesunie się do przodu
      (jak po advance_route) i nie ma wyjątków.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    route = ["SMOKE_T2_ROUTE_A", "SMOKE_T2_ROUTE_B"]
    route_manager.set_route(route, route_type="test")

    # po set_route current_index powinien być 0
    assert route_manager.current_index == 0, (
        f"After set_route, current_index should be 0, got {route_manager.current_index}"
    )

    ev_jump = {
        "event": "FSDJump",
        "StarSystem": route[0],
    }

    handler.handle_event(json.dumps(ev_jump), gui_ref=None)
    msgs = ctx.drain_queue()

    # FSDJump powinien przesunąć current_index na 1 (advance_route)
    assert route_manager.current_index == 1, (
        "After FSDJump from first system, RouteManager.current_index should be 1, "
        f"got {route_manager.current_index}"
    )

    joined = " | ".join(str(m) for m in msgs)
    assert (
        "[ROUTE]" in joined
        or "[AUTO-SCHOWEK]" in joined
        or "[PLANNER]" in joined
        or "[CLIPBOARD]" in joined
        or "[OBS][PLANNER]" in joined
        or "[OBS][CLIPBOARD]" in joined
    ), (
        "Expected some route/auto-schowek related logs after FSDJump, "
        f"got: {joined}"
    )


def test_nav_symbiosis_guard_and_desync(ctx: TestContext) -> None:
    """
    TEST-NAV-SYMBIOSIS-01 (techniczny):
    - aligned NavRoute + milestone => brak ROUTE_DESYNC,
    - real off-route => ROUTE_DESYNC (po confirm_jumps),
    - powrót na trasę => kasuje stan desync.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    cfg = config.config._settings  # type: ignore[attr-defined]
    original = {
        "auto_clipboard_mode": cfg.get("auto_clipboard_mode"),
        "auto_clipboard_next_hop_trigger": cfg.get("auto_clipboard_next_hop_trigger"),
        "auto_clipboard_next_hop_resync_policy": cfg.get("auto_clipboard_next_hop_resync_policy"),
        "auto_clipboard_next_hop_desync_confirm_jumps": cfg.get("auto_clipboard_next_hop_desync_confirm_jumps"),
        "features.clipboard.next_hop_stepper": cfg.get("features.clipboard.next_hop_stepper"),
        "route_progress_speech": cfg.get("route_progress_speech"),
    }

    try:
        cfg["auto_clipboard_mode"] = "NEXT_HOP"
        cfg["auto_clipboard_next_hop_trigger"] = "fsdjump"
        cfg["auto_clipboard_next_hop_resync_policy"] = "nearest_forward"
        cfg["auto_clipboard_next_hop_desync_confirm_jumps"] = 1
        cfg["features.clipboard.next_hop_stepper"] = True
        cfg["route_progress_speech"] = True

        route = ["NAV_A", "NAV_B", "NAV_C", "NAV_D", "NAV_E"]
        gui_common._set_active_route_data(route, "dummy", "sig", "smoke.nav")
        app_state.set_spansh_milestones(["NAV_E"], mode="neutron", source="smoke.nav")
        app_state.set_nav_route(endpoint="NAV_E", systems=route, source="smoke.nav")

        # Aligned jump path: no false desync.
        gui_common.update_next_hop_on_system("NAV_B", "fsdjump", source="smoke.nav")
        aligned_msgs = ctx.drain_queue()
        aligned_joined = " | ".join(str(m) for m in aligned_msgs)
        assert "ROUTE_DESYNC" not in aligned_joined, (
            "Aligned NavRoute+milestone should not emit ROUTE_DESYNC; "
            f"got: {aligned_joined}"
        )
        aligned_state = app_state.get_route_awareness_snapshot()
        assert aligned_state.get("route_mode") == "awareness", (
            f"Expected awareness mode after aligned jump, got: {aligned_state}"
        )
        assert not bool(aligned_state.get("is_off_route")), (
            f"Aligned jump should keep on-route state, got: {aligned_state}"
        )

        # Real off-route: should trigger desync.
        ctx.clear_queue()
        gui_common.update_next_hop_on_system("NAV_Z", "fsdjump", source="smoke.nav")
        off_msgs = ctx.drain_queue()
        off_joined = " | ".join(str(m) for m in off_msgs)
        assert "ROUTE_DESYNC" in off_joined, (
            "Real off-route should emit ROUTE_DESYNC; "
            f"got: {off_joined}"
        )
        off_state = app_state.get_route_awareness_snapshot()
        assert bool(off_state.get("is_off_route")), (
            f"Off-route jump should set is_off_route=True, got: {off_state}"
        )

        # Return to route clears desync state and resumes progression.
        ctx.clear_queue()
        gui_common.update_next_hop_on_system("NAV_C", "fsdjump", source="smoke.nav")
        back_msgs = ctx.drain_queue()
        back_joined = " | ".join(str(m) for m in back_msgs)
        assert "ROUTE_DESYNC" not in back_joined, (
            "Back on route should not re-emit ROUTE_DESYNC; "
            f"got: {back_joined}"
        )
        assert not bool(getattr(gui_common, "_ACTIVE_ROUTE_DESYNC_ACTIVE", True)), (
            "Desync flag should be cleared after returning to route"
        )
        back_state = app_state.get_route_awareness_snapshot()
        assert back_state.get("route_mode") == "awareness", (
            f"Expected awareness mode after returning to route, got: {back_state}"
        )
        assert not bool(back_state.get("is_off_route")), (
            f"Returning to route should clear off-route state, got: {back_state}"
        )
        assert int(back_state.get("route_progress_percent") or 0) >= 25, (
            f"Expected progress update after returning to route, got: {back_state}"
        )
    finally:
        for key, value in original.items():
            cfg[key] = value
        try:
            app_state.clear_spansh_milestones(source="smoke.nav.cleanup")
            app_state.clear_nav_route(source="smoke.nav.cleanup")
        except Exception:
            pass


def test_journal_f3_exobio_progress_no_flood(ctx: TestContext) -> None:
    """
    F3 journal gate:
    - ScanOrganic 1/2/3 emit expected progression,
    - 4th ScanOrganic for same body/species stays silent,
    - CodexEntry new entry is deduped for same (system, species).
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    bio_events.reset_bio_flags()

    system_name = "SMOKE_T2_F3_EXOBIO_SYS"
    body_name = "SMOKE_T2_F3_EXOBIO_BODY"
    species_name = "Aleoida Arcus"

    events = [
        {"event": "Location", "StarSystem": system_name},
        {
            "event": "ScanOrganic",
            "StarSystem": system_name,
            "BodyName": body_name,
            "Species_Localised": species_name,
        },
        {
            "event": "ScanOrganic",
            "StarSystem": system_name,
            "BodyName": body_name,
            "Species_Localised": species_name,
        },
        {
            "event": "ScanOrganic",
            "StarSystem": system_name,
            "BodyName": body_name,
            "Species_Localised": species_name,
        },
        {
            "event": "ScanOrganic",
            "StarSystem": system_name,
            "BodyName": body_name,
            "Species_Localised": species_name,
        },
        {
            "event": "CodexEntry",
            "StarSystem": system_name,
            "BodyName": body_name,
            "Category": "Biology",
            "IsNewEntry": True,
            "Name_Localised": "Cactoida Cortexum",
        },
        {
            "event": "CodexEntry",
            "StarSystem": system_name,
            "BodyName": body_name,
            "Category": "Biology",
            "IsNewEntry": True,
            "Name_Localised": "Cactoida Cortexum",
        },
    ]

    for ev in events:
        handler.handle_event(json.dumps(ev), gui_ref=None)

    joined = " | ".join(str(m) for m in ctx.drain_queue()).lower()
    assert joined.count("pierwsza próbka aleoida arcus pobrana.") == 1, (
        "Expected one first-sample callout in journal F3 exobio scenario"
    )
    assert joined.count("druga próbka aleoida arcus pobrana.") == 1, (
        "Expected one second-sample callout in journal F3 exobio scenario"
    )
    assert joined.count("mamy wszystko dla aleoida arcus.") == 1, (
        "Expected one completion callout in journal F3 exobio scenario"
    )
    assert joined.count("nowy wpis biologiczny. cactoida cortexum.") == 1, (
        "Expected one deduped codex callout in journal F3 exobio scenario"
    )


def test_journal_f4_survival_no_rebuy_nonflood(ctx: TestContext) -> None:
    """
    F4 journal gate:
    - repeated no-rebuy journal payload should emit survival insight only once per signature,
    - payload should be critical with reason no_rebuy.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_T2_F4_SURVIVAL_SYS"
    app_state.last_survival_rebuy_signature = None
    survival_events.reset_survival_rebuy_state()

    no_rebuy = {
        "event": "LoadGame",
        "StarSystem": "SMOKE_T2_F4_SURVIVAL_SYS",
        "Credits": 100_000,
        "Rebuy": 850_000,
    }
    handler.handle_event(json.dumps(no_rebuy), gui_ref=None)
    handler.handle_event(json.dumps(no_rebuy), gui_ref=None)

    batch = ctx.drain_queue()
    survival_payloads = [
        item[1]
        for item in batch
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "survival_rebuy"
    ]
    assert len(survival_payloads) == 1, (
        "Expected one survival payload in no-rebuy non-flood scenario, "
        f"got: {survival_payloads}"
    )
    payload = survival_payloads[-1] or {}
    assert payload.get("level") == "critical", f"Expected critical survival payload, got: {payload}"
    assert payload.get("reason") == "no_rebuy", f"Expected no_rebuy reason, got: {payload}"


def test_journal_f5_combat_awareness_nonflood(ctx: TestContext) -> None:
    """
    F5 journal/status gate:
    - repeated combat pattern update should emit one combat payload per pattern/session.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_T2_F5_COMBAT_SYS"
    app_state.last_combat_awareness_signature = None
    combat_events.reset_combat_awareness_state()

    status = {
        "StarSystem": "SMOKE_T2_F5_COMBAT_SYS",
        "InDanger": True,
        "Hull": 0.18,
        "ShieldsUp": False,
    }
    handler.on_status_update(status, gui_ref=None)
    handler.on_status_update(status, gui_ref=None)

    batch = ctx.drain_queue()
    combat_payloads = [
        item[1]
        for item in batch
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "combat_awareness"
    ]
    assert len(combat_payloads) == 1, (
        "Expected one combat payload in non-flood scenario, "
        f"got: {combat_payloads}"
    )
    payload = combat_payloads[-1] or {}
    assert payload.get("level") == "critical", f"Expected critical combat payload, got: {payload}"
    assert payload.get("pattern_id") == "combat_hull_critical", (
        f"Expected combat_hull_critical pattern, got: {payload}"
    )


def test_journal_f5_anti_spam_transitions_and_exceptions(ctx: TestContext) -> None:
    """
    F5 anti-spam integration:
    - EXOBIO READY blocked in combat should retry once after leaving combat,
    - READY should not flood after successful emit,
    - fuel critical should still trigger in combat and remain non-flood.
    """
    settings = config.config._settings  # type: ignore[attr-defined]
    saved_survival_enabled = settings.get("survival_rebuy_awareness_enabled")
    saved_combat_enabled = settings.get("combat_awareness_enabled")
    settings["survival_rebuy_awareness_enabled"] = False
    settings["combat_awareness_enabled"] = False

    try:
        ctx.clear_queue()
        ctx.reset_debouncer()
        reset_dispatcher_runtime_state()
        app_state.current_system = "SMOKE_T2_F5_ANTI_SPAM_SYS"
        app_state.last_combat_awareness_signature = None
        combat_events.reset_combat_awareness_state()
        app_state.last_survival_rebuy_signature = None
        survival_events.reset_survival_rebuy_state()
        bio_events.reset_bio_flags()
        fuel_events.LOW_FUEL_WARNED = False  # type: ignore[attr-defined]
        fuel_events.LOW_FUEL_FLAG_PENDING = False  # type: ignore[attr-defined]
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = 0.0  # type: ignore[attr-defined]

        key = ("smoke_t2_f5_anti_spam_sys", "smoke_t2_f5_anti_spam_body", "aleoida arcus")
        bio_events.EXOBIO_SAMPLE_COUNT[key] = 1
        bio_events.EXOBIO_RANGE_TRACKERS[key] = {
            "lat": 0.0,
            "lon": 0.0,
            "radius_m": 6_371_000.0,
            "threshold_m": 100.0,
            "pending": False,
            "body": "smoke_t2_f5_anti_spam_body",
            "system": "smoke_t2_f5_anti_spam_sys",
        }

        handler.on_status_update(
            {
                "StarSystem": "SMOKE_T2_F5_ANTI_SPAM_SYS",
                "BodyName": "SMOKE_T2_F5_ANTI_SPAM_BODY",
                "Latitude": 0.0,
                "Longitude": 0.002,
                "PlanetRadius": 6_371_000.0,
                "in_combat": True,
                "LowFuel": False,
            },
            gui_ref=None,
        )
        assert key not in bio_events.EXOBIO_RANGE_READY_WARNED, (
            "READY should not be latched when blocked by combat silence"
        )

        handler.on_status_update(
            {
                "StarSystem": "SMOKE_T2_F5_ANTI_SPAM_SYS",
                "BodyName": "SMOKE_T2_F5_ANTI_SPAM_BODY",
                "Latitude": 0.0,
                "Longitude": 0.0022,
                "PlanetRadius": 6_371_000.0,
                "in_combat": False,
                "LowFuel": False,
            },
            gui_ref=None,
        )
        assert key in bio_events.EXOBIO_RANGE_READY_WARNED, "READY should emit once after leaving combat"

        handler.on_status_update(
            {
                "StarSystem": "SMOKE_T2_F5_ANTI_SPAM_SYS",
                "BodyName": "SMOKE_T2_F5_ANTI_SPAM_BODY",
                "Latitude": 0.0,
                "Longitude": 0.0024,
                "PlanetRadius": 6_371_000.0,
                "in_combat": False,
                "LowFuel": False,
            },
            gui_ref=None,
        )
        assert key in bio_events.EXOBIO_RANGE_READY_WARNED, "READY should stay non-flood after successful emit"

        handler.on_status_update(
            {
                "StarSystem": "SMOKE_T2_F5_ANTI_SPAM_SYS",
                "in_combat": True,
                "Fuel": {"FuelMain": 0.05},
                "FuelCapacity": {"Main": 10.0},
                "LowFuel": True,
            },
            gui_ref=None,
        )
        handler.on_status_update(
            {
                "StarSystem": "SMOKE_T2_F5_ANTI_SPAM_SYS",
                "in_combat": True,
                "Fuel": {"FuelMain": 0.05},
                "FuelCapacity": {"Main": 10.0},
                "LowFuel": True,
            },
            gui_ref=None,
        )

        joined = " | ".join(str(item) for item in ctx.drain_queue()).lower()
        assert joined.count("warning. fuel reserves critical.") == 1, (
            "Fuel critical should trigger once and stay non-flood in repeated combat status updates"
        )
    finally:
        settings["survival_rebuy_awareness_enabled"] = saved_survival_enabled
        settings["combat_awareness_enabled"] = saved_combat_enabled


def test_journal_f5_quality_gates_cross_module_nonflood(ctx: TestContext) -> None:
    """
    F5 quality-gates journal smoke:
    - repeated no-rebuy emits one survival payload,
    - repeated combat critical emits one combat payload,
    - both payload streams coexist without cross-module flood.
    """
    settings = config.config._settings  # type: ignore[attr-defined]
    saved_survival_enabled = settings.get("survival_rebuy_awareness_enabled")
    saved_combat_enabled = settings.get("combat_awareness_enabled")
    settings["survival_rebuy_awareness_enabled"] = True
    settings["combat_awareness_enabled"] = True

    try:
        ctx.clear_queue()
        ctx.reset_debouncer()
        reset_dispatcher_runtime_state()
        app_state.current_system = "SMOKE_T2_F5_QUALITY_SYS"
        app_state.last_survival_rebuy_signature = None
        app_state.last_combat_awareness_signature = None
        survival_events.reset_survival_rebuy_state()
        combat_events.reset_combat_awareness_state()

        no_rebuy = {
            "event": "LoadGame",
            "StarSystem": "SMOKE_T2_F5_QUALITY_SYS",
            "Credits": 100_000,
            "Rebuy": 900_000,
        }
        handler.handle_event(json.dumps(no_rebuy), gui_ref=None)
        handler.handle_event(json.dumps(no_rebuy), gui_ref=None)

        survival_batch = ctx.drain_queue()
        survival_payloads = [
            item[1]
            for item in survival_batch
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "survival_rebuy"
        ]
        assert len(survival_payloads) == 1, (
            "Expected one survival payload in quality gate scenario, "
            f"got: {survival_payloads}"
        )
        survival_payload = survival_payloads[-1] or {}
        assert survival_payload.get("reason") == "no_rebuy", (
            f"Expected no_rebuy survival reason, got: {survival_payload}"
        )

        settings["survival_rebuy_awareness_enabled"] = False
        ctx.clear_queue()

        critical_status = {
            "StarSystem": "SMOKE_T2_F5_QUALITY_SYS",
            "InDanger": True,
            "Hull": 0.18,
            "ShieldsUp": False,
        }
        handler.on_status_update(critical_status, gui_ref=None)
        handler.on_status_update(critical_status, gui_ref=None)

        batch = ctx.drain_queue()
        combat_payloads = [
            item[1]
            for item in batch
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "combat_awareness"
        ]
        assert len(combat_payloads) == 1, (
            "Expected one combat payload in cross-module quality gate scenario, "
            f"got: {combat_payloads}"
        )
        combat_payload = combat_payloads[-1] or {}
        assert combat_payload.get("pattern_id") == "combat_hull_critical", (
            f"Expected combat_hull_critical payload, got: {combat_payload}"
        )
    finally:
        settings["survival_rebuy_awareness_enabled"] = saved_survival_enabled
        settings["combat_awareness_enabled"] = saved_combat_enabled


def test_journal_f11_startjump_cash_in_nonflood(ctx: TestContext) -> None:
    """
    F11 journal smoke:
    - StartJump (Hyperspace) emituje cash-in callout,
    - drugi identyczny event jest stlumiony przez anti-spam.
    """
    settings = config.config._settings  # type: ignore[attr-defined]
    saved_startjump_enabled = settings.get("cash_in.startjump_callout_enabled")
    saved_startjump_cd = settings.get("cash_in.startjump_callout_cooldown_sec")
    saved_system = str(getattr(app_state, "current_system", "") or "")

    try:
        settings["cash_in.startjump_callout_enabled"] = True
        settings["cash_in.startjump_callout_cooldown_sec"] = 35.0
        ctx.clear_queue()
        ctx.reset_debouncer()
        reset_dispatcher_runtime_state()
        app_state.current_system = "SMOKE_T2_F11_STARTJUMP_SYS"

        startjump_line = json.dumps(
            {
                "event": "StartJump",
                "JumpType": "Hyperspace",
                "StarSystem": "SMOKE_T2_F11_STARTJUMP_SYS",
            }
        )
        with (
            patch.object(
                app_state.exit_summary,
                "build_summary_data",
                return_value=ExitSummaryData(
                    system_name="SMOKE_T2_F11_STARTJUMP_SYS",
                    total_value=5_000_000.0,
                ),
            ),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 16_000_000.0}),
            ),
        ):
            handler.handle_event(startjump_line, gui_ref=None)
            handler.handle_event(startjump_line, gui_ref=None)

        logs = [
            str(item[1] or "")
            for item in ctx.drain_queue()
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "log"
        ]
        callouts = [line for line in logs if "Cash-in:" in line]
        assert len(callouts) == 1, (
            "Expected one StartJump cash-in callout in nonflood journal scenario, "
            f"got: {callouts}"
        )
    finally:
        settings["cash_in.startjump_callout_enabled"] = saved_startjump_enabled
        settings["cash_in.startjump_callout_cooldown_sec"] = saved_startjump_cd
        app_state.current_system = saved_system


def test_journal_f12_cross_system_cash_in_route_gate(ctx: TestContext) -> None:
    """
    F12 journal smoke:
    - expedition case: brak lokalnego UC, cross-system daje realny target i handoff jest OK,
    - provider-empty case: fallback orientacyjny i handoff zablokowany.
    """
    settings = config.config._settings  # type: ignore[attr-defined]
    saved_system = str(getattr(app_state, "current_system", "") or "")
    saved_station = str(getattr(app_state, "current_station", "") or "")
    saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
    saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
    saved_lookup_enabled = settings.get("cash_in.station_candidates_lookup_enabled")
    saved_cross_enabled = settings.get("cash_in.cross_system_discovery_enabled")
    saved_edsm_enabled = settings.get("features.providers.edsm_enabled")
    saved_system_lookup = settings.get("features.providers.system_lookup_online")
    saved_station_lookup = settings.get("features.trade.station_lookup_online")
    saved_cross_radius = settings.get("cash_in.cross_system_radius_ly")
    saved_cross_max = settings.get("cash_in.cross_system_max_systems")
    saved_swr_enabled = settings.get("cash_in.swr_cache_enabled")
    saved_local_fallback_enabled = settings.get("cash_in.local_known_fallback_enabled")

    try:
        settings["cash_in.station_candidates_lookup_enabled"] = True
        settings["cash_in.cross_system_discovery_enabled"] = True
        settings["features.providers.edsm_enabled"] = True
        settings["features.providers.system_lookup_online"] = True
        settings["features.trade.station_lookup_online"] = True
        settings["cash_in.cross_system_radius_ly"] = 120.0
        settings["cash_in.cross_system_max_systems"] = 8
        settings["cash_in.swr_cache_enabled"] = False
        settings["cash_in.local_known_fallback_enabled"] = False

        ctx.clear_queue()
        ctx.reset_debouncer()
        reset_dispatcher_runtime_state()
        app_state.current_system = "SMOKE_T2_F12_ORIGIN_SYS"
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        cash_in_events._reset_cash_in_swr_cache_for_tests()
        cash_in_events._reset_cash_in_local_known_cache_for_tests()

        payload = {
            "system": "SMOKE_T2_F12_ORIGIN_SYS",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 6_400_000.0,
            "cash_in_session_estimated": 22_500_000.0,
            "confidence": "high",
            "service": "uc",
        }

        local_no_service = [
            {
                "name": "SMOKE_T2_F12_LOCAL_ONLY_VISTA",
                "system_name": "SMOKE_T2_F12_ORIGIN_SYS",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 0.5,
                "source": "EDSM",
            }
        ]
        cross_candidates = [
            {
                "name": "SMOKE_T2_F12_REMOTE_UC",
                "system_name": "SMOKE_T2_F12_REMOTE_SYS",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 41.0,
                "distance_ls": 1200.0,
                "source": "EDSM",
            }
        ]

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=local_no_service,
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=(cross_candidates, {"systems_requested": 3, "systems_with_candidates": 1}),
            ),
        ):
            ok = cash_in_events.trigger_cash_in_assistant(mode="manual", summary_payload=payload, gui_ref=None)
        assert ok is True, "Expected cross-system cash-in emit in journal smoke"

        queue_batch = ctx.drain_queue()
        payload_items = [
            item[1]
            for item in queue_batch
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "cash_in_assistant"
        ]
        assert payload_items, "Expected structured cash_in_assistant payload in journal smoke"
        structured = dict(payload_items[-1] or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        assert str(station_meta.get("cross_system_lookup_status") or "") == "cross_system", (
            f"Expected cross_system status in journal smoke, got: {station_meta}"
        )

        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        assert options, "Expected cash-in options in journal smoke expedition case"
        selected = dict(options[0])
        handoff = cash_in_events.handoff_cash_in_to_route_intent(
            selected,
            set_route_intent=app_state.set_route_intent,
            source="smoke.t2.f12.intent",
            allow_auto_route=False,
        )
        assert bool(handoff.get("ok")), f"Expected route handoff for cross-system target, got: {handoff}"
        assert str(handoff.get("target_system") or "") == "SMOKE_T2_F12_REMOTE_SYS", (
            f"Expected remote target system, got: {handoff}"
        )

        ctx.clear_queue()
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=([], {"systems_requested": 4, "systems_with_candidates": 0}),
            ),
        ):
            ok_empty = cash_in_events.trigger_cash_in_assistant(
                mode="manual",
                summary_payload={
                    "system": "SMOKE_T2_F12_ORIGIN_SYS",
                    "cash_in_signal": "sredni",
                    "cash_in_system_estimated": 1_900_000.0,
                    "cash_in_session_estimated": 8_200_000.0,
                    "confidence": "high",
                    "service": "uc",
                },
                gui_ref=None,
            )
        assert ok_empty is True, "Expected orientational cash-in emit for provider-empty journal case"

        queue_batch = ctx.drain_queue()
        payload_items = [
            item[1]
            for item in queue_batch
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "cash_in_assistant"
        ]
        assert payload_items, "Expected provider-empty payload in journal smoke"
        structured = dict(payload_items[-1] or {})
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        assert options, "Expected fallback options for provider-empty journal case"
        blocked = cash_in_events.handoff_cash_in_to_route_intent(
            dict(options[0]),
            set_route_intent=app_state.set_route_intent,
            source="smoke.t2.f12.intent.blocked",
            allow_auto_route=False,
        )
        assert bool(blocked.get("ok")) is False, (
            f"Expected blocked handoff without real target in journal smoke, got: {blocked}"
        )
        assert str(blocked.get("reason") or "") == "target_missing_system", (
            f"Expected target_missing_system for blocked handoff, got: {blocked}"
        )
    finally:
        settings["cash_in.station_candidates_lookup_enabled"] = saved_lookup_enabled
        settings["cash_in.cross_system_discovery_enabled"] = saved_cross_enabled
        settings["features.providers.edsm_enabled"] = saved_edsm_enabled
        settings["features.providers.system_lookup_online"] = saved_system_lookup
        settings["features.trade.station_lookup_online"] = saved_station_lookup
        settings["cash_in.cross_system_radius_ly"] = saved_cross_radius
        settings["cash_in.cross_system_max_systems"] = saved_cross_max
        settings["cash_in.swr_cache_enabled"] = saved_swr_enabled
        settings["cash_in.local_known_fallback_enabled"] = saved_local_fallback_enabled
        app_state.current_system = saved_system
        app_state.current_station = saved_station
        app_state.last_cash_in_signature = saved_last_sig
        app_state.cash_in_skip_signature = saved_skip_sig
        cash_in_events._reset_cash_in_swr_cache_for_tests()
        cash_in_events._reset_cash_in_local_known_cache_for_tests()


def test_journal_f13_provider_resilience_fallback_matrix(ctx: TestContext) -> None:
    """
    F13 journal smoke:
    - outage 503 + stale SWR fallback daje jawne reasony i niska confidence,
    - providers-empty + local-known fallback daje jawny status local fallback.
    """
    settings = config.config._settings  # type: ignore[attr-defined]
    saved_system = str(getattr(app_state, "current_system", "") or "")
    saved_station = str(getattr(app_state, "current_station", "") or "")
    saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
    saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
    saved_lookup_enabled = settings.get("cash_in.station_candidates_lookup_enabled")
    saved_cross_enabled = settings.get("cash_in.cross_system_discovery_enabled")
    saved_edsm_enabled = settings.get("features.providers.edsm_enabled")
    saved_station_lookup = settings.get("features.trade.station_lookup_online")
    saved_swr_enabled = settings.get("cash_in.swr_cache_enabled")
    saved_swr_fresh_ttl = settings.get("cash_in.swr_cache_fresh_ttl_sec")
    saved_swr_stale_ttl = settings.get("cash_in.swr_cache_stale_ttl_sec")
    saved_local_enabled = settings.get("cash_in.local_known_fallback_enabled")

    try:
        settings["cash_in.station_candidates_lookup_enabled"] = True
        settings["cash_in.cross_system_discovery_enabled"] = False
        settings["features.providers.edsm_enabled"] = True
        settings["features.trade.station_lookup_online"] = False
        settings["cash_in.swr_cache_enabled"] = True
        settings["cash_in.swr_cache_fresh_ttl_sec"] = 0.01
        settings["cash_in.swr_cache_stale_ttl_sec"] = 3600.0
        settings["cash_in.local_known_fallback_enabled"] = True

        ctx.clear_queue()
        ctx.reset_debouncer()
        reset_dispatcher_runtime_state()
        app_state.current_system = "SMOKE_T2_F13_SYS"
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        cash_in_events._reset_cash_in_swr_cache_for_tests()
        cash_in_events._reset_cash_in_local_known_cache_for_tests()

        payload = {
            "system": "SMOKE_T2_F13_SYS",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 6_900_000.0,
            "cash_in_session_estimated": 23_100_000.0,
            "confidence": "high",
            "service": "uc",
        }
        seed_rows = [
            {
                "name": "SMOKE_T2_F13_SEED",
                "system_name": "SMOKE_T2_F13_REMOTE",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 27.0,
                "source": "EDSM",
            }
        ]
        snapshot_503 = {
            "provider": "EDSM",
            "endpoints": {
                "station_details": {
                    "circuit_open": False,
                    "last_error_code": 503,
                    "provider_down_503_count": 2,
                },
                "nearby_systems": {
                    "circuit_open": False,
                    "last_error_code": 0,
                    "provider_down_503_count": 0,
                },
            },
        }

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                side_effect=[seed_rows, []],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                side_effect=[{}, snapshot_503],
            ),
        ):
            ok_seed = cash_in_events.trigger_cash_in_assistant(mode="manual", summary_payload=payload, gui_ref=None)
            time.sleep(0.05)
            ok_stale = cash_in_events.trigger_cash_in_assistant(mode="manual", summary_payload=payload, gui_ref=None)
        assert ok_seed is True and ok_stale is True, "Expected stale fallback emits in F13 journal smoke"

        queue_batch = ctx.drain_queue()
        payload_items = [
            item[1]
            for item in queue_batch
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "cash_in_assistant"
        ]
        assert len(payload_items) >= 2, "Expected two payloads for stale fallback scenario"
        stale_payload = dict(payload_items[-1] or {})
        stale_meta = dict(stale_payload.get("station_candidates_meta") or {})
        stale_edge = dict(stale_payload.get("edge_case_meta") or {})
        stale_reasons = {
            str(item).strip().lower()
            for item in (stale_edge.get("reasons") or [])
            if str(item).strip()
        }
        assert bool(stale_meta.get("swr_cache_used")), f"Expected swr cache usage, got: {stale_meta}"
        assert str(stale_meta.get("provider_lookup_status") or "") == "provider_down_503", (
            f"Expected provider_down_503 in stale scenario, got: {stale_meta}"
        )
        assert {"stale_cache", "provider_down_503"}.issubset(stale_reasons), (
            f"Expected stale+503 reasons, got: {stale_edge}"
        )

        ctx.clear_queue()
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        settings["cash_in.swr_cache_enabled"] = False
        cash_in_events._reset_cash_in_swr_cache_for_tests()
        cash_in_events._reset_cash_in_local_known_cache_for_tests()

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                side_effect=[seed_rows, []],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                side_effect=[{}, {}],
            ),
        ):
            ok_local_seed = cash_in_events.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=payload,
                gui_ref=None,
            )
            ok_local = cash_in_events.trigger_cash_in_assistant(mode="manual", summary_payload=payload, gui_ref=None)
        assert ok_local_seed is True and ok_local is True, "Expected local-known fallback emits in F13 journal smoke"

        queue_batch = ctx.drain_queue()
        payload_items = [
            item[1]
            for item in queue_batch
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "cash_in_assistant"
        ]
        assert len(payload_items) >= 2, "Expected two payloads for local-known scenario"
        local_payload = dict(payload_items[-1] or {})
        local_meta = dict(local_payload.get("station_candidates_meta") or {})
        local_edge = dict(local_payload.get("edge_case_meta") or {})
        local_reasons = {
            str(item).strip().lower()
            for item in (local_edge.get("reasons") or [])
            if str(item).strip()
        }
        assert bool(local_meta.get("local_known_fallback_used")), (
            f"Expected local known fallback flag, got: {local_meta}"
        )
        assert str(local_meta.get("source_status") or "") == "local_known_fallback", (
            f"Expected local_known_fallback source, got: {local_meta}"
        )
        assert {"local_known_fallback", "providers_empty"}.issubset(local_reasons), (
            f"Expected local+providers_empty reasons, got: {local_edge}"
        )
    finally:
        settings["cash_in.station_candidates_lookup_enabled"] = saved_lookup_enabled
        settings["cash_in.cross_system_discovery_enabled"] = saved_cross_enabled
        settings["features.providers.edsm_enabled"] = saved_edsm_enabled
        settings["features.trade.station_lookup_online"] = saved_station_lookup
        settings["cash_in.swr_cache_enabled"] = saved_swr_enabled
        settings["cash_in.swr_cache_fresh_ttl_sec"] = saved_swr_fresh_ttl
        settings["cash_in.swr_cache_stale_ttl_sec"] = saved_swr_stale_ttl
        settings["cash_in.local_known_fallback_enabled"] = saved_local_enabled
        app_state.current_system = saved_system
        app_state.current_station = saved_station
        app_state.last_cash_in_signature = saved_last_sig
        app_state.cash_in_skip_signature = saved_skip_sig
        cash_in_events._reset_cash_in_swr_cache_for_tests()
        cash_in_events._reset_cash_in_local_known_cache_for_tests()


# --- RUNNER ------------------------------------------------------------------


TestFunc = Callable[[TestContext], None]
TestSpec = Tuple[str, TestFunc]


def run_all_tests() -> int:
    ctx = TestContext()
    _ensure_voice_disabled()

    tests: List[TestSpec] = [
        ("test_journal_location_and_fsdjump_app_state", test_journal_location_and_fsdjump_app_state),
        ("test_journal_docked_updates_station", test_journal_docked_updates_station),
        ("test_debouncer_basic", test_debouncer_basic),
        ("test_journal_sequence_no_crash", test_journal_sequence_no_crash),
        ("test_route_manager_autoschowek_integration", test_route_manager_autoschowek_integration),
        ("test_nav_symbiosis_guard_and_desync", test_nav_symbiosis_guard_and_desync),
        ("test_journal_f3_exobio_progress_no_flood", test_journal_f3_exobio_progress_no_flood),
        ("test_journal_f4_survival_no_rebuy_nonflood", test_journal_f4_survival_no_rebuy_nonflood),
        ("test_journal_f5_combat_awareness_nonflood", test_journal_f5_combat_awareness_nonflood),
        ("test_journal_f5_anti_spam_transitions_and_exceptions", test_journal_f5_anti_spam_transitions_and_exceptions),
        ("test_journal_f5_quality_gates_cross_module_nonflood", test_journal_f5_quality_gates_cross_module_nonflood),
        ("test_journal_f11_startjump_cash_in_nonflood", test_journal_f11_startjump_cash_in_nonflood),
        ("test_journal_f12_cross_system_cash_in_route_gate", test_journal_f12_cross_system_cash_in_route_gate),
        ("test_journal_f13_provider_resilience_fallback_matrix", test_journal_f13_provider_resilience_fallback_matrix),
    ]

    print("=== RenataAI Journal / AppState / Debouncer Tests (T2) ===")
    print(f"Root dir: {ROOT_DIR}")
    print("----------------------------------------------------------")

    passed = 0
    failed = 0

    for name, func in tests:
        print(f"> Running {name} ...", end=" ")
        try:
            func(ctx)
        except AssertionError as e:
            failed += 1
            print("[FAIL]")
            print(f"    AssertionError: {e}")
        except Exception:
            failed += 1
            print("[FAIL]")
            tb = traceback.format_exc()
            for line in tb.splitlines():
                print(f"    {line}")
        else:
            passed += 1
            print("[OK]")

    print("----------------------------------------------------------")
    print(f"Summary: {passed} passed, {failed} failed")

    return 1 if failed else 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
