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
from typing import Callable, List, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config  # type: ignore
from logic.utils import MSG_QUEUE, DEBOUNCER  # type: ignore
from logic.event_handler import handler  # type: ignore
from app.state import app_state  # type: ignore
from app.route_manager import route_manager  # type: ignore


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
    assert f"[STATE] System = {sys_jump}" in joined_jump, (
        "Expected [STATE] System log after FSDJump, "
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
        or "[OBS][PLANNER]" in joined
        or "[OBS][CLIPBOARD]" in joined
    ), (
        "Expected some route/auto-schowek related logs after FSDJump, "
        f"got: {joined}"
    )


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
