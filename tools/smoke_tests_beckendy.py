"""
tools/smoke_tests_beckendy.py

Lekki smoke-test backendu RenataAI (bez pytesta).
Uruchom z katalogu głównego projektu:
    python tools/smoke_tests_beckendy.py
"""

from __future__ import annotations

import os
import sys
import traceback
import queue
import re
import time
import ast
import tempfile
from typing import Callable, List, Tuple
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

# --- ŚCIEŻKI / IMPORTY --------------------------------------------------------


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config  # type: ignore
from logic.utils import MSG_QUEUE, DEBOUNCER  # type: ignore
from logic.utils import notify as notify_module  # type: ignore

from app.state import app_state  # type: ignore
from app.route_manager import route_manager  # type: ignore

from logic.events import fuel_events  # type: ignore
from logic.events import trade_events  # type: ignore
from logic.events import navigation_events  # type: ignore
from logic.events import exploration_fss_events as fss_events  # type: ignore
from logic.events import exploration_bio_events as bio_events  # type: ignore
from logic.events import exploration_dss_events as dss_events  # type: ignore
from logic.events import exploration_misc_events as misc_events  # type: ignore
from logic.events import exploration_awareness as awareness_events  # type: ignore
from logic.events import exploration_summary as summary_events  # type: ignore
from logic.events import cash_in_assistant as cash_in_events  # type: ignore
from logic.events import survival_rebuy_awareness as survival_events  # type: ignore
from logic.events import combat_awareness as combat_events  # type: ignore
from logic import spansh_payloads
from logic import spansh_client as spansh_client_logic  # type: ignore
from logic import neutron as neutron_logic  # type: ignore
from logic import riches as riches_logic  # type: ignore
from logic import ammonia as ammonia_logic  # type: ignore
from logic import elw_route as elw_logic  # type: ignore
from logic import hmc_route as hmc_logic  # type: ignore
from logic import exomastery as exomastery_logic  # type: ignore
from logic import trade as trade_logic  # type: ignore
from logic import cargo_value_estimator  # type: ignore
from logic.rows_normalizer import normalize_trade_rows
from logic.exit_summary import ExitSummaryData
from logic.risk_rebuy_contract import build_risk_rebuy_contract
from logic.tts.text_preprocessor import prepare_tts
from logic.insight_dispatcher import (
    Insight,
    emit_insight,
    pick_insight_for_emit,
    evaluate_risk_trust_gate,
    reset_dispatcher_runtime_state,
    should_speak,
)
from logic.event_insight_mapping import get_insight_class, get_tts_policy_spec, resolve_emit_contract
from logic.entry_repository import EntryRepository
from logic.entry_templates import build_template_entry
from logic.journal_entry_mapping import build_mvp_entry_draft
from logic.journal_navigation import (
    extract_navigation_chips,
    resolve_chip_nav_target,
    resolve_entry_nav_target,
    resolve_entry_nav_target_typed,
    resolve_logbook_nav_target,
)
from logic.logbook_feed import build_logbook_feed_item
from logic.capabilities import (
    CAP_SETTINGS_FULL,
    CAP_TTS_ADVANCED_POLICY,
    CAP_UI_EXTENDED_TABS,
    CAP_VOICE_STT,
    PROFILE_FREE,
    PROFILE_PRO,
    capability_config_patch_from_free_policy,
    has_capability,
    resolve_capabilities,
)
from gui import common_tables  # type: ignore
from gui.tabs.pulpit import PulpitTab  # type: ignore
from gui.tabs.spansh.trade import TradeTab  # type: ignore


# --- POMOCNICZY KONTEKST TESTÓW ----------------------------------------------


class TestContext:
    """
    Prosty kontekst dla smoke-testów.

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


# --- POMOCNICZE FUNKCJE PAYLOAD ----------------------------------------------


def _payload_fields(payload: object) -> dict[str, object]:
    """
    Zwraca slownik pol payloadu.

    Dla kluczy wielokrotnych (np. body_types) zachowuje liste wartosci.
    """
    fields: dict[str, object] = {}
    form_fields = getattr(payload, "form_fields", []) or []
    for key, value in form_fields:
        if key in fields:
            current = fields[key]
            if isinstance(current, list):
                current.append(value)
            else:
                fields[key] = [current, value]
        else:
            fields[key] = value
    return fields


# --- POMOCNICZE FUNKCJE KONFIGURACJI -----------------------------------------


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


# --- TESTY: PALIWO -----------------------------------------------------------


def test_low_fuel_basic(ctx: TestContext) -> None:
    """
    Scenariusz:
    - bezpieczny poziom paliwa -> brak komunikatu LOW_FUEL,
    - niski poziom paliwa -> pojawia się komunikat 'Warning. Fuel reserves critical.'.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    # Upewniamy się, że flaga globalna zaczyna od False
    fuel_events.LOW_FUEL_WARNED = False  # type: ignore[attr-defined]

    # Bezpieczny status (50% paliwa)
    status_safe = {
        "Fuel": {"FuelMain": 0.5},  # heurystyka: 0–1 → 0–100%
        "FuelCapacity": {"Main": 10},
        "Flags": 0,
        "StarSystem": "SMOKE_TEST_SAFE_SYSTEM",
    }

    fuel_events.handle_status_update(status_safe, gui_ref=None)

    # Po bezpiecznym statusie kolejka powinna być pusta
    safe_msgs = ctx.drain_queue()
    assert len(safe_msgs) == 0, f"Expected no LOW_FUEL messages, got: {safe_msgs}"

    # Niski poziom paliwa (5%)
    ctx.clear_queue()
    ctx.reset_debouncer()
    fuel_events.LOW_FUEL_WARNED = False  # type: ignore[attr-defined]

    status_low = {
        "Fuel": {"FuelMain": 0.05},
        "FuelCapacity": {"Main": 10},
        "Flags": 0,
        "StarSystem": "SMOKE_TEST_LOW_FUEL",
    }

    fuel_events.handle_status_update(status_low, gui_ref=None)

    low_msgs = ctx.drain_queue()
    assert len(low_msgs) > 0, "Expected at least one LOW_FUEL message, got none"

    joined = " | ".join(str(m) for m in low_msgs)
    assert "Warning. Fuel reserves critical." in joined, (
        "LOW_FUEL warning text not found in MSG_QUEUE; "
        f"messages: {joined}"
    )


def test_low_fuel_transient_startup_sco_guard(ctx: TestContext) -> None:
    """
    Scenariusz regresyjny:
    - pojedyncza niepewna probka low-fuel (bez FuelCapacity, startup/SCO) nie moze wywolac alertu,
    - probka bezpieczna resetuje pending,
    - kolejna pojedyncza niepewna probka nadal nie moze wywolac alertu.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    fuel_events.LOW_FUEL_WARNED = False  # type: ignore[attr-defined]
    fuel_events.LOW_FUEL_FLAG_PENDING = False  # type: ignore[attr-defined]
    fuel_events.LOW_FUEL_FLAG_PENDING_TS = 0.0  # type: ignore[attr-defined]

    transient_low = {
        "Fuel": {"FuelMain": 0.02},
        "Flags": 0,
        "StarSystem": "SMOKE_TEST_TRANSIENT_LOW",
    }
    fuel_events.handle_status_update(transient_low, gui_ref=None)
    msgs_first = ctx.drain_queue()
    assert len(msgs_first) == 0, (
        "Single uncertain startup/SCO low-fuel sample should not emit alert, "
        f"got: {msgs_first}"
    )

    safe_sample = {
        "Fuel": {"FuelMain": 0.7},
        "FuelCapacity": {"Main": 10},
        "Flags": 0,
        "StarSystem": "SMOKE_TEST_TRANSIENT_LOW",
    }
    fuel_events.handle_status_update(safe_sample, gui_ref=None)
    msgs_safe = ctx.drain_queue()
    assert len(msgs_safe) == 0, f"Safe sample should not emit alert, got: {msgs_safe}"

    fuel_events.handle_status_update(transient_low, gui_ref=None)
    msgs_second = ctx.drain_queue()
    assert len(msgs_second) == 0, (
        "Another single uncertain startup/SCO low-fuel sample should still not emit alert, "
        f"got: {msgs_second}"
    )


# --- TESTY: MAKLER PRO / JACKPOT ---------------------------------------------


def test_trade_jackpot_basic(ctx: TestContext) -> None:
    """
    Scenariusz:
    - Market.json bez jackpota -> brak komunikatów,
    - Market.json z ceną poniżej progu -> komunikat powiedz() + log [MAKLER PRO].
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    # Progi z configa
    thresholds_cfg = config.get("jackpot_thresholds", {})
    if not thresholds_cfg:
        raise AssertionError("Brak skonfigurowanych jackpot_thresholds w configu")

    # Bierzemy pierwszy z progów
    item_name, jackpot_threshold = next(iter(thresholds_cfg.items()))
    item_name = str(item_name)
    jackpot_threshold = int(jackpot_threshold)

    # trade_jackpot_speech domyślnie True w DEFAULT_SETTINGS, ale ustawiamy
    try:
        live_settings = config.config._settings  # type: ignore[attr-defined]
        if isinstance(live_settings, dict):
            live_settings["trade_jackpot_speech"] = True
            live_settings["jackpot_thresholds"] = thresholds_cfg
    except Exception:
        pass

    # Reset stanów globalnych Maklera PRO
    trade_events.JACKPOT_WARNED_STATIONS = set()  # type: ignore[attr-defined]
    trade_events.JACKPOT_CACHE = set()  # type: ignore[attr-defined]

    app_state.current_system = "SMOKE_TEST_JACKPOT_SYSTEM"

    # 1) Brak jackpota – cena powyżej progu
    data_no = {
        "event": "Market",
        "StationName": "SMOKE_TEST_STATION_NO",
        "StarSystem": app_state.current_system,
        "Items": [
            {
                "Name": item_name,
                "Stock": 100,
                "BuyPrice": jackpot_threshold + 100,
            }
        ],
    }

    trade_events.handle_market_data(data_no, gui_ref=None)
    msgs_no = ctx.drain_queue()
    joined_no = " | ".join(str(m) for m in msgs_no)
    assert "[MAKLER PRO]" not in joined_no, (
        "Expected no MAKLER PRO jackpot message for non-jackpot market, "
        f"got: {joined_no}"
    )

    # 2) Jackpot – cena poniżej progu
    ctx.clear_queue()
    trade_events.JACKPOT_WARNED_STATIONS = set()  # type: ignore[attr-defined]
    trade_events.JACKPOT_CACHE = set()  # type: ignore[attr-defined]

    data_yes = {
        "event": "Market",
        "StationName": "SMOKE_TEST_STATION_JACKPOT",
        "StarSystem": app_state.current_system,
        "Items": [
            {
                "Name": item_name,
                "Stock": 100,
                "BuyPrice": jackpot_threshold - 1,
            }
        ],
    }

    trade_events.handle_market_data(data_yes, gui_ref=None)
    msgs_yes = ctx.drain_queue()
    assert len(msgs_yes) > 0, "Expected some messages for jackpot scenario, got none"

    joined_yes = " | ".join(str(m) for m in msgs_yes)
    assert "[MAKLER PRO]" in joined_yes, (
        "Expected MAKLER PRO jackpot log in MSG_QUEUE, "
        f"got: {joined_yes}"
    )


# --- TESTY: FSS PROGRES ------------------------------------------------------


def test_fss_progress_basic(ctx: TestContext) -> None:
    """
    Scenariusz:
    - mały system 4 ciał,
    - FSSDiscoveryScan ustawia BodyCount,
    - kolejne Scan-y powinny wywołać progi FSS + inne komunikaty,
    - na końcu FSSAllBodiesFound nie rzuca wyjątków.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    # Reset stanów eksploracyjnych
    fss_events.reset_fss_progress()
    app_state.current_system = "SMOKE_TEST_FSS_SYSTEM"

    # FSSDiscoveryScan – ustawienie liczby ciał
    ev_discovery = {
        "event": "FSSDiscoveryScan",
        "BodyCount": 4,
        "SystemName": app_state.current_system,
    }
    fss_events.handle_fss_discovery_scan(ev_discovery, gui_ref=None)

    # 4 różne ciała – za każdym razem WasDiscovered=False (first discovery)
    for idx in range(4):
        ev_scan = {
            "event": "Scan",
            "BodyName": f"SMOKE_TEST_BODY_{idx + 1}",
            "WasDiscovered": False,
        }
        fss_events.handle_scan(ev_scan, gui_ref=None)

    # Na koniec FSSAllBodiesFound
    ev_all = {
        "event": "FSSAllBodiesFound",
        "SystemName": app_state.current_system,
    }
    fss_events.handle_fss_all_bodies_found(ev_all, gui_ref=None)

    msgs = ctx.drain_queue()
    assert len(msgs) > 0, "Expected some FSS-related messages, got none"

    joined = " | ".join(str(m) for m in msgs)
    expected_fragments = [
        "Dwadzieścia pięć procent systemu przeskanowane.",
        "Połowa systemu przeskanowana.",
        "Siedemdziesiąt pięć procent systemu przeskanowane.",
        "Ostatnia planeta do skanowania.",
        "System w pełni przeskanowany.",
    ]
    assert any(fragment in joined for fragment in expected_fragments), (
        "Expected at least one FSS progress message in MSG_QUEUE, "
        f"got: {joined}"
    )


def test_fss_last_body_before_full_9_of_10(ctx: TestContext) -> None:
    """
    Last-body must fire on 9/10, and full-scan on 10/10.
    Last-body must NOT be emitted at 10/10.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    fss_events.reset_fss_progress()
    app_state.current_system = "SMOKE_TEST_FSS_9_10"

    fss_events.handle_fss_discovery_scan(
        {"event": "FSSDiscoveryScan", "BodyCount": 10, "SystemName": app_state.current_system},
        gui_ref=None,
    )

    for idx in range(8):
        fss_events.handle_scan(
            {"event": "Scan", "BodyName": f"SMOKE_TEST_9_10_BODY_{idx + 1}", "WasDiscovered": False},
            gui_ref=None,
        )
    ctx.clear_queue()

    fss_events.handle_scan(
        {"event": "Scan", "BodyName": "SMOKE_TEST_9_10_BODY_9", "WasDiscovered": False},
        gui_ref=None,
    )
    msgs_9 = " | ".join(str(m) for m in ctx.drain_queue())
    assert "Ostatnia planeta do skanowania." in msgs_9, "Expected last-body callout on 9/10"
    assert "System w peĹ‚ni przeskanowany." not in msgs_9, "Full-scan must not fire on 9/10"

    fss_events.handle_scan(
        {"event": "Scan", "BodyName": "SMOKE_TEST_9_10_BODY_10", "WasDiscovered": False},
        gui_ref=None,
    )
    msgs_10 = " | ".join(str(m) for m in ctx.drain_queue())
    lower_10 = msgs_10.lower()
    assert "system" in lower_10 and "przeskanowany" in lower_10, "Expected full-scan callout on 10/10"
    assert "Ostatnia planeta do skanowania." not in msgs_10, "Last-body must not be emitted at 10/10"


def test_fss_last_body_before_full_11_of_12(ctx: TestContext) -> None:
    """
    Last-body must fire on 11/12, and full-scan on 12/12.
    This path uses only Scan fallback (without FSSAllBodiesFound).
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    fss_events.reset_fss_progress()
    app_state.current_system = "SMOKE_TEST_FSS_11_12"

    fss_events.handle_fss_discovery_scan(
        {"event": "FSSDiscoveryScan", "BodyCount": 12, "SystemName": app_state.current_system},
        gui_ref=None,
    )

    for idx in range(10):
        fss_events.handle_scan(
            {"event": "Scan", "BodyName": f"SMOKE_TEST_11_12_BODY_{idx + 1}", "WasDiscovered": False},
            gui_ref=None,
        )
    ctx.clear_queue()

    fss_events.handle_scan(
        {"event": "Scan", "BodyName": "SMOKE_TEST_11_12_BODY_11", "WasDiscovered": False},
        gui_ref=None,
    )
    msgs_11 = " | ".join(str(m) for m in ctx.drain_queue())
    assert "Ostatnia planeta do skanowania." in msgs_11, "Expected last-body callout on 11/12"
    assert "System w peĹ‚ni przeskanowany." not in msgs_11, "Full-scan must not fire on 11/12"

    fss_events.handle_scan(
        {"event": "Scan", "BodyName": "SMOKE_TEST_11_12_BODY_12", "WasDiscovered": False},
        gui_ref=None,
    )
    msgs_12 = " | ".join(str(m) for m in ctx.drain_queue())
    lower_12 = msgs_12.lower()
    assert "system" in lower_12 and "przeskanowany" in lower_12, "Expected full-scan callout on 12/12"
    assert "Ostatnia planeta do skanowania." not in msgs_12, "Last-body must not be emitted at 12/12"


# --- TESTY: BIO / DSS SYGNAŁY ------------------------------------------------


def test_bio_signals_basic(ctx: TestContext) -> None:
    """
    Scenariusz:
    - SAASignalsFound z >=3 sygnałami biological -> komunikat powiedz(),
    - powtórzenie eventu na tym samym ciele -> drugi raz cicho (anty-spam).
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    bio_events.reset_bio_flags()

    ev_bio = {
        "event": "SAASignalsFound",
        "BodyName": "SMOKE_TEST_BIO_BODY",
        "Signals": [
            {"Type": "Biological", "Count": 2},
            {"Type": "Biological", "Count": 2},
        ],
    }

    # Pierwsze wywołanie – oczekujemy komunikatu
    bio_events.handle_dss_bio_signals(ev_bio, gui_ref=None)
    msgs_first = ctx.drain_queue()
    assert len(msgs_first) > 0, "Expected bio assistant message on first call, got none"

    joined_first = " | ".join(str(m) for m in msgs_first)
    assert "sygnały biologiczne" in joined_first, (
        "Expected biological signals message text in first call, "
        f"got: {joined_first}"
    )

    # Drugie wywołanie – ten sam body -> powinno być cicho
    ctx.clear_queue()
    bio_events.handle_dss_bio_signals(ev_bio, gui_ref=None)
    msgs_second = ctx.drain_queue()
    assert len(msgs_second) == 0, (
        "Expected no additional bio messages on second call for same body, "
        f"got: {msgs_second}"
    )


def test_dss_helper_completion_basic(ctx: TestContext) -> None:
    """
    DSS helper smoke:
    - SAAScanComplete -> completion callout,
    - sparse progress milestones (1/3/5),
    - no completion duplicates for the same body.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    dss_events.reset_dss_helper_state()

    dss_events.handle_dss_scan_complete(
        {
            "event": "SAAScanComplete",
            "StarSystem": "SMOKE_DSS_SYSTEM",
            "BodyName": "SMOKE_DSS_BODY_1",
            "ProbesUsed": 5,
            "EfficiencyTarget": 6,
            "WasMapped": False,
        },
        gui_ref=None,
    )
    msgs_first = " | ".join(str(m) for m in ctx.drain_queue())
    assert "Mapowanie DSS ukonczone" in msgs_first, "Missing DSS completion callout for first body"
    assert "Pierwsze mapowanie DSS" in msgs_first, "Missing DSS progress milestone for first body"
    assert "first mapped" in msgs_first.lower(), "Missing first mapped confirmation on explicit WasMapped=False"

    ctx.clear_queue()
    dss_events.handle_dss_scan_complete(
        {
            "event": "SAAScanComplete",
            "StarSystem": "SMOKE_DSS_SYSTEM",
            "BodyName": "SMOKE_DSS_BODY_1",
            "ProbesUsed": 5,
            "EfficiencyTarget": 6,
            "WasMapped": False,
        },
        gui_ref=None,
    )
    assert len(ctx.drain_queue()) == 0, "Duplicate SAAScanComplete for same body should stay silent"

    ctx.clear_queue()
    dss_events.handle_dss_scan_complete(
        {
            "event": "SAAScanComplete",
            "StarSystem": "SMOKE_DSS_SYSTEM",
            "BodyName": "SMOKE_DSS_BODY_2",
            "ProbesUsed": 7,
            "EfficiencyTarget": 6,
            "WasMapped": True,
        },
        gui_ref=None,
    )
    dss_events.handle_dss_scan_complete(
        {
            "event": "SAAScanComplete",
            "StarSystem": "SMOKE_DSS_SYSTEM",
            "BodyName": "SMOKE_DSS_BODY_3",
            "ProbesUsed": 8,
            "EfficiencyTarget": 6,
            "WasMapped": True,
        },
        gui_ref=None,
    )
    msgs_more = " | ".join(str(m) for m in ctx.drain_queue())
    assert "Zmapowano DSS 3 cial" in msgs_more, "Missing DSS progress milestone at 3 bodies"


def test_ammonia_payload_snapshot(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_ammonia_payload(
        start="Sol",
        cel="Colonia",
        jump_range=42.5,
        radius=50,
        max_sys=25,
        max_dist=5000,
        min_value=250000,
        loop=True,
        avoid_tharg=False,
    )
    fields = _payload_fields(payload)

    assert fields.get("min_value") == "1", "min_value should be fixed for ammonia payload"
    assert fields.get("loop") == "1", "loop should map to loop flag"
    assert fields.get("avoid_thargoids") == "0", "avoid_thargoids should map to avoid flag"


def test_exomastery_payload_snapshot(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_exomastery_payload(
        start="Sol",
        cel="Colonia",
        jump_range=42.5,
        radius=50,
        max_sys=25,
        max_dist=5000,
        min_value=200000,
        loop=True,
        avoid_tharg=False,
    )

    fields = {key: value for key, value in payload.form_fields}
    assert fields.get("min_value") == "200000", "min_value should map to payload key"
    assert fields.get("loop") == "1", "loop should map to loop flag"
    assert fields.get("avoid_thargoids") == "0", "avoid_thargoids should map to avoid flag"


def test_riches_payload_snapshot(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_riches_payload(
        start="Sol",
        cel="Colonia",
        jump_range=42.5,
        radius=50,
        max_sys=25,
        max_dist=5000,
        min_value=250000,
        loop=True,
        use_map=True,
        avoid_tharg=False,
    )
    fields = _payload_fields(payload)

    assert fields.get("min_value") == "250000", "min_value should map to min_scan"
    assert fields.get("use_mapping_value") == "1", "use_mapping_value should map to use_map"
    assert fields.get("avoid_thargoids") == "0", "avoid_thargoids should map to avoid_tharg"


def test_elw_payload_snapshot(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_elw_payload(
        start="Sol",
        cel="Colonia",
        jump_range=42.5,
        radius=50,
        max_sys=25,
        max_dist=5000,
        min_value=250000,
        loop=True,
        avoid_tharg=False,
    )
    fields = _payload_fields(payload)

    assert fields.get("body_types") == "Earth-like world", "body_types should be ELW"
    assert fields.get("min_value") == "1", "min_value should be fixed for ELW payload"
    assert fields.get("avoid_thargoids") == "0", "avoid_thargoids should map to avoid_tharg"


def test_hmc_payload_snapshot(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_hmc_payload(
        start="Sol",
        cel="Colonia",
        jump_range=42.5,
        radius=50,
        max_sys=25,
        max_dist=5000,
        min_value=250000,
        loop=True,
        avoid_tharg=False,
    )
    fields = _payload_fields(payload)

    assert fields.get("body_types") == [
        "Rocky body",
        "High metal content world",
    ], "body_types should include Rocky + HMC"
    assert fields.get("min_value") == "1", "min_value should be fixed for HMC payload"
    assert fields.get("avoid_thargoids") == "0", "avoid_thargoids should map to avoid_tharg"


def test_trade_payload_snapshot(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_trade_payload(
        start_system="Sol",
        start_station="Jameson Memorial",
        capital=1_000_000,
        max_hop=25.5,
        cargo=256,
        max_hops=10,
        max_dta=1000,
        max_age=5,
        flags={
            "large_pad": True,
            "planetary": False,
            "player_owned": True,
            "restricted": False,
            "prohibited": True,
            "avoid_loops": True,
            "allow_permits": False,
        },
    )
    fields = _payload_fields(payload)

    assert fields.get("system") == "Sol", "system should map to payload"
    assert fields.get("station") == "Jameson Memorial", "station should map to payload"
    assert fields.get("requires_large_pad") == "1", "requires_large_pad should map to large_pad"
    assert fields.get("allow_prohibited") == "1", "allow_prohibited should map to prohibited"
    assert fields.get("unique") == "1", "unique should map to avoid_loops"


def test_trade_payload_forever_omits_market_age(_ctx: TestContext) -> None:
    payload = spansh_payloads.build_trade_payload(
        start_system="Sol",
        start_station="Jameson Memorial",
        capital=1_000_000,
        max_hop=25.5,
        cargo=256,
        max_hops=10,
        max_dta=1000,
        max_age=None,
        flags={"avoid_loops": True},
    )
    fields = _payload_fields(payload)
    assert "max_price_age" not in fields, "max_price_age must be omitted for forever mode"


def test_neutron_payload_snapshot(_ctx: TestContext) -> None:
    class DummyClient(spansh_client_logic.SpanshClient):
        def __init__(self) -> None:
            super().__init__()
            self.last_payload = None

        def route(self, mode, payload, referer=None, gui_ref=None):  # type: ignore[override]
            self.last_payload = payload
            return {}

    dummy = DummyClient()
    dummy.neutron_route("Sol", "Colonia", 42.5, 60.0)

    assert dummy.last_payload is not None, "neutron payload should be captured"
    if hasattr(dummy.last_payload, "form_fields"):
        fields = {key: value for key, value in dummy.last_payload.form_fields}
    else:
        fields = dummy.last_payload
    assert fields.get("from") == "Sol", "neutron payload should map from"
    assert fields.get("to") == "Colonia", "neutron payload should map to"
    assert fields.get("range") == "42.5", "neutron range should be string"
    efficiency = fields.get("efficiency")
    assert efficiency in ("60.0", "60"), "neutron efficiency should be string"


def test_start_system_fallback_source(_ctx: TestContext) -> None:
    files = [
        "gui/tabs/spansh/ammonia.py",
        "gui/tabs/spansh/riches.py",
        "gui/tabs/spansh/elw.py",
        "gui/tabs/spansh/hmc.py",
        "gui/tabs/spansh/exomastery.py",
        "gui/tabs/spansh/neutron.py",
        "gui/tabs/spansh/trade.py",
    ]
    pattern = re.compile(
        r"if\s+not\s+[\w_]+\s*:\s*\n\s*[\w_]+\s*=.*current_system",
        re.IGNORECASE,
    )
    for rel_path in files:
        path = os.path.join(ROOT_DIR, rel_path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        assert "current_system" in content, f"Missing current_system fallback in {rel_path}"
        assert pattern.search(content), f"Missing start fallback block in {rel_path}"


def test_resolve_planner_jump_range_auto(_ctx: TestContext) -> None:
    cfg = config.config._settings
    original = {
        "planner_auto_use_ship_jump_range": cfg.get("planner_auto_use_ship_jump_range"),
        "planner_allow_manual_range_override": cfg.get("planner_allow_manual_range_override"),
        "planner_fallback_range_ly": cfg.get("planner_fallback_range_ly"),
    }

    try:
        cfg["planner_auto_use_ship_jump_range"] = True
        cfg["planner_allow_manual_range_override"] = True
        cfg["planner_fallback_range_ly"] = 33.3

        app_state.ship_state.jump_range_current_ly = 55.5
        val = spansh_client_logic.resolve_planner_jump_range(None, context="test")
        assert abs(val - 55.5) < 0.0001, "auto range should use ship JR"

        app_state.ship_state.jump_range_current_ly = None
        val = spansh_client_logic.resolve_planner_jump_range(None, context="test")
        assert abs(val - 33.3) < 0.0001, "fallback range should be used when JR missing"
    finally:
        for key, value in original.items():
            cfg[key] = value


def test_route_planner_modules_smoke(_ctx: TestContext) -> None:
    """
    Scenariusz:
    - plannerowe moduły logic/* działają na stubowanym kliencie SPANSH,
    - parsery zwracają niepuste route/rows bez sieci i bez pełnego GUI.
    """

    class DummyClient:
        def route(self, mode, payload, referer=None, gui_ref=None, **_kwargs):
            if mode == "trade":
                return [
                    {
                        "from_system": "SMOKE_TRADE_A",
                        "to_system": "SMOKE_TRADE_B",
                        "commodity": "Gold",
                        "profit": 12000,
                        "profit_per_tonne": 250,
                        "jumps": 2,
                    }
                ]
            if mode == "exobiology":
                return [
                    {
                        "system": "SMOKE_EXO_A",
                        "landmarks": [
                            {
                                "body": "SMOKE_EXO_A 1",
                                "species": "Aleoida Arcus",
                                "distance": 300,
                                "value": 700000,
                            }
                        ],
                    }
                ]
            return [
                {
                    "system": "SMOKE_ROUTE_A",
                    "jumps": 1,
                    "bodies": [
                        {
                            "name": "SMOKE_ROUTE_A 1",
                            "subtype": "Water world",
                            "distance": 1200,
                            "value": 123456,
                            "mapping_value": 223456,
                        }
                    ],
                }
            ]

        def neutron_route(
            self,
            start,
            cel,
            zasieg,
            eff,
            gui_ref=None,
            return_details=False,
            supercharge_mode=None,
            via=None,
        ):
            systems = ["SMOKE_NEU_A", "SMOKE_NEU_B", "SMOKE_NEU_C"]
            details = [
                {"system": "SMOKE_NEU_A", "distance": 10.0, "remaining": 30.0, "neutron": True, "jumps": 2},
                {"system": "SMOKE_NEU_B", "distance": 20.0, "remaining": 10.0, "neutron": False, "jumps": 1},
                {"system": "SMOKE_NEU_C", "distance": 10.0, "remaining": 0.0, "neutron": False, "jumps": 0},
            ]
            if return_details:
                return systems, details
            return systems

    dummy = DummyClient()
    originals = {
        "riches": riches_logic.client,
        "ammonia": ammonia_logic.client,
        "elw": elw_logic.client,
        "hmc": hmc_logic.client,
        "exo": exomastery_logic.client,
        "trade": trade_logic.client,
        "neutron": neutron_logic.client,
    }

    try:
        riches_logic.client = dummy
        ammonia_logic.client = dummy
        elw_logic.client = dummy
        hmc_logic.client = dummy
        exomastery_logic.client = dummy
        trade_logic.client = dummy
        neutron_logic.client = dummy

        route_riches, rows_riches = riches_logic.oblicz_rtr(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=10,
            max_dist=5000,
            min_scan=250000,
            loop=False,
            use_map=True,
            avoid_tharg=True,
            gui_ref=None,
        )
        assert route_riches and rows_riches, "RICHES planner should return rows"

        route_amm, rows_amm = ammonia_logic.oblicz_ammonia(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=10,
            max_dist=5000,
            loop=False,
            avoid_tharg=True,
            gui_ref=None,
        )
        assert route_amm and rows_amm, "AMMONIA planner should return rows"

        route_elw, rows_elw = elw_logic.oblicz_elw(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=10,
            max_dist=5000,
            loop=False,
            avoid_tharg=True,
            gui_ref=None,
        )
        assert route_elw and rows_elw, "ELW planner should return rows"

        route_hmc, rows_hmc = hmc_logic.oblicz_hmc(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=10,
            max_dist=5000,
            loop=False,
            avoid_tharg=True,
            gui_ref=None,
        )
        assert route_hmc and rows_hmc, "HMC planner should return rows"

        route_exo, rows_exo = exomastery_logic.oblicz_exomastery(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=10,
            max_dist=5000,
            min_landmark_value=200000,
            loop=False,
            avoid_tharg=True,
            gui_ref=None,
        )
        assert route_exo and rows_exo, "EXOMASTERY planner should return rows"

        route_trade, rows_trade = trade_logic.oblicz_trade(
            start_system="Sol",
            start_station="Jameson Memorial",
            capital=1_000_000,
            max_hop=25.0,
            cargo=64,
            max_hops=4,
            max_dta=1000,
            max_age=7,
            flags={"avoid_loops": True},
            gui_ref=None,
        )
        assert route_trade and rows_trade, "TRADE planner should return rows"

        neutron_route = neutron_logic.oblicz_spansh(
            start="Sol",
            cel="Colonia",
            zasieg=42.0,
            eff=60.0,
            gui_ref=None,
        )
        assert neutron_route, "NEUTRON planner should return route"

        neutron_route2, neutron_details = neutron_logic.oblicz_spansh_with_details(
            start="Sol",
            cel="Colonia",
            zasieg=42.0,
            eff=60.0,
            gui_ref=None,
        )
        assert neutron_route2 and neutron_details, "NEUTRON planner details should be returned"

    finally:
        riches_logic.client = originals["riches"]
        ammonia_logic.client = originals["ammonia"]
        elw_logic.client = originals["elw"]
        hmc_logic.client = originals["hmc"]
        exomastery_logic.client = originals["exo"]
        trade_logic.client = originals["trade"]
        neutron_logic.client = originals["neutron"]


# --- TESTY: FIRST FOOTFALL ---------------------------------------------------


def test_first_footfall_basic(ctx: TestContext) -> None:
    """
    Scenariusz:
    - Footfall z flagą FirstFootfall=True na nowym ciele -> komunikat powiedz(),
    - drugi raz na tym samym ciele -> cicho (anty-spam).
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    misc_events.reset_footfall_flags()

    ev_first = {
        "event": "Footfall",
        "BodyName": "SMOKE_TEST_FOOTFALL_BODY",
        "FirstFootfall": True,
    }

    # Pierwsze wywołanie – powinien być komunikat
    misc_events.handle_first_footfall(ev_first, gui_ref=None)
    msgs_first = ctx.drain_queue()
    assert len(msgs_first) > 0, "Expected first footfall message, got none"

    joined_first = " | ".join(str(m) for m in msgs_first)
    assert "pierwszy ludzki krok" in joined_first, (
        "Expected first-footfall text in first call, "
        f"got: {joined_first}"
    )

    # Drugi raz na tym samym ciele – powinno być cicho
    ctx.clear_queue()
    misc_events.handle_first_footfall(ev_first, gui_ref=None)
    msgs_second = ctx.drain_queue()
    assert len(msgs_second) == 0, (
        "Expected no additional first-footfall messages on second call, "
        f"got: {msgs_second}"
    )



def test_table_schemas_basic(_ctx: TestContext) -> None:
    try:
        from gui import table_schemas
    except Exception as exc:
        raise AssertionError(f"Failed to import table_schemas: {exc}")

    schemas = table_schemas.SCHEMAS
    assert schemas, "No table schemas defined"

    for schema_id, schema in schemas.items():
        assert schema.columns, f"Schema {schema_id} has no columns"
        keys = [col.key for col in schema.columns]
        labels = [col.label for col in schema.columns]
        assert all(k for k in keys), f"Schema {schema_id} has empty column key"
        assert all(l for l in labels), f"Schema {schema_id} has empty column label"
        assert len(set(keys)) == len(keys), f"Schema {schema_id} has duplicate column keys"


def test_spansh_system_copy_mapping(_ctx: TestContext) -> None:
    body_schemas = ["ammonia", "elw", "hmc", "exomastery", "riches", "neutron"]
    for schema_id in body_schemas:
        value, is_real = common_tables.resolve_copy_system_value(
            schema_id,
            {"system_name": "SMOKE_SYS_A"},
            None,
        )
        assert is_real, f"{schema_id}: expected real system from system_name"
        assert value == "SMOKE_SYS_A", f"{schema_id}: wrong mapped system"

    trade_value, trade_real = common_tables.resolve_copy_system_value(
        "trade",
        {"to_system": "SMOKE_TRADE_TARGET", "from_system": "SMOKE_TRADE_SOURCE"},
        None,
    )
    assert trade_real, "trade: expected real system from trade row"
    assert trade_value == "SMOKE_TRADE_TARGET", "trade: expected to_system priority"

    txt_value, txt_real = common_tables.resolve_copy_system_value(
        "trade",
        {},
        "SMOKE_A -> SMOKE_B",
    )
    assert txt_real, "trade text fallback should resolve system"
    assert txt_value == "SMOKE_B", "trade text fallback should use target system"

    missing_value, missing_real = common_tables.resolve_copy_system_value(
        "riches",
        {},
        "",
    )
    assert not missing_real, "empty payload should not be marked as real system"
    assert missing_value == "brak nazwy systemu", "fallback copy text mismatch"


def test_spansh_copy_mode_actions(_ctx: TestContext) -> None:
    required_labels = [
        "Kopiuj wiersze",
        "Kopiuj wiersz",
        "Kopiuj z naglowkiem",
        "Kopiuj zaznaczone",
        "Kopiuj wszystko",
    ]
    files = [
        "gui/tabs/spansh/planner_base.py",
        "gui/tabs/spansh/neutron.py",
        "gui/tabs/spansh/trade.py",
    ]
    for rel_path in files:
        path = os.path.join(ROOT_DIR, rel_path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for label in required_labels:
            assert label in content, f"Missing '{label}' action in {rel_path}"
        assert "enable_results_checkboxes(" in content, f"Missing checkbox-mode enable in {rel_path}"
        assert "get_checked_internal_indices(" in content, f"Missing checkbox selection source in {rel_path}"

    common_tables_path = os.path.join(ROOT_DIR, "gui/common_tables.py")
    with open(common_tables_path, "r", encoding="utf-8", errors="ignore") as f:
        table_content = f.read()
    assert table_content.count('selectmode="extended"') >= 2, (
        "Expected extended multi-select for listbox and treeview"
    )
    for symbol in (
        "CHECKBOX_OFF",
        "CHECKBOX_ON",
        "def enable_results_checkboxes(",
        "def get_checked_internal_indices(",
        "def _on_treeview_checkbox_click(",
        "def _on_listbox_checkbox_click(",
        "__sel__",
    ):
        assert symbol in table_content, f"Missing checkbox support symbol: {symbol}"
    assert "selection_includes" in table_content, "Expected listbox right-click selection guard"
    assert "current_selection = set(widget.selection())" in table_content, (
        "Expected treeview right-click selection guard"
    )


def test_spansh_export_actions_and_formats(_ctx: TestContext) -> None:
    files = [
        "gui/tabs/spansh/planner_base.py",
        "gui/tabs/spansh/neutron.py",
        "gui/tabs/spansh/trade.py",
    ]
    required_labels = [
        "Kopiuj do Excela",
        "Zaznaczone",
        "Z naglowkiem",
        "Wiersz",
        "Wszystko",
    ]
    for rel_path in files:
        path = os.path.join(ROOT_DIR, rel_path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for label in required_labels:
            assert label in content, f"Missing '{label}' export option in {rel_path}"
        assert "Kopiuj CSV" not in content, f"Deprecated CSV menu still present in {rel_path}"
        assert "Kopiuj TSV" not in content, f"Deprecated TSV menu still present in {rel_path}"
        assert "Kopiuj jako Exel" not in content, f"Deprecated Excel label in {rel_path}"

    row = {
        "from_system": "SOL",
        "to_system": "COLONIA",
        "commodity": "Gold",
        "profit": 12000,
        "profit_per_ton": 250,
        "jumps": 2,
    }
    csv_body = common_tables.format_row_delimited("trade", row, ",")
    csv_head = common_tables.format_row_delimited_with_header("trade", row, ",")
    tsv_head = common_tables.format_row_delimited_with_header("trade", row, "\t")
    assert csv_body and "SOL" in csv_body and "COLONIA" in csv_body, "CSV body export missing values"
    assert "\n" in csv_head, "CSV with headers should include header line"
    assert "\n" in tsv_head and "\t" in tsv_head, "TSV with headers should include tabs and header line"
    assert csv_head.count(",") >= 2, "CSV with headers should not be empty separators only"


def test_trade_station_name_normalization(_ctx: TestContext) -> None:
    sample = {
        "result": [
            {
                "from_system": "SOL",
                "to_system": "COLONIA",
                "from_station": "Jameson Memorial",
                "to_station": "Jaques Station",
                "commodity": "Gold",
                "profit": 12000,
            },
            {
                "from": {"system": "LHS 20", "station": "Ohm City"},
                "to": {"system": "Shinrarta Dezhra", "station_name": "Jameson Memorial"},
                "commodity": {"name": "Palladium"},
                "profit_per_tonne": 3333,
            },
            {
                "from_system": "A",
                "to_system": "B",
                "commodity": "Silver",
            },
        ]
    }
    route, rows = normalize_trade_rows(sample)
    assert route, "Expected non-empty route from trade normalization"
    assert len(rows) == 3, f"Expected 3 trade rows, got {len(rows)}"

    r0 = rows[0]
    assert r0.get("from_station") == "Jameson Memorial", "Flat from_station mapping failed"
    assert r0.get("to_station") == "Jaques Station", "Flat to_station mapping failed"

    r1 = rows[1]
    assert r1.get("from_system") == "LHS 20", "Nested from.system mapping failed"
    assert r1.get("to_system") == "Shinrarta Dezhra", "Nested to.system mapping failed"
    assert r1.get("from_station") == "Ohm City", "Nested from.station mapping failed"
    assert r1.get("to_station") == "Jameson Memorial", "Nested to.station_name mapping failed"
    assert r1.get("commodity") == "Palladium", "Nested commodity.name mapping failed"

    r2 = rows[2]
    assert r2.get("from_station") == "UNKNOWN_STATION", "Missing from_station should use UNKNOWN_STATION"
    assert r2.get("to_station") == "UNKNOWN_STATION", "Missing to_station should use UNKNOWN_STATION"


def test_trade_multi_commodity_aliases_and_metrics(_ctx: TestContext) -> None:
    sample = {
        "result": [
            {
                "fromSystem": "DIAGUANDRI",
                "toSystem": "VALTYS",
                "fromStation": "Ray Gateway",
                "toStation": "Oleskiw City",
                "distanceLy": 46.74,
                "commodity": "Liquid oxygen",
                "amount": 256,
                "buyPrice": 719,
                "sellPrice": 2333,
                "profit": 1614,
                "totalProfit": 413184,
                "updatedAgo": "27 minutes ago",
                "cumulativeProfit": 413184,
            },
            {
                "from": {"system": "CHUP KAMUI", "station": "Savinykh Platform", "updated_at": "39 minutes ago"},
                "to": {"system": "LHS 1217", "station_name": "Segmentum Tempestus"},
                "distance": 42.10,
                "commodities": [
                    {
                        "commodity": "Imperial Slaves",
                        "amount": 31,
                        "buyPrice": 1563,
                        "sellPrice": 17154,
                        "profit": 15591,
                        "totalProfit": 483321,
                    },
                    {
                        "commodity_name": "Military Grade Fabrics",
                        "qty": 225,
                        "buy_price": 309,
                        "sell_price": 14530,
                        "profit_per_tonne": 14221,
                        "total_profit": 3199725,
                    },
                ],
            },
        ]
    }
    _route, rows = normalize_trade_rows(
        sample,
        external_meta={
            "source_status": "CACHE_TTL_HIT",
            "confidence": "mid",
            "data_age": "2h",
            "confidence_score": 0.72,
            "data_age_seconds": 7200,
        },
    )
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"

    single = rows[0]
    assert single.get("commodity_display") == "Liquid oxygen", "Single commodity display mapping failed"
    assert single.get("amount") == 256, "Single amount mapping failed"
    assert single.get("buy_price") == 719, "Single buyPrice alias mapping failed"
    assert single.get("sell_price") == 2333, "Single sellPrice alias mapping failed"
    assert single.get("profit") == 1614, "Single profit per unit mapping failed"
    assert single.get("total_profit") == 413184, "Single totalProfit alias mapping failed"
    assert single.get("updated_ago"), "Single updatedAgo alias mapping failed"
    assert single.get("cumulative_profit") == 413184, "Single cumulativeProfit alias mapping failed"
    assert single.get("distance_ly") == 46.74, "Single distanceLy alias mapping failed"
    assert single.get("cumulative_profit_from_payload") is True, "Single cumulative payload source should be flagged"
    assert single.get("source_status") == "CACHE_TTL_HIT", "Expected source_status passthrough from external meta"
    assert single.get("confidence") == "mid", "Expected confidence passthrough from external meta"
    assert single.get("data_age") == "2h", "Expected data_age passthrough from external meta"

    multi = rows[1]
    assert multi.get("commodity_display") == "Imperial Slaves +1", "Multi commodity aggregate display failed"
    assert multi.get("amount") == 256, "Multi amount aggregation failed"
    assert multi.get("buy_price") == 461, "Multi weighted buy price failed"
    assert multi.get("sell_price") == 14848, "Multi weighted sell price failed"
    assert multi.get("total_profit") == 3683046, "Multi total_profit aggregation failed"
    assert multi.get("profit") == 14387, "Multi profit per unit derivation failed"
    assert multi.get("updated_ago"), "Multi updated_at fallback mapping failed"
    assert multi.get("cumulative_profit") == 4096230, "Multi cumulative fallback calculation failed"
    assert multi.get("distance_ly") == 42.10, "Multi distance mapping failed"
    assert multi.get("cumulative_profit_from_payload") is False, "Multi cumulative fallback should not be payload"
    assert multi.get("source_status") == "CACHE_TTL_HIT", "Expected source_status passthrough for all rows"


def test_trade_updated_buy_sell_pair_from_market_timestamps(_ctx: TestContext) -> None:
    now = int(time.time())
    sample = {
        "result": [
            {
                "from": {
                    "system": "DIAGUANDRI",
                    "station": "Ray Gateway",
                    "market_updated_at": now - 600,
                },
                "to": {
                    "system": "CHONGQUAN",
                    "station": "Pippin Terminal",
                    "market_updated_at": now - 7200,
                },
                "distance": 42.0,
                "commodity": "Silver",
                "amount": 256,
                "profit": 15000,
                "total_profit": 3840000,
            }
        ]
    }
    _route, rows = normalize_trade_rows(sample)
    assert len(rows) == 1, f"Expected one trade row, got {len(rows)}"
    row = rows[0]
    updated_buy = str(row.get("updated_buy_ago") or "")
    updated_sell = str(row.get("updated_sell_ago") or "")
    updated_display = str(row.get("updated_ago") or "")
    assert updated_buy.endswith("m"), "Expected buy-side compact age in minutes"
    assert updated_sell.endswith("h"), "Expected sell-side compact age in hours"
    assert " / " in updated_display, "Expected combined buy/sell updated display"


def test_trade_nested_source_destination_prices_for_details(_ctx: TestContext) -> None:
    sample = {
        "result": [
            {
                "from": {"system": "DIAGUANDRI", "station": "Ray Gateway"},
                "to": {"system": "Tascheter Sector RT-R a4-0", "station": "Fibonacci Relay"},
                "distance": 46.74,
                "commodities": [
                    {
                        "name": "Liquid oxygen",
                        "amount": 256,
                        "profit": 1614,
                        "total_profit": 413184,
                        "source_commodity": {"buy_price": 719},
                        "destination_commodity": {"sell_price": 2333},
                    }
                ],
            }
        ]
    }
    _route, rows = normalize_trade_rows(sample)
    assert len(rows) == 1, f"Expected one trade row, got {len(rows)}"
    row = rows[0]
    assert row.get("buy_price") == 719, "Expected buy_price from source_commodity.buy_price"
    assert row.get("sell_price") == 2333, "Expected sell_price from destination_commodity.sell_price"
    commodities = row.get("commodities_raw") or []
    assert isinstance(commodities, list) and commodities, "Expected commodities_raw to be populated"
    first = commodities[0]
    assert first.get("buy_price") == 719, "Expected details buy_price from nested source commodity"
    assert first.get("sell_price") == 2333, "Expected details sell_price from nested destination commodity"


def test_tts_polish_diacritics_global(_ctx: TestContext) -> None:
    fss = prepare_tts("MSG.FSS_PROGRESS_50", {})
    assert fss and "Połowa systemu przeskanowana." in fss, "Expected Polish diacritics in FSS text"

    milestone = prepare_tts(
        "MSG.MILESTONE_REACHED",
        {"target": "Źródło", "next_target": "Łąka"},
    )
    assert milestone and "osiągnięty" in milestone.lower(), "Expected 'osiągnięty' in milestone text"
    assert "przechodzę" in milestone.lower(), "Expected 'przechodzę' in milestone text"

    startup = prepare_tts("MSG.STARTUP_SYSTEMS", {"version": "v1"})
    assert startup and "Startuję wszystkie systemy." in startup, "Expected Polish diacritics in startup text"

    repaired = prepare_tts(
        "MSG.TRADE_JACKPOT",
        {"raw_text": "To Ĺ›wietna okazja. Cena: 100 kredytĂłw."},
    )
    assert repaired and "świetna okazja" in repaired.lower(), "Expected mojibake repair for Polish text"
    assert "kredytów" in repaired.lower(), "Expected mojibake repair for Polish currency word"
    for marker in ("Ã", "Ä", "Å", "Ĺ", "â€"):
        assert marker not in repaired, f"Unexpected mojibake marker '{marker}' in repaired text"


def test_exobio_sample_progress_sequence(_ctx: TestContext) -> None:
    # Preserve original helpers patched for deterministic threshold/value.
    orig_min_distance = bio_events._species_minimum_distance  # type: ignore[attr-defined]
    orig_estimate_value = bio_events._estimate_collected_species_value  # type: ignore[attr-defined]
    try:
        bio_events.reset_bio_flags()
        app_state.current_system = "SMOKE_EXOBIO_SYS"

        bio_events._species_minimum_distance = lambda _species: 100.0  # type: ignore[attr-defined]
        bio_events._estimate_collected_species_value = (  # type: ignore[attr-defined]
            lambda _ev, _species: (12345.0, False)
        )

        # Baseline position for tracker.
        bio_events.handle_exobio_status_position(
            {
                "Latitude": 0.0,
                "Longitude": 0.0,
                "PlanetRadius": 6_371_000.0,
                "BodyName": "SMOKE_BODY",
            },
            gui_ref=None,
        )

        # 1/3
        ev_sample = {
            "event": "ScanOrganic",
            "StarSystem": "SMOKE_EXOBIO_SYS",
            "BodyName": "SMOKE_BODY",
            "Species_Localised": "Aleoida Arcus",
        }
        bio_events.handle_exobio_progress(ev_sample, gui_ref=None)
        msgs_1 = [str(m) for m in MSG_QUEUE.queue]
        joined_1 = " | ".join(msgs_1)
        assert "Pierwsza próbka Aleoida Arcus pobrana." in joined_1, "Missing first sample progress callout"
        while not MSG_QUEUE.empty():
            MSG_QUEUE.get_nowait()

        # Gate after 1/3.
        bio_events.handle_exobio_status_position(
            {
                "Latitude": 0.0,
                "Longitude": 0.002,
                "PlanetRadius": 6_371_000.0,
                "BodyName": "SMOKE_BODY",
            },
            gui_ref=None,
        )
        msgs_gate_1 = [str(m) for m in MSG_QUEUE.queue]
        joined_gate_1 = " | ".join(msgs_gate_1)
        assert "Osiągnięto odpowiednią odległość. Pobierz kolejną próbkę." in joined_gate_1, (
            "Missing gate callout after first sample"
        )
        while not MSG_QUEUE.empty():
            MSG_QUEUE.get_nowait()

        # 2/3
        bio_events.handle_exobio_progress(ev_sample, gui_ref=None)
        msgs_2 = [str(m) for m in MSG_QUEUE.queue]
        joined_2 = " | ".join(msgs_2)
        assert "Druga próbka Aleoida Arcus pobrana." in joined_2, "Missing second sample progress callout"
        while not MSG_QUEUE.empty():
            MSG_QUEUE.get_nowait()

        # Gate after 2/3.
        bio_events.handle_exobio_status_position(
            {
                "Latitude": 0.0,
                "Longitude": 0.0042,
                "PlanetRadius": 6_371_000.0,
                "BodyName": "SMOKE_BODY",
            },
            gui_ref=None,
        )
        msgs_gate_2 = [str(m) for m in MSG_QUEUE.queue]
        joined_gate_2 = " | ".join(msgs_gate_2)
        assert "Osiągnięto odpowiednią odległość. Pobierz kolejną próbkę." in joined_gate_2, (
            "Missing gate callout after second sample"
        )
        while not MSG_QUEUE.empty():
            MSG_QUEUE.get_nowait()

        # 3/3 + value.
        bio_events.handle_exobio_progress(ev_sample, gui_ref=None)
        msgs_3 = [str(m) for m in MSG_QUEUE.queue]
        joined_3 = " | ".join(msgs_3)
        assert "Mamy wszystko dla Aleoida Arcus." in joined_3, "Missing completion callout at 3/3"
        assert "12 345 kredytów" in joined_3, "Missing value callout at 3/3"
        while not MSG_QUEUE.empty():
            MSG_QUEUE.get_nowait()

        # After completion: no more gate, no more sample spam for same species/body.
        bio_events.handle_exobio_status_position(
            {
                "Latitude": 0.0,
                "Longitude": 0.0065,
                "PlanetRadius": 6_371_000.0,
                "BodyName": "SMOKE_BODY",
            },
            gui_ref=None,
        )
        bio_events.handle_exobio_progress(ev_sample, gui_ref=None)
        assert MSG_QUEUE.empty(), "No additional callouts expected after 3/3 completion"

    finally:
        bio_events._species_minimum_distance = orig_min_distance  # type: ignore[attr-defined]
        bio_events._estimate_collected_species_value = orig_estimate_value  # type: ignore[attr-defined]
        bio_events.reset_bio_flags()
        while not MSG_QUEUE.empty():
            MSG_QUEUE.get_nowait()


def test_f3_exploration_cross_module_invariants(ctx: TestContext) -> None:
    """
    F3 quality gate (cross-module):
    - mixed exploration signals in one system -> single awareness summary,
    - exobio 1/2/3 progression without extra 4th sample callout.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    app_state.current_system = "SMOKE_F3_CROSS_SYSTEM"
    awareness_events.reset_exploration_awareness()
    fss_events.reset_fss_progress()
    bio_events.reset_bio_flags()
    dss_events.reset_dss_helper_state()

    class DummyGui:
        def __init__(self) -> None:
            self.carto_df = pd.DataFrame(
                [
                    {
                        "Body_Type": "earth-like world",
                        "Terraformable": "No",
                        "DSS_Mapped_Value": 1_500_000,
                    },
                    {
                        "Body_Type": "rocky body",
                        "Terraformable": "No",
                        "DSS_Mapped_Value": 900_000,
                    },
                ]
            )

    def _awareness_limits(key: str, default=None):
        if key == "exploration.awareness.max_callouts_per_system":
            return 1
        if key == "exploration.awareness.max_callouts_per_session":
            return 60
        return default

    gui_ref = DummyGui()
    with (
        patch("logic.events.exploration_awareness.config.get", side_effect=_awareness_limits),
        patch(
            "logic.events.exploration_bio_events._estimate_collected_species_value",
            return_value=(12345.0, False),
        ),
    ):
        # Awareness stack: first callout + one summary for mixed exploration context.
        fss_events.handle_scan(
            {
                "event": "Scan",
                "StarSystem": "SMOKE_F3_CROSS_SYSTEM",
                "BodyName": "SMOKE_F3_BODY_1",
                "PlanetClass": "Earth-like world",
                "WasDiscovered": False,
            },
            gui_ref=gui_ref,
        )
        bio_events.handle_dss_bio_signals(
            {
                "event": "SAASignalsFound",
                "StarSystem": "SMOKE_F3_CROSS_SYSTEM",
                "BodyName": "SMOKE_F3_BODY_2",
                "Signals": [{"Type": "Biological", "Count": 3}],
            },
            gui_ref=gui_ref,
        )
        dss_events.handle_dss_target_hint(
            {
                "event": "Scan",
                "StarSystem": "SMOKE_F3_CROSS_SYSTEM",
                "BodyName": "SMOKE_F3_BODY_3",
                "PlanetClass": "Rocky body",
                "WasMapped": False,
            },
            gui_ref=gui_ref,
        )

        # Exobio progress: 1/2/3 then stop.
        sample_event = {
            "event": "ScanOrganic",
            "StarSystem": "SMOKE_F3_CROSS_SYSTEM",
            "BodyName": "SMOKE_F3_BIO_BODY",
            "Species_Localised": "Aleoida Arcus",
        }
        bio_events.handle_exobio_progress(sample_event, gui_ref=None)
        bio_events.handle_exobio_progress(sample_event, gui_ref=None)
        bio_events.handle_exobio_progress(sample_event, gui_ref=None)
        bio_events.handle_exobio_progress(sample_event, gui_ref=None)

    joined = " | ".join(str(m) for m in ctx.drain_queue())
    joined_lower = joined.lower()

    assert joined_lower.count("w tym systemie sa jeszcze obiekty warte uwagi eksploracyjnej.") == 1, (
        "Expected exactly one mixed-system summary in F3 cross-module scenario"
    )
    assert joined_lower.count("pierwsza próbka aleoida arcus pobrana.") == 1, (
        "Expected exactly one first-sample exobio callout"
    )
    assert joined_lower.count("druga próbka aleoida arcus pobrana.") == 1, (
        "Expected exactly one second-sample exobio callout"
    )
    assert joined_lower.count("mamy wszystko dla aleoida arcus.") == 1, (
        "Expected exactly one completion exobio callout"
    )


def test_f4_exploration_summary_baseline(ctx: TestContext) -> None:
    """
    F4 baseline smoke:
    - manual summary emits once through dispatcher path,
    - queue receives log + structured exploration summary payload.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_F4_SUMMARY_SYSTEM"
    app_state.last_exploration_summary_signature = None

    sample = ExitSummaryData(
        system_name="SMOKE_F4_SUMMARY_SYSTEM",
        scanned_bodies=9,
        total_bodies=10,
        elw_count=1,
        elw_value=20_000_000.0,
        ww_count=1,
        ww_value=2_000_000.0,
        ww_t_count=0,
        ww_t_value=0.0,
        hmc_t_count=1,
        hmc_t_value=1_500_000.0,
        biology_species_count=1,
        biology_value=3_000_000.0,
        bonus_discovery=800_000.0,
        total_value=27_300_000.0,
    )

    with (
        patch.object(app_state.exit_summary, "build_summary_data", return_value=sample),
        patch.object(
            app_state,
            "system_value_engine",
            new=type("DummyEngine", (), {"calculate_totals": lambda self: {"total": 40_000_000.0}})(),
        ),
    ):
        ok = summary_events.trigger_exploration_summary(mode="manual", gui_ref=None)

    assert ok, "Expected manual exploration summary trigger to emit"

    items = ctx.drain_queue()
    assert any(
        isinstance(item, tuple) and len(item) == 2 and item[0] == "log"
        for item in items
    ), "Expected summary log line in queue"
    payload_items = [
        item[1]
        for item in items
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "exploration_summary"
    ]
    assert payload_items, "Expected structured exploration_summary payload in queue"
    payload = payload_items[-1]
    assert payload.get("system") == "SMOKE_F4_SUMMARY_SYSTEM", (
        f"Unexpected summary payload system: {payload}"
    )
    assert payload.get("next_step"), f"Missing next_step in summary payload: {payload}"
    assert payload.get("highlights"), f"Missing highlights in summary payload: {payload}"


def test_f4_cash_in_assistant_baseline(ctx: TestContext) -> None:
    """
    F4 cash-in baseline smoke:
    - manual trigger emits queue line + structured cash-in payload,
    - decision space contains 2-3 options + Pomijam.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_F4_CASHIN_SYSTEM"
    app_state.last_cash_in_signature = None
    app_state.cash_in_skip_signature = None

    summary_payload = {
        "system": "SMOKE_F4_CASHIN_SYSTEM",
        "scanned_bodies": 9,
        "total_bodies": 12,
        "cash_in_signal": "wysoki",
        "cash_in_system_estimated": 19_500_000.0,
        "cash_in_session_estimated": 42_000_000.0,
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
    }

    ok = cash_in_events.trigger_cash_in_assistant(
        mode="manual",
        gui_ref=None,
        summary_payload=summary_payload,
    )
    assert ok, "Expected manual cash-in assistant trigger to emit"

    items = ctx.drain_queue()
    assert any(
        isinstance(item, tuple) and len(item) == 2 and item[0] == "log"
        for item in items
    ), "Expected cash-in assistant log line in queue"
    payload_items = [
        item[1]
        for item in items
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "cash_in_assistant"
    ]
    assert payload_items, "Expected structured cash_in_assistant payload in queue"

    payload = payload_items[-1]
    options = payload.get("options") or []
    assert 2 <= len(options) <= 3, f"Expected 2-3 cash-in options, got: {options}"
    skip_action = payload.get("skip_action") or {}
    assert str(skip_action.get("label") or "").strip() == "Pomijam", (
        f"Expected Pomijam skip action, got: {skip_action}"
    )


def test_f4_survival_rebuy_awareness_baseline(ctx: TestContext) -> None:
    """
    F4 survival/rebuy baseline smoke:
    - no-rebuy path emits critical payload,
    - repeated same signature does not spam,
    - payload is propagated to queue for UI card rendering.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_F4_SURVIVAL_SYSTEM"
    app_state.last_survival_rebuy_signature = None
    survival_events.reset_survival_rebuy_state()

    event = {
        "event": "LoadGame",
        "StarSystem": "SMOKE_F4_SURVIVAL_SYSTEM",
        "Credits": 150_000,
        "Rebuy": 900_000,
    }

    first = survival_events.handle_journal_event(event, gui_ref=None)
    second = survival_events.handle_journal_event(event, gui_ref=None)
    assert first is None and second is None  # handler is side-effect based

    items = ctx.drain_queue()
    assert any(
        isinstance(item, tuple) and len(item) == 2 and item[0] == "log"
        for item in items
    ), "Expected survival/rebuy log line in queue"
    payload_items = [
        item[1]
        for item in items
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "survival_rebuy"
    ]
    assert len(payload_items) == 1, f"Expected single non-spam survival payload, got: {payload_items}"
    payload = payload_items[-1]
    assert payload.get("level") == "critical", f"Expected critical survival level, got: {payload}"
    assert payload.get("reason") == "no_rebuy", f"Expected no_rebuy reason, got: {payload}"


def test_f5_combat_awareness_baseline(ctx: TestContext) -> None:
    """
    F5 combat awareness baseline smoke:
    - high-risk combat pattern requires repeat entry before emit,
    - emitted payload is non-flooded and has expected structure.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_F5_COMBAT_SYSTEM"
    app_state.last_combat_awareness_signature = None
    combat_events.reset_combat_awareness_state()

    with patch.object(
        app_state,
        "system_value_engine",
        new=SimpleNamespace(calculate_totals=lambda: {"total": 30_000_000.0}),
    ):
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_COMBAT_SYSTEM",
                "InDanger": True,
                "Hull": 0.55,
                "ShieldsUp": False,
                "FSDCooldown": 5.0,
            },
            gui_ref=None,
        )
        # Exit pattern.
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_COMBAT_SYSTEM",
                "InDanger": True,
                "Hull": 0.80,
                "ShieldsUp": True,
                "FSDCooldown": 0.0,
            },
            gui_ref=None,
        )
        # Re-enter pattern -> should emit.
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_COMBAT_SYSTEM",
                "InDanger": True,
                "Hull": 0.55,
                "ShieldsUp": False,
                "FSDCooldown": 5.0,
            },
            gui_ref=None,
        )
        # Same active pattern should not flood.
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_COMBAT_SYSTEM",
                "InDanger": True,
                "Hull": 0.55,
                "ShieldsUp": False,
                "FSDCooldown": 5.0,
            },
            gui_ref=None,
        )

    items = ctx.drain_queue()
    payload_items = [
        item[1]
        for item in items
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "combat_awareness"
    ]
    assert len(payload_items) == 1, f"Expected single non-flood combat payload, got: {payload_items}"
    payload = payload_items[-1] or {}
    assert payload.get("level") in {"high", "critical"}, f"Unexpected combat level: {payload}"
    assert str(payload.get("pattern_id") or "").strip(), f"Missing combat pattern_id: {payload}"
    assert bool(payload.get("in_combat")), f"Expected in_combat=True in combat payload: {payload}"


def test_f5_dispatcher_priority_matrix_baseline(_ctx: TestContext) -> None:
    """
    F5 dispatcher matrix baseline smoke:
    - COMBAT message suppresses lower NAV message in active matrix window.
    - Repeated P2 risk message escalates to P1 then P0.
    """
    reset_dispatcher_runtime_state()
    with (
        patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
        patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
        patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
    ):
        combat_ok = emit_insight(
            "combat high",
            message_id="MSG.COMBAT_AWARENESS_HIGH",
            source="combat_awareness",
            event_type="COMBAT_RISK_PATTERN",
            context={
                "system": "SMOKE_F5_MATRIX",
                "risk_status": "RISK_HIGH",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P1_HIGH",
            dedup_key="combat:smoke",
            cooldown_scope="entity",
            cooldown_seconds=0.0,
        )
        nav_ok = emit_insight(
            "nav next hop",
            message_id="MSG.NEXT_HOP",
            source="navigation_events",
            event_type="ROUTE_PROGRESS",
            context={
                "system": "SMOKE_F5_MATRIX",
                "risk_status": "RISK_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="nav:smoke",
            cooldown_scope="entity",
            cooldown_seconds=0.0,
        )

        for _ in range(3):
            emit_insight(
                "escalation candidate",
                message_id="MSG.TEST_MATRIX_ESC",
                source="navigation_events",
                event_type="TEST_EVENT",
                context={
                    "system": "SMOKE_F5_MATRIX",
                    "risk_status": "RISK_CRITICAL",
                    "var_status": "VAR_HIGH",
                    "trust_status": "TRUST_HIGH",
                    "confidence": "high",
                },
                priority="P2_NORMAL",
                dedup_key="matrix:escalate:smoke",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )

    assert combat_ok is True, "Expected combat awareness message in matrix baseline"
    assert nav_ok is False, "Expected navigation suppression after recent combat voice"
    nav_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
    assert nav_ctx.get("voice_priority_reason") == "matrix_suppressed_by_recent_higher_or_equal", (
        f"Unexpected matrix suppression reason: {nav_ctx}"
    )
    escalation_priorities = [
        dict(call.kwargs.get("context") or {}).get("effective_priority")
        for call in powiedz_mock.call_args_list[-3:]
    ]
    assert escalation_priorities == ["P2_NORMAL", "P1_HIGH", "P0_CRITICAL"], (
        f"Unexpected controlled escalation priorities: {escalation_priorities}"
    )


def test_f5_voice_policy_contract_baseline(_ctx: TestContext) -> None:
    resolved = resolve_emit_contract(
        message_id="MSG.EXOBIO_RANGE_READY",
        context={"system": "SMOKE_F5_POLICY"},
        event_type="BIO_PROGRESS",
        priority=None,
        dedup_key=None,
        cooldown_scope=None,
        cooldown_seconds=None,
    )
    runtime_ctx = dict(resolved.get("context") or {})
    assert runtime_ctx.get("tts_intent") == "context", f"Unexpected tts_intent: {runtime_ctx}"
    assert runtime_ctx.get("tts_category") == "explore", f"Unexpected tts_category: {runtime_ctx}"
    assert runtime_ctx.get("tts_cooldown_policy") == "BYPASS_GLOBAL", (
        f"Unexpected tts_cooldown_policy: {runtime_ctx}"
    )

    def _can_send(key, cooldown_sec, context=None):
        if key == "TTS_GLOBAL":
            return False
        return True

    with (
        patch("logic.utils.notify.has_capability", return_value=False),
        patch("logic.utils.notify._is_transit_mode", return_value=False),
        patch.object(notify_module.DEBOUNCER, "can_send", side_effect=_can_send),
    ):
        allowed = notify_module._should_speak_tts(
            "MSG.EXOBIO_RANGE_READY",
            {"confidence": "high"},
        )

    assert allowed is True, "BYPASS_GLOBAL contract should allow threshold message despite global cooldown"


def test_f5_anti_spam_regression_baseline(_ctx: TestContext) -> None:
    """
    F5 anti-spam regression baseline:
    - burst combat message (same signature) emits once,
    - EXOBIO READY is blocked in combat, then recovers once and re-enters cooldown,
    - FSS threshold bypasses global TTS cooldown but still respects entity cooldown,
    - fuel critical is never lost during combat burst.
    """
    reset_dispatcher_runtime_state()
    try:
        last = getattr(notify_module.DEBOUNCER, "_last", None)
        if isinstance(last, dict):
            last.clear()
    except Exception:
        pass

    with (
        patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
        patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
    ):
        burst = [
            emit_insight(
                "combat burst",
                message_id="MSG.COMBAT_AWARENESS_HIGH",
                source="combat_awareness",
                event_type="COMBAT_RISK_PATTERN",
                context={
                    "system": "SMOKE_F5_ANTI_SPAM",
                    "in_combat": True,
                    "risk_status": "RISK_HIGH",
                    "var_status": "VAR_HIGH",
                    "trust_status": "TRUST_HIGH",
                    "confidence": "high",
                },
                priority="P1_HIGH",
                dedup_key="smoke:f5:anti:combat:burst",
                cooldown_scope="entity",
                cooldown_seconds=75.0,
            )
            for _ in range(3)
        ]
        assert burst == [False, True, False], f"Unexpected burst anti-spam behavior: {burst}"

        # Separate sub-scenario: clear matrix/debouncer state so READY recovery is
        # validated against combat silence/cooldown rules, not previous burst memory.
        reset_dispatcher_runtime_state()
        try:
            last = getattr(notify_module.DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

        ready_blocked = emit_insight(
            "ready in combat",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F5_ANTI_SPAM",
                "in_combat": True,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:anti:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        ready_recovered = emit_insight(
            "ready after combat",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F5_ANTI_SPAM",
                "in_combat": False,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:anti:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        ready_cooldown = emit_insight(
            "ready after combat again",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F5_ANTI_SPAM",
                "in_combat": False,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:anti:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        assert ready_blocked is False, "READY should be blocked by combat silence in combat"
        assert ready_recovered is True, "READY should recover once after leaving combat"
        assert ready_cooldown is False, "READY should not flood after recovery emit"

        fuel_ok = emit_insight(
            "fuel critical",
            message_id="MSG.FUEL_CRITICAL",
            source="fuel_events",
            event_type="SHIP_HEALTH_CHANGED",
            context={
                "system": "SMOKE_F5_ANTI_SPAM",
                "in_combat": True,
                "risk_status": "RISK_CRITICAL",
                "var_status": "VAR_HIGH",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P0_CRITICAL",
            dedup_key="smoke:f5:anti:fuel",
            cooldown_scope="entity",
            cooldown_seconds=300.0,
            combat_silence_sensitive=False,
        )
        assert fuel_ok is True, "Fuel critical must not be lost during combat burst"
        fuel_ctx = dict(powiedz_mock.call_args_list[-1].kwargs.get("context") or {})
        assert fuel_ctx.get("voice_priority_reason") in {"priority_critical", "matrix_p0_critical"}, (
            f"Unexpected fuel critical voice reason: {fuel_ctx}"
        )

    reset_dispatcher_runtime_state()
    try:
        last = getattr(notify_module.DEBOUNCER, "_last", None)
        if isinstance(last, dict):
            last.clear()
    except Exception:
        pass

    # Prime global TTS cooldown and verify threshold contract bypasses it.
    notify_module.DEBOUNCER.can_send("TTS_GLOBAL", 8.0)
    fss_first = emit_insight(
        "fss 25",
        message_id="MSG.FSS_PROGRESS_25",
        source="exploration_fss_events",
        event_type="SYSTEM_SCANNED",
        context={
            "system": "SMOKE_F5_ANTI_SPAM_FSS",
            "risk_status": "RISK_MEDIUM",
            "var_status": "VAR_MEDIUM",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        },
        priority="P2_NORMAL",
        dedup_key="smoke:f5:anti:fss25",
        cooldown_scope="entity",
        cooldown_seconds=120.0,
    )
    fss_second = emit_insight(
        "fss 25 again",
        message_id="MSG.FSS_PROGRESS_25",
        source="exploration_fss_events",
        event_type="SYSTEM_SCANNED",
        context={
            "system": "SMOKE_F5_ANTI_SPAM_FSS",
            "risk_status": "RISK_MEDIUM",
            "var_status": "VAR_MEDIUM",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        },
        priority="P2_NORMAL",
        dedup_key="smoke:f5:anti:fss25",
        cooldown_scope="entity",
        cooldown_seconds=120.0,
    )
    assert fss_first is True, "FSS threshold should bypass global cooldown"
    assert fss_second is False, "FSS threshold should still respect anti-spam entity cooldown"


def test_f5_quality_gates_invariants(ctx: TestContext) -> None:
    """
    F5 quality gate pack:
    - combat awareness stays pattern-only and non-coercive,
    - dispatcher matrix keeps deterministic F4/F5 conflict resolution,
    - anti-spam stays stable in combat and outside combat.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()
    app_state.current_system = "SMOKE_F5_QUALITY_SYSTEM"
    app_state.last_combat_awareness_signature = None
    reset_dispatcher_runtime_state()
    combat_events.reset_combat_awareness_state()

    with (
        patch.object(
            app_state,
            "system_value_engine",
            new=SimpleNamespace(calculate_totals=lambda: {"total": 33_000_000.0}),
        ),
        patch("logic.events.combat_awareness.emit_insight") as combat_emit_mock,
    ):
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_QUALITY_SYSTEM",
                "InDanger": True,
                "Hull": 0.55,
                "ShieldsUp": False,
                "FSDCooldown": 5.0,
            },
            gui_ref=None,
        )
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_QUALITY_SYSTEM",
                "InDanger": True,
                "Hull": 0.80,
                "ShieldsUp": True,
                "FSDCooldown": 0.0,
            },
            gui_ref=None,
        )
        combat_events.handle_status_update(
            {
                "StarSystem": "SMOKE_F5_QUALITY_SYSTEM",
                "InDanger": True,
                "Hull": 0.55,
                "ShieldsUp": False,
                "FSDCooldown": 5.0,
            },
            gui_ref=None,
        )

    assert combat_emit_mock.call_count == 1, "Combat awareness should emit once per active repeated pattern"
    combat_ctx = dict(combat_emit_mock.call_args.kwargs.get("context") or {})
    raw_text = str(combat_ctx.get("raw_text") or "").lower()
    assert "wzorzec ryzyka" in raw_text, f"Expected pattern-only wording, got: {raw_text}"
    assert "musisz" not in raw_text and "powinienes" not in raw_text, (
        f"Combat awareness should stay non-coercive, got: {raw_text}"
    )

    reset_dispatcher_runtime_state()
    with (
        patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
        patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False, True]),
        patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
    ):
        summary_ok = emit_insight(
            "summary",
            message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
            source="exploration_summary",
            event_type="SYSTEM_SUMMARY",
            context={
                "system": "SMOKE_F5_QUALITY_SYSTEM",
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P3_LOW",
            dedup_key="smoke:f5:quality:summary",
            cooldown_scope="entity",
            cooldown_seconds=45.0,
        )
        combat_ok = emit_insight(
            "combat",
            message_id="MSG.COMBAT_AWARENESS_HIGH",
            source="combat_awareness",
            event_type="COMBAT_RISK_PATTERN",
            context={
                "system": "SMOKE_F5_QUALITY_SYSTEM",
                "in_combat": False,
                "risk_status": "RISK_HIGH",
                "var_status": "VAR_HIGH",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P1_HIGH",
            dedup_key="smoke:f5:quality:combat",
            cooldown_scope="entity",
            cooldown_seconds=0.0,
        )
        nav_ok = emit_insight(
            "next hop",
            message_id="MSG.NEXT_HOP",
            source="navigation_events",
            event_type="ROUTE_PROGRESS",
            context={
                "system": "SMOKE_F5_QUALITY_SYSTEM",
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:quality:nav",
            cooldown_scope="entity",
            cooldown_seconds=30.0,
        )

    assert summary_ok is True, "Expected summary emit in matrix gate scenario"
    assert combat_ok is True, "Expected combat preemption in matrix gate scenario"
    assert nav_ok is False, "Expected lower class/priority suppression after combat"
    second_ctx = dict(powiedz_mock.call_args_list[1].kwargs.get("context") or {})
    third_ctx = dict(powiedz_mock.call_args_list[2].kwargs.get("context") or {})
    assert second_ctx.get("voice_priority_reason") == "matrix_preempt_higher_force", (
        f"Unexpected combat preemption reason: {second_ctx}"
    )
    assert third_ctx.get("voice_priority_reason") == "matrix_suppressed_by_recent_higher_or_equal", (
        f"Unexpected suppression reason: {third_ctx}"
    )

    reset_dispatcher_runtime_state()
    try:
        last = getattr(notify_module.DEBOUNCER, "_last", None)
        if isinstance(last, dict):
            last.clear()
    except Exception:
        pass

    with (
        patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
        patch("logic.insight_dispatcher._notify.powiedz"),
    ):
        ready_blocked = emit_insight(
            "ready in combat",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F5_QUALITY_SYSTEM",
                "in_combat": True,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:quality:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        ready_recovered = emit_insight(
            "ready after combat",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F5_QUALITY_SYSTEM",
                "in_combat": False,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:quality:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        ready_cooldown = emit_insight(
            "ready second",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F5_QUALITY_SYSTEM",
                "in_combat": False,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f5:quality:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )

    assert ready_blocked is False, "READY should be blocked in combat"
    assert ready_recovered is True, "READY should recover after leaving combat"
    assert ready_cooldown is False, "READY should stay non-flood after recovery"


def test_f6_voice_ethics_compliance_baseline(_ctx: TestContext) -> None:
    """
    F6 voice ethics compliance baseline:
    - policy contract for threshold/critical exceptions is stable,
    - cooldown exceptions bypass global cooldown but keep anti-spam/combat invariants,
    - wording stays informational and non-coercive.
    """
    expected_policy = {
        "MSG.EXOBIO_SAMPLE_LOGGED": ("context", "explore", "ALWAYS_SAY"),
        "MSG.EXOBIO_RANGE_READY": ("context", "explore", "BYPASS_GLOBAL"),
        "MSG.FSS_PROGRESS_25": ("context", "explore", "BYPASS_GLOBAL"),
        "MSG.FSS_PROGRESS_50": ("context", "explore", "BYPASS_GLOBAL"),
        "MSG.FSS_PROGRESS_75": ("context", "explore", "BYPASS_GLOBAL"),
        "MSG.FSS_LAST_BODY": ("context", "explore", "BYPASS_GLOBAL"),
        "MSG.SYSTEM_FULLY_SCANNED": ("context", "explore", "BYPASS_GLOBAL"),
        "MSG.FUEL_CRITICAL": ("critical", "alert", "ALWAYS_SAY"),
    }
    for message_id, expected in expected_policy.items():
        policy = get_tts_policy_spec(message_id)
        assert (policy.intent, policy.category, policy.cooldown_policy) == expected, (
            f"Unexpected policy for {message_id}: {(policy.intent, policy.category, policy.cooldown_policy)}"
        )

    def _can_send(key, cooldown_sec, context=None):
        if key == "TTS_GLOBAL":
            return False
        return True

    with (
        patch("logic.utils.notify.has_capability", return_value=False),
        patch("logic.utils.notify._is_transit_mode", return_value=False),
        patch.object(notify_module.DEBOUNCER, "can_send", side_effect=_can_send),
    ):
        assert notify_module._should_speak_tts("MSG.EXOBIO_RANGE_READY", {"confidence": "high"}) is True, (
            "READY should bypass blocked global cooldown"
        )
        assert notify_module._should_speak_tts("MSG.FSS_PROGRESS_50", {"confidence": "high"}) is True, (
            "FSS threshold should bypass blocked global cooldown"
        )
        assert notify_module._should_speak_tts("MSG.FUEL_CRITICAL", {"confidence": "high"}) is True, (
            "Fuel critical should ignore blocked global cooldown"
        )
        assert notify_module._should_speak_tts("MSG.NEXT_HOP", {"confidence": "high"}) is False, (
            "Normal nav message should be blocked by global cooldown"
        )

    reset_dispatcher_runtime_state()
    try:
        last = getattr(notify_module.DEBOUNCER, "_last", None)
        if isinstance(last, dict):
            last.clear()
    except Exception:
        pass

    with (
        patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
        patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
    ):
        ready_blocked = emit_insight(
            "ready in combat",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F6_ETHICS",
                "in_combat": True,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f6:ethics:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        ready_allowed = emit_insight(
            "ready after combat",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F6_ETHICS",
                "in_combat": False,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f6:ethics:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        ready_cooldown = emit_insight(
            "ready second",
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context={
                "system": "SMOKE_F6_ETHICS",
                "in_combat": False,
                "risk_status": "RISK_MEDIUM",
                "var_status": "VAR_MEDIUM",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            dedup_key="smoke:f6:ethics:ready",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        fuel_allowed = emit_insight(
            "fuel critical",
            message_id="MSG.FUEL_CRITICAL",
            source="fuel_events",
            event_type="SHIP_HEALTH_CHANGED",
            context={
                "system": "SMOKE_F6_ETHICS",
                "in_combat": True,
                "risk_status": "RISK_CRITICAL",
                "var_status": "VAR_HIGH",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P0_CRITICAL",
            dedup_key="smoke:f6:ethics:fuel",
            cooldown_scope="entity",
            cooldown_seconds=300.0,
            combat_silence_sensitive=False,
        )
        fuel_cooldown = emit_insight(
            "fuel critical second",
            message_id="MSG.FUEL_CRITICAL",
            source="fuel_events",
            event_type="SHIP_HEALTH_CHANGED",
            context={
                "system": "SMOKE_F6_ETHICS",
                "in_combat": True,
                "risk_status": "RISK_CRITICAL",
                "var_status": "VAR_HIGH",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P0_CRITICAL",
            dedup_key="smoke:f6:ethics:fuel",
            cooldown_scope="entity",
            cooldown_seconds=300.0,
            combat_silence_sensitive=False,
        )

    assert ready_blocked is False, "READY should be blocked by combat silence"
    assert ready_allowed is True, "READY should recover after combat silence"
    assert ready_cooldown is False, "READY should keep entity anti-spam"
    assert fuel_allowed is True, "Fuel critical must be delivered even in combat"
    assert fuel_cooldown is False, "Fuel critical must still respect entity anti-spam cooldown"

    reasons = [dict(call.kwargs.get("context") or {}).get("voice_priority_reason") for call in powiedz_mock.call_args_list]
    assert "combat_silence" in reasons, f"Missing combat silence reason: {reasons}"
    assert "insight_cooldown" in reasons, f"Missing cooldown reason: {reasons}"
    assert any(
        reason in {"priority_critical", "matrix_p0_critical", "matrix_p0_critical_force"} for reason in reasons
    ), f"Missing critical reason: {reasons}"

    tone_samples = [
        prepare_tts("MSG.FUEL_CRITICAL", {}) or "",
        prepare_tts("MSG.FSS_PROGRESS_25", {}) or "",
        prepare_tts("MSG.FSS_LAST_BODY", {}) or "",
        prepare_tts("MSG.MILESTONE_REACHED", {"target": "SOL", "next_target": "LHS 20"}) or "",
    ]
    forbidden = ("musisz", "powinienes", "natychmiast", "top 1", "top1", "jedyna opcja")
    for text in tone_samples:
        lower = str(text or "").lower()
        assert lower.strip(), "Tone audit sample should not be empty"
        for phrase in forbidden:
            assert phrase not in lower, f"Non-neutral wording detected: '{phrase}' in '{text}'"


def test_f7_quality_gates_and_smoke_baseline(ctx: TestContext) -> None:
    """
    F7 quality gate baseline:
    - widget strip order and visibility contract,
    - single-slot panel policy (P0 can override),
    - mode detector + TTL + manual safety contract,
    - risk/rebuy deterministic mapping,
    - cargo VaR fallback/confidence contract.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    assert PulpitTab._WIDGET_ORDER[:4] == ["mode", "risk", "cash", "route"], (
        f"Unexpected widget prefix: {PulpitTab._WIDGET_ORDER}"
    )
    assert set(PulpitTab._WIDGET_ALWAYS) == {"mode", "risk", "cash", "route"}, (
        f"Unexpected always-visible widgets: {PulpitTab._WIDGET_ALWAYS}"
    )
    assert PulpitTab._WIDGET_MAX_VISIBLE == 7, (
        f"Expected widget visibility cap=7, got: {PulpitTab._WIDGET_MAX_VISIBLE}"
    )
    assert PulpitTab._PANEL_MAX_ACTIONS == 6, (
        f"Expected panel action cap=6, got: {PulpitTab._PANEL_MAX_ACTIONS}"
    )

    contract = build_risk_rebuy_contract(
        {
            "risk_status": "RISK_LOW",
            "exploration_value_estimated": 0.0,
            "exobio_value_estimated": 0.0,
            "credits": 900_000.0,
            "rebuy_cost": 1_000_000.0,
        }
    )
    assert contract.rebuy_label == "NO REBUY", f"Expected NO REBUY, got: {contract.rebuy_label}"
    assert contract.risk_label == "CRIT", f"Expected CRIT on NO REBUY, got: {contract.risk_label}"

    cargo_value_estimator.reset_runtime()
    cargo_value_estimator.update_cargo_snapshot(
        {"Inventory": [{"Name": "Unknown Cargo", "Count": 5}]},
        source="smoke.f7.cargo",
    )
    estimate = cargo_value_estimator.estimate_cargo_value(cargo_tons=5.0)
    assert estimate.source == "fallback", f"Expected fallback source, got: {estimate.source}"
    assert estimate.confidence == "LOW", f"Expected LOW confidence, got: {estimate.confidence}"
    assert int(round(estimate.cargo_expected_cr)) == 100_000, (
        f"Unexpected fallback expected value: {estimate.cargo_expected_cr}"
    )
    assert estimate.cargo_floor_cr > 0.0, "Cargo floor should stay positive in fallback mode"

    saved_snapshot = app_state.get_mode_state_snapshot()
    saved_is_docked = bool(getattr(app_state, "is_docked", False))
    saved_state_keys = {
        "mode_id": config.STATE.get("mode_id"),
        "mode_source": config.STATE.get("mode_source"),
        "mode_confidence": config.STATE.get("mode_confidence"),
        "mode_since": config.STATE.get("mode_since"),
        "mode_ttl": config.STATE.get("mode_ttl"),
        "is_docked": config.STATE.get("is_docked"),
    }
    saved_signals = {}
    for name in (
        "_mode_signal_docked",
        "_mode_signal_combat_active",
        "_mode_signal_combat_last_ts",
        "_mode_signal_hardpoints_since",
        "_mode_signal_exploration_active",
        "_mode_signal_exploration_last_ts",
        "_mode_signal_mining_active",
        "_mode_signal_mining_last_ts",
        "_mode_signal_mining_loadout",
        "_mode_last_emit_signature",
    ):
        saved_signals[name] = getattr(app_state, name)
    saved_overlay = getattr(app_state, "mode_overlay", None)
    saved_combat_silence = bool(getattr(app_state, "mode_combat_silence", False))

    settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
    saved_ttl = {}
    if isinstance(settings, dict):
        for key in ("mode.ttl.combat_sec", "mode.ttl.exploration_sec", "mode.ttl.mining_sec"):
            saved_ttl[key] = settings.get(key)
        settings["mode.ttl.combat_sec"] = 1.0
        settings["mode.ttl.exploration_sec"] = 120.0
        settings["mode.ttl.mining_sec"] = 90.0

    try:
        with app_state.lock:
            app_state.mode_id = "NORMAL"
            app_state.mode_source = "AUTO"
            app_state.mode_confidence = 0.60
            app_state.mode_since = time.time()
            app_state.mode_ttl = None
            app_state.mode_overlay = None
            app_state.mode_combat_silence = False
            app_state.is_docked = False
            app_state._mode_signal_docked = False
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = 0.0
            app_state._mode_signal_hardpoints_since = None
            app_state._mode_signal_exploration_active = False
            app_state._mode_signal_exploration_last_ts = 0.0
            app_state._mode_signal_mining_active = False
            app_state._mode_signal_mining_last_ts = 0.0
            app_state._mode_signal_mining_loadout = False
            app_state._mode_last_emit_signature = ""
            app_state._persist_mode_state_locked()
        app_state.publish_mode_state(force=True)

        app_state.set_mode_manual("EXPLORATION", source="smoke.f7.mode.manual")
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"in_combat": True, "risk_status": "RISK_HIGH"},
            source="smoke.f7.mode.manual.safety",
        )
        snap_manual = app_state.get_mode_state_snapshot()
        assert snap_manual.get("mode_id") == "EXPLORATION", (
            f"Manual lock broken by AUTO signal: {snap_manual}"
        )
        assert snap_manual.get("mode_source") == "MANUAL", (
            f"Expected MANUAL source, got: {snap_manual}"
        )
        assert snap_manual.get("mode_overlay") == "COMBAT", (
            f"Expected COMBAT safety overlay, got: {snap_manual}"
        )
        assert bool(snap_manual.get("mode_combat_silence")) is True, (
            f"Expected combat_silence ON under safety overlay, got: {snap_manual}"
        )

        app_state.set_mode_auto(source="smoke.f7.mode.auto")
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"in_combat": True, "risk_status": "RISK_HIGH"},
            source="smoke.f7.mode.auto.signal",
        )
        snap_auto = app_state.get_mode_state_snapshot()
        assert snap_auto.get("mode_id") == "COMBAT", (
            f"Expected COMBAT in AUTO mode, got: {snap_auto}"
        )
        assert snap_auto.get("mode_ttl") == 1.0, (
            f"Expected COMBAT TTL override=1.0, got: {snap_auto}"
        )

        with app_state.lock:
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = time.time() - 2.0
        app_state.refresh_mode_state(source="smoke.f7.mode.auto.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        assert snap_expired.get("mode_id") == "NORMAL", (
            f"Expected NORMAL after TTL expiry, got: {snap_expired}"
        )
        assert snap_expired.get("mode_ttl") is None, (
            f"Expected empty TTL after expiry, got: {snap_expired}"
        )
    finally:
        with app_state.lock:
            app_state.mode_id = str(saved_snapshot.get("mode_id") or "NORMAL")
            app_state.mode_source = str(saved_snapshot.get("mode_source") or "AUTO")
            app_state.mode_confidence = float(saved_snapshot.get("mode_confidence") or 0.60)
            app_state.mode_since = float(saved_snapshot.get("mode_since") or time.time())
            ttl = saved_snapshot.get("mode_ttl")
            app_state.mode_ttl = float(ttl) if ttl is not None else None
            app_state.mode_overlay = saved_overlay
            app_state.mode_combat_silence = saved_combat_silence
            app_state.is_docked = saved_is_docked
            for key, value in saved_signals.items():
                setattr(app_state, key, value)
            app_state._persist_mode_state_locked()

        for key, value in saved_state_keys.items():
            if value is None:
                config.STATE.pop(key, None)
            else:
                config.STATE[key] = value

        if isinstance(settings, dict):
            for key, value in saved_ttl.items():
                if value is None:
                    settings.pop(key, None)
                else:
                    settings[key] = value

        app_state.publish_mode_state(force=True)
        cargo_value_estimator.reset_runtime()
        ctx.clear_queue()


def test_f4_cross_module_voice_priority_baseline(_ctx: TestContext) -> None:
    """
    F4 cross-module voice priority baseline:
    - Cash-In preempts Summary in the same window.
    - Summary is suppressed after recent Survival High.
    """
    reset_dispatcher_runtime_state()

    base_ctx = {
        "system": "SMOKE_F4_PRIORITY_SYSTEM",
        "risk_status": "RISK_MEDIUM",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
    }

    with (
        patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
        patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False]),
        patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
    ):
        summary_ok = emit_insight(
            "summary",
            message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
            source="exploration_summary",
            event_type="SYSTEM_SUMMARY",
            context=base_ctx,
            priority="P3_LOW",
            dedup_key="smoke:f4:summary",
            cooldown_scope="entity",
            cooldown_seconds=45.0,
        )
        cash_ok = emit_insight(
            "cash-in",
            message_id="MSG.CASH_IN_ASSISTANT",
            source="cash_in_assistant",
            event_type="CASH_IN_REVIEW",
            context=base_ctx,
            priority="P2_NORMAL",
            dedup_key="smoke:f4:cash",
            cooldown_scope="entity",
            cooldown_seconds=90.0,
        )

    assert summary_ok is True, "Expected summary TTS in first F4 priority step"
    assert cash_ok is True, "Expected cash-in preemption over summary/global cooldown"
    second_call = powiedz_mock.call_args_list[1]
    second_ctx = second_call.kwargs.get("context") or {}
    assert second_ctx.get("voice_priority_reason") == "cross_module_preempt_higher_force", (
        f"Expected preemption reason for cash-in, got: {second_ctx}"
    )

    reset_dispatcher_runtime_state()
    with (
        patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
        patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True),
        patch("logic.insight_dispatcher._notify.powiedz"),
    ):
        survival_ok = emit_insight(
            "survival",
            message_id="MSG.SURVIVAL_REBUY_HIGH",
            source="survival_rebuy_awareness",
            event_type="SURVIVAL_RISK_CHANGED",
            context=base_ctx,
            priority="P1_HIGH",
            dedup_key="smoke:f4:survival",
            cooldown_scope="entity",
            cooldown_seconds=120.0,
        )
        summary_after_survival = emit_insight(
            "summary",
            message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
            source="exploration_summary",
            event_type="SYSTEM_SUMMARY",
            context=base_ctx,
            priority="P3_LOW",
            dedup_key="smoke:f4:summary2",
            cooldown_scope="entity",
            cooldown_seconds=45.0,
        )

    assert survival_ok is True, "Expected survival high to speak"
    assert summary_after_survival is False, "Expected lower-priority summary suppression after survival high"


def test_f4_quality_gates_invariants(ctx: TestContext) -> None:
    """
    F4 quality gate pack:
    - Summary auto non-flood,
    - Cash-In decision space contract (2-3 + Pomijam),
    - Survival no-rebuy critical non-flood,
    - Cross-module priority deterministic preemption.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    app_state.current_system = "SMOKE_F4_QUALITY_SYSTEM"
    app_state.last_exploration_summary_signature = None
    app_state.last_cash_in_signature = None
    app_state.cash_in_skip_signature = None
    app_state.last_survival_rebuy_signature = None
    reset_dispatcher_runtime_state()
    survival_events.reset_survival_rebuy_state()

    sample = ExitSummaryData(
        system_name="SMOKE_F4_QUALITY_SYSTEM",
        scanned_bodies=9,
        total_bodies=12,
        elw_count=1,
        elw_value=19_000_000.0,
        ww_count=1,
        ww_value=3_300_000.0,
        ww_t_count=1,
        ww_t_value=3_300_000.0,
        hmc_t_count=1,
        hmc_t_value=1_600_000.0,
        biology_species_count=2,
        biology_value=5_000_000.0,
        bonus_discovery=800_000.0,
        total_value=29_000_000.0,
    )

    with (
        patch.object(app_state.exit_summary, "build_summary_data", return_value=sample),
        patch.object(
            app_state,
            "system_value_engine",
            new=type("DummyEngine", (), {"calculate_totals": lambda self: {"total": 44_000_000.0}})(),
        ),
    ):
        first = summary_events.trigger_exploration_summary(mode="auto", gui_ref=None)
        second = summary_events.trigger_exploration_summary(mode="auto", gui_ref=None)

    assert first, "Expected first auto summary emit"
    assert not second, "Expected second auto summary to be signature-suppressed"

    first_batch = ctx.drain_queue()
    summary_payloads = [
        item[1]
        for item in first_batch
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "exploration_summary"
    ]
    cash_payloads = [
        item[1]
        for item in first_batch
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "cash_in_assistant"
    ]
    assert len(summary_payloads) == 1, f"Expected one summary payload, got: {summary_payloads}"
    assert len(cash_payloads) == 1, f"Expected one cash-in payload, got: {cash_payloads}"
    options = (cash_payloads[-1] or {}).get("options") or []
    skip_action = (cash_payloads[-1] or {}).get("skip_action") or {}
    assert 2 <= len(options) <= 3, f"Expected 2-3 cash-in options, got: {options}"
    assert str(skip_action.get("label") or "").strip() == "Pomijam", (
        f"Expected Pomijam in cash-in skip action, got: {skip_action}"
    )

    ctx.clear_queue()
    survival_events.handle_journal_event(
        {
            "event": "LoadGame",
            "StarSystem": "SMOKE_F4_QUALITY_SYSTEM",
            "Credits": 100_000,
            "Rebuy": 900_000,
        },
        gui_ref=None,
    )
    survival_events.handle_journal_event(
        {
            "event": "LoadGame",
            "StarSystem": "SMOKE_F4_QUALITY_SYSTEM",
            "Credits": 100_000,
            "Rebuy": 900_000,
        },
        gui_ref=None,
    )
    survival_batch = ctx.drain_queue()
    survival_payloads = [
        item[1]
        for item in survival_batch
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "survival_rebuy"
    ]
    assert len(survival_payloads) == 1, f"Expected one survival payload (non-flood), got: {survival_payloads}"
    assert (survival_payloads[-1] or {}).get("level") == "critical", (
        f"Expected critical survival payload, got: {survival_payloads[-1]}"
    )

    reset_dispatcher_runtime_state()
    base_ctx = {
        "system": "SMOKE_F4_QUALITY_SYSTEM",
        "risk_status": "RISK_MEDIUM",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
    }
    with (
        patch("logic.insight_dispatcher._notify.DEBOUNCER.can_send", return_value=True),
        patch("logic.insight_dispatcher._notify._should_speak_tts", side_effect=[True, False]),
        patch("logic.insight_dispatcher._notify.powiedz") as powiedz_mock,
    ):
        summary_ok = emit_insight(
            "summary",
            message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
            source="exploration_summary",
            event_type="SYSTEM_SUMMARY",
            context=base_ctx,
            priority="P3_LOW",
            dedup_key="smoke:f4:quality:summary",
            cooldown_scope="entity",
            cooldown_seconds=45.0,
        )
        cash_ok = emit_insight(
            "cash-in",
            message_id="MSG.CASH_IN_ASSISTANT",
            source="cash_in_assistant",
            event_type="CASH_IN_REVIEW",
            context=base_ctx,
            priority="P2_NORMAL",
            dedup_key="smoke:f4:quality:cash",
            cooldown_scope="entity",
            cooldown_seconds=90.0,
        )

    assert summary_ok is True, "Expected summary emit in priority gate smoke"
    assert cash_ok is True, "Expected cash-in preemption in priority gate smoke"
    second_ctx = powiedz_mock.call_args_list[1].kwargs.get("context") or {}
    assert second_ctx.get("voice_priority_reason") == "cross_module_preempt_higher_force", (
        f"Expected deterministic preemption reason, got: {second_ctx}"
    )


def test_trade_station_state_reset_on_system_change(_ctx: TestContext) -> None:
    class DummyVar:
        def __init__(self, value: str = "") -> None:
            self._value = value

        def get(self) -> str:
            return self._value

        def set(self, value: str) -> None:
            self._value = value

    class DummyAuto:
        def __init__(self) -> None:
            self.hidden = False

        def hide(self) -> None:
            self.hidden = True

    class DummyTrade:
        def __init__(self, start_system: str, start_station: str, last_key: str | None) -> None:
            self.var_start_system = DummyVar(start_system)
            self.var_start_station = DummyVar(start_station)
            self.ac_station = DummyAuto()
            self._start_system_last_key = last_key
            self.hint_updates = 0

        def _normalize_key(self, value: str) -> str:
            return str(value or "").strip().lower()

        def _get_station_input(self) -> str:
            return (self.var_start_station.get() or "").strip()

        def _clear_station_hint(self) -> None:
            return None

        def _update_station_hint(self) -> None:
            self.hint_updates += 1

    # No real system change -> station stays.
    same = DummyTrade(start_system="Sol ", start_station="Jameson Memorial", last_key="sol")
    TradeTab._on_start_system_changed(same)
    assert same.var_start_station.get() == "Jameson Memorial", "Station should stay when system key is unchanged"
    assert not same.ac_station.hidden, "Autocomplete should not hide when system key is unchanged"

    # Real system change -> station resets + suggestions hidden.
    changed = DummyTrade(start_system="Achenar", start_station="Jameson Memorial", last_key="sol")
    TradeTab._on_start_system_changed(changed)
    assert changed.var_start_station.get() == "", "Station should reset on real system change"
    assert changed.ac_station.hidden, "Autocomplete suggestions should hide after system change"
    assert changed._start_system_last_key == "achenar", "Last normalized system key should update"

    # Initial trace with unknown previous key -> no forced reset.
    initial = DummyTrade(start_system="Shinrarta Dezhra", start_station="Jameson Memorial", last_key=None)
    TradeTab._on_start_system_changed(initial)
    assert initial.var_start_station.get() == "Jameson Memorial", "Initial trace should not clear prefilled station"


def test_trade_station_picker_candidates_and_wiring(_ctx: TestContext) -> None:
    class DummyTradePicker:
        def __init__(self, cached: list[str], recent: list[str]) -> None:
            self._station_autocomplete_by_system = False
            self._station_lookup_online = False
            self._cached = list(cached)
            self._recent_stations = list(recent)

        def _get_cached_stations(self, _system: str) -> list[str]:
            return list(self._cached)

        def _remember_station_list(self, _system: str, _stations: list[str]) -> None:
            return None

        def _filter_stations(self, stations: list[str], _query: str) -> list[str]:
            return list(stations)

    cached_first = DummyTradePicker(cached=["Jameson Memorial"], recent=["Ohm City"])
    out_cached = TradeTab._load_station_candidates(cached_first, "Sol")
    assert out_cached == ["Jameson Memorial"], "Picker should prioritize cached station list"

    recent_fallback = DummyTradePicker(cached=[], recent=["Ohm City", "Jameson Memorial"])
    out_recent = TradeTab._load_station_candidates(recent_fallback, "Sol")
    assert out_recent == ["Ohm City", "Jameson Memorial"], "Picker should fallback to recent stations"

    trade_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/trade.py")
    with open(trade_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    assert "def _open_station_picker_dialog" in content, "Missing station picker dialog handler"
    assert "Wybierz stacje..." in content, "Missing station picker button label"
    assert "<Control-space>" in content, "Missing station picker keyboard shortcut binding"


def test_spansh_feedback_smoke_pack_coverage(_ctx: TestContext) -> None:
    # 1) Copy/export matrix source of truth is in planner_base.
    planner_base_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/planner_base.py")
    with open(planner_base_path, "r", encoding="utf-8", errors="ignore") as f:
        planner_base = f.read()
    for label in ("Kopiuj wiersze", "Kopiuj do Excela"):
        assert label in planner_base, f"Missing '{label}' in planner base menu source"

    # 2) All planner-base tabs must attach the same context menu parity.
    parity_tabs = [
        "gui/tabs/spansh/ammonia.py",
        "gui/tabs/spansh/elw.py",
        "gui/tabs/spansh/hmc.py",
        "gui/tabs/spansh/exomastery.py",
        "gui/tabs/spansh/riches.py",
    ]
    for rel_path in parity_tabs:
        path = os.path.join(ROOT_DIR, rel_path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        assert "SpanshPlannerBase" in content, f"{rel_path}: expected SpanshPlannerBase inheritance"
        assert "_attach_default_results_context_menu(" in content, (
            f"{rel_path}: missing default results context menu attach"
        )

    # 3) Dedicated tabs (neutron/trade) must still expose explicit copy/export actions.
    for rel_path in ("gui/tabs/spansh/neutron.py", "gui/tabs/spansh/trade.py"):
        path = os.path.join(ROOT_DIR, rel_path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for label in ("Kopiuj wiersze", "Kopiuj do Excela"):
            assert label in content, f"{rel_path}: missing '{label}' action"

    # 4) Verify the key feedback-regression tests are present in this smoke module.
    this_file = os.path.join(ROOT_DIR, "tools/smoke_tests_beckendy.py")
    with open(this_file, "r", encoding="utf-8", errors="ignore") as f:
        self_content = f.read()
    required_tests = [
        "test_spansh_system_copy_mapping",
        "test_spansh_copy_mode_actions",
        "test_spansh_export_actions_and_formats",
        "test_low_fuel_transient_startup_sco_guard",
        "test_neutron_empty_state_skeleton_overlay",
        "test_spansh_empty_state_skeleton_overlay_parity",
        "test_window_resize_hitbox_wiring",
        "test_trade_table_first_map_layout_refresh",
        "test_startup_window_deferred_show",
        "test_trade_split_view_layout_wiring",
        "test_trade_station_name_normalization",
        "test_trade_multi_commodity_aliases_and_metrics",
        "test_fss_last_body_before_full_9_of_10",
        "test_fss_last_body_before_full_11_of_12",
        "test_tts_polish_diacritics_global",
        "test_exobio_sample_progress_sequence",
        "test_trade_station_state_reset_on_system_change",
        "test_trade_station_picker_candidates_and_wiring",
        "test_trade_payload_forever_omits_market_age",
        "test_f4_cash_in_assistant_baseline",
        "test_f5_combat_awareness_baseline",
        "test_f5_dispatcher_priority_matrix_baseline",
        "test_f5_voice_policy_contract_baseline",
        "test_f5_anti_spam_regression_baseline",
    ]
    for test_name in required_tests:
        assert f"def {test_name}(" in self_content, f"Missing regression test function: {test_name}"


def test_neutron_empty_state_skeleton_overlay(_ctx: TestContext) -> None:
    neutron_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/neutron.py")
    with open(neutron_path, "r", encoding="utf-8", errors="ignore") as f:
        neutron_content = f.read()

    assert 'common.render_table_treeview(self.lst, "neutron", [])' in neutron_content, (
        "Neutron should render skeleton table columns on startup"
    )
    assert 'display_mode="overlay_body"' in neutron_content, (
        "Neutron empty state should use overlay_body mode"
    )

    empty_state_path = os.path.join(ROOT_DIR, "gui/empty_state.py")
    with open(empty_state_path, "r", encoding="utf-8", errors="ignore") as f:
        empty_state_content = f.read()

    assert "def _detect_treeview_header_height" in empty_state_content, (
        "empty_state should detect treeview header height for body-only overlay"
    )
    assert "height=-header_h" in empty_state_content, (
        "overlay should be clipped to treeview body below header"
    )


def test_spansh_empty_state_skeleton_overlay_parity(_ctx: TestContext) -> None:
    planner_base_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/planner_base.py")
    with open(planner_base_path, "r", encoding="utf-8", errors="ignore") as f:
        planner_base_content = f.read()

    assert "from gui import empty_state" in planner_base_content, (
        "planner_base should import empty_state"
    )
    assert "common.render_table_treeview(list_widget, self._schema_id, [])" in planner_base_content, (
        "planner_base should render skeleton columns for treeview tabs"
    )
    assert "display_mode=\"overlay_body\"" in planner_base_content, (
        "planner_base should use body-only overlay for treeview empty-state"
    )

    trade_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/trade.py")
    with open(trade_path, "r", encoding="utf-8", errors="ignore") as f:
        trade_content = f.read()

    assert "from gui import empty_state" in trade_content, "trade tab should import empty_state"
    assert "common.render_table_treeview(self.lst_trade, \"trade\", [])" in trade_content, (
        "trade tab should render skeleton columns on startup"
    )
    assert "display_mode=\"overlay_body\"" in trade_content, (
        "trade tab should use body-only overlay for empty-state"
    )


def test_window_resize_hitbox_wiring(_ctx: TestContext) -> None:
    app_path = os.path.join(ROOT_DIR, "gui/app.py")
    with open(app_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    required_snippets = [
        "self._init_window_resize_hitbox()",
        "def _init_window_resize_hitbox(self) -> None:",
        "self._resize_hitbox_px = 8",
        "self.root.bind_all(\"<Motion>\", self._on_resize_motion, add=\"+\")",
        "self.root.bind_all(\"<ButtonPress-1>\", self._on_resize_press, add=\"+\")",
        "self.root.bind_all(\"<B1-Motion>\", self._on_resize_drag, add=\"+\")",
        "self.root.bind_all(\"<ButtonRelease-1>\", self._on_resize_release, add=\"+\")",
        "def _is_resize_allowed(self) -> bool:",
        "def _detect_resize_zone(self, x_root: int, y_root: int):",
        "def _cursor_for_resize_zone(zone):",
        "return \"sb_h_double_arrow\"",
        "return \"sb_v_double_arrow\"",
        "return \"size_nw_se\"",
    ]

    for snippet in required_snippets:
        assert snippet in content, f"Missing resize hitbox wiring snippet: {snippet}"


def test_trade_table_first_map_layout_refresh(_ctx: TestContext) -> None:
    trade_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/trade.py")
    with open(trade_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    required_snippets = [
        "self._trade_table_layout_ready: bool = False",
        "self._trade_table_layout_retry_count: int = 0",
        "self.lst_trade.bind(\"<Map>\", self._on_trade_table_mapped, add=\"+\")",
        "def _on_trade_table_mapped(self, _event=None) -> None:",
        "def _refresh_trade_table_layout(self) -> None:",
        "self.root.after_idle(self._refresh_trade_table_layout)",
        "if not self.lst_trade.winfo_viewable():",
        "self._trade_table_layout_retry_count += 1",
        "if self._trade_table_layout_retry_count <= 10:",
        "self.root.after(60, self._refresh_trade_table_layout)",
        "common.render_table_treeview(self.lst_trade, \"trade\", rows)",
    ]

    for snippet in required_snippets:
        assert snippet in content, f"Missing trade first-map layout refresh snippet: {snippet}"


def test_startup_window_deferred_show(_ctx: TestContext) -> None:
    main_path = os.path.join(ROOT_DIR, "main.py")
    with open(main_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    required_snippets = [
        "root = tk.Tk()",
        "root.withdraw()",
        "def _show_main_window():",
        "root.deiconify()",
        "root.after(0, _show_main_window)",
    ]
    for snippet in required_snippets:
        assert snippet in content, f"Missing deferred startup-window snippet: {snippet}"


def test_trade_split_view_layout_wiring(_ctx: TestContext) -> None:
    trade_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/trade.py")
    with open(trade_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    required_snippets = [
        "self.trade_split = ttk.PanedWindow(fr, orient=tk.VERTICAL)",
        "self.trade_split.add(self.trade_top_wrap, weight=4)",
        "self.trade_split.add(self.trade_bottom_wrap, weight=2)",
        "self.var_trade_details_toggle = tk.StringVar(value=\"Pokaz szczegoly kroku\")",
        "command=self._toggle_trade_details",
        "def _toggle_trade_details(self) -> None:",
        "def _set_trade_details_collapsed(self, collapsed: bool, *, force: bool = False) -> None:",
        "self._clear_trade_leg_details(collapse=True)",
    ]

    for snippet in required_snippets:
        assert snippet in content, f"Missing trade split-view layout snippet: {snippet}"


def test_global_scrollbar_style_and_window_chrome_wiring(_ctx: TestContext) -> None:
    app_path = os.path.join(ROOT_DIR, "gui/app.py")
    with open(app_path, "r", encoding="utf-8", errors="ignore") as f:
        app_content = f.read()

    required_app_snippets = [
        "sb_kwargs = {",
        "\"troughcolor\": C_BG,",
        "\"arrowcolor\": C_FG,",
        "style.configure(",
        "\"Horizontal.TScale\",",
        "troughcolor=C_ACC,",
        "bordercolor=\"#d0ccc6\",",
        "borderwidth=0,",
        "style.configure(\"TScrollbar\", **sb_kwargs)",
        "style.configure(\"Vertical.TScrollbar\", **sb_kwargs)",
        "style.configure(\"Horizontal.TScrollbar\", **sb_kwargs)",
        "style.map(",
        "\"Horizontal.TScrollbar\",",
        "style.configure(",
        "\"TPanedwindow\",",
        "style.configure(\"Vertical.Sash\", background=C_ACC)",
        "style.configure(\"Horizontal.Sash\", background=C_ACC)",
        "apply_renata_orange_window_chrome(self.root)",
    ]
    for snippet in required_app_snippets:
        assert snippet in app_content, f"Missing global scrollbar/window-chrome wiring snippet: {snippet}"

    chrome_path = os.path.join(ROOT_DIR, "gui/window_chrome.py")
    with open(chrome_path, "r", encoding="utf-8", errors="ignore") as f:
        chrome_content = f.read()
    required_chrome_snippets = [
        "def apply_window_chrome_colors(",
        "DwmSetWindowAttribute",
        "_DWMWA_CAPTION_COLOR = 35",
        "caption_hex=\"#ff7100\"",
    ]
    for snippet in required_chrome_snippets:
        assert snippet in chrome_content, f"Missing window chrome helper snippet: {snippet}"

    files_with_explicit_vertical_style = [
        os.path.join(ROOT_DIR, "gui/common_tables.py"),
        os.path.join(ROOT_DIR, "gui/tabs/settings.py"),
        os.path.join(ROOT_DIR, "gui/tabs/spansh/trade.py"),
        os.path.join(ROOT_DIR, "gui/tabs/spansh/neutron.py"),
    ]
    for path in files_with_explicit_vertical_style:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        assert "style=\"Vertical.TScrollbar\"" in content, f"Missing explicit Vertical.TScrollbar usage in {path}"

    trade_path = os.path.join(ROOT_DIR, "gui/tabs/spansh/trade.py")
    with open(trade_path, "r", encoding="utf-8", errors="ignore") as f:
        trade_content = f.read()
    assert "style=\"Horizontal.TScale\"" in trade_content, "Missing explicit Horizontal.TScale usage for market age slider"


def test_insight_dispatcher_conflict_selection_deterministic(_ctx: TestContext) -> None:
    candidates = [
        Insight(
            text="normal",
            message_id="MSG.NORMAL",
            source="test",
            priority="P2_NORMAL",
        ),
        Insight(
            text="critical",
            message_id="MSG.CRITICAL",
            source="test",
            priority="P0_CRITICAL",
        ),
        Insight(
            text="high",
            message_id="MSG.HIGH",
            source="test",
            priority="P1_HIGH",
        ),
    ]

    selected_1 = pick_insight_for_emit(candidates)
    selected_2 = pick_insight_for_emit(candidates)

    assert selected_1 is not None, "Dispatcher should pick one insight"
    assert selected_2 is not None, "Dispatcher should be deterministic across runs"
    assert selected_1.message_id == "MSG.CRITICAL", "Highest priority insight should win"
    assert selected_2.message_id == "MSG.CRITICAL", "Selection must be deterministic"


def test_risk_trust_gate_blocks_low_trust_low_confidence(_ctx: TestContext) -> None:
    insight = Insight(
        text="low confidence hint",
        message_id="MSG.TEST_LOW",
        source="test_gate",
        priority="P2_NORMAL",
        context={
            "risk_status": "RISK_HIGH",
            "trust_status": "TRUST_LOW",
            "confidence": "low",
        },
    )
    decision = evaluate_risk_trust_gate(insight)
    assert decision.allow_emit is False, "Low trust + low confidence should block normal priority emits"
    assert decision.reason in {"low_confidence", "trust_low_confidence_low"}, (
        f"Unexpected gate reason: {decision.reason}"
    )


def test_risk_trust_gate_allows_critical_override(_ctx: TestContext) -> None:
    insight = Insight(
        text="critical warning",
        message_id="MSG.TEST_CRIT",
        source="test_gate",
        priority="P0_CRITICAL",
        context={
            "risk_status": "RISK_CRITICAL",
            "trust_status": "TRUST_LOW",
            "confidence": "low",
        },
    )
    decision = evaluate_risk_trust_gate(insight)
    assert decision.allow_emit is True, "Critical priority should bypass low trust/confidence gate"
    assert decision.reason == "priority_critical", f"Unexpected gate reason: {decision.reason}"


def test_no_wild_emits_in_migrated_event_modules(_ctx: TestContext) -> None:
    migrated_files = [
        os.path.join(ROOT_DIR, "logic/events/navigation_events.py"),
        os.path.join(ROOT_DIR, "logic/events/fuel_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_fss_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_dss_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_bio_events.py"),
        os.path.join(ROOT_DIR, "logic/events/survival_rebuy_awareness.py"),
        os.path.join(ROOT_DIR, "logic/events/combat_awareness.py"),
    ]

    for path in migrated_files:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        assert "emit_insight(" in content, f"Expected dispatcher usage in {path}"
        assert "powiedz(" not in content, f"Found direct powiedz() call in migrated module {path}"


def test_event_insight_mapping_core_contract(_ctx: TestContext) -> None:
    required_message_ids = [
        "MSG.NEXT_HOP",
        "MSG.JUMPED_SYSTEM",
        "MSG.DOCKED",
        "MSG.UNDOCKED",
        "MSG.FUEL_CRITICAL",
        "MSG.FSS_PROGRESS_25",
        "MSG.FSS_PROGRESS_50",
        "MSG.FSS_PROGRESS_75",
        "MSG.FSS_LAST_BODY",
        "MSG.SYSTEM_FULLY_SCANNED",
        "MSG.DSS_TARGET_HINT",
        "MSG.DSS_COMPLETED",
        "MSG.DSS_PROGRESS",
        "MSG.FIRST_MAPPED",
        "MSG.EXOBIO_SAMPLE_LOGGED",
        "MSG.EXOBIO_RANGE_READY",
        "MSG.EXOBIO_NEW_ENTRY",
        "MSG.CASH_IN_ASSISTANT",
        "MSG.SURVIVAL_REBUY_HIGH",
        "MSG.SURVIVAL_REBUY_CRITICAL",
        "MSG.COMBAT_AWARENESS_HIGH",
        "MSG.COMBAT_AWARENESS_CRITICAL",
    ]
    for message_id in required_message_ids:
        spec = get_insight_class(message_id)
        assert spec is not None, f"Missing insight class mapping for {message_id}"
        assert spec.canonical_event, f"Missing canonical_event for {message_id}"
        assert spec.kind, f"Missing kind for {message_id}"
        assert spec.decision_space, f"Missing decision_space for {message_id}"

    resolved = resolve_emit_contract(
        message_id="MSG.FUEL_CRITICAL",
        context={"system": "SOL"},
        event_type="SHIP_HEALTH_CHANGED",
        dedup_key=None,
        priority=None,
        cooldown_scope=None,
        cooldown_seconds=None,
    )
    assert resolved["dedup_key"] == "low_fuel:SOL", "Fuel dedup key should be deterministic from mapping template"
    assert resolved["priority"] == "P0_CRITICAL", "Fuel mapping should enforce critical priority by default"
    assert resolved["cooldown_scope"] == "entity", "Fuel mapping should use entity cooldown scope"
    ctx = resolved["context"] or {}
    assert ctx.get("canonical_event") == "SHIP_HEALTH_CHANGED", "Resolved context should expose canonical event"
    assert ctx.get("insight_kind") == "risk", "Resolved context should expose insight kind"
    assert ctx.get("decision_space") == "critical_warning", "Resolved context should expose decision space"


def test_capabilities_profile_contract(_ctx: TestContext) -> None:
    free_caps = resolve_capabilities({"plan.profile": "FREE"})
    assert free_caps.profile == PROFILE_FREE, "FREE profile should resolve as FREE"
    assert not free_caps.has(CAP_SETTINGS_FULL), "FREE should not expose full settings capability"
    assert not free_caps.has(CAP_UI_EXTENDED_TABS), "FREE should not expose extended tabs capability"
    assert not free_caps.has(CAP_TTS_ADVANCED_POLICY), "FREE should use conservative TTS policy"
    assert not free_caps.has(CAP_VOICE_STT), "FREE should keep STT capability disabled"

    pro_caps = resolve_capabilities({"plan.profile": "PRO"})
    assert pro_caps.profile == PROFILE_PRO, "PRO profile should resolve as PRO"
    assert pro_caps.has(CAP_SETTINGS_FULL), "PRO should expose full settings capability"
    assert pro_caps.has(CAP_UI_EXTENDED_TABS), "PRO should expose extended tabs capability"
    assert pro_caps.has(CAP_TTS_ADVANCED_POLICY), "PRO should expose advanced TTS policy capability"
    assert pro_caps.has(CAP_VOICE_STT), "PRO should expose STT capability"


def test_default_profile_contract_is_free_pub(_ctx: TestContext) -> None:
    default_caps = resolve_capabilities(config.DEFAULT_SETTINGS)
    assert default_caps.profile == PROFILE_FREE, "DEFAULT_SETTINGS should resolve to FREE profile"
    assert not default_caps.has(CAP_SETTINGS_FULL), "DEFAULT_SETTINGS should keep full settings capability disabled"
    assert not default_caps.has(CAP_UI_EXTENDED_TABS), "DEFAULT_SETTINGS should keep extended tabs capability disabled"
    assert not default_caps.has(CAP_TTS_ADVANCED_POLICY), "DEFAULT_SETTINGS should keep advanced TTS policy disabled"
    assert not default_caps.has(CAP_VOICE_STT), "DEFAULT_SETTINGS should keep STT capability disabled"


def test_no_plan_checks_in_action_modules(_ctx: TestContext) -> None:
    action_files = [
        os.path.join(ROOT_DIR, "logic/events/navigation_events.py"),
        os.path.join(ROOT_DIR, "logic/events/fuel_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_fss_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_dss_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_bio_events.py"),
        os.path.join(ROOT_DIR, "logic/events/exploration_misc_events.py"),
        os.path.join(ROOT_DIR, "logic/events/trade_events.py"),
        os.path.join(ROOT_DIR, "logic/events/survival_rebuy_awareness.py"),
        os.path.join(ROOT_DIR, "logic/events/combat_awareness.py"),
    ]
    forbidden_plan_conditions = (
        "features.tts.free_policy_enabled",
        "plan.profile",
    )
    for path in action_files:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for marker in forbidden_plan_conditions:
            assert marker not in content, f"Plan condition '{marker}' should not exist in action module {path}"


def test_combat_silence_invariant_zero_tts_except_critical(ctx: TestContext) -> None:
    ctx.clear_queue()
    ctx.reset_debouncer()

    normal = Insight(
        text="normal in combat",
        message_id="MSG.TEST_COMBAT_NORMAL",
        source="smoke",
        priority="P2_NORMAL",
        context={
            "in_combat": True,
            "risk_status": "RISK_MEDIUM",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        },
    )
    critical = Insight(
        text="critical in combat",
        message_id="MSG.TEST_COMBAT_CRITICAL",
        source="smoke",
        priority="P0_CRITICAL",
        context={
            "in_combat": True,
            "risk_status": "RISK_CRITICAL",
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        },
    )

    assert should_speak(normal) is False, "combat silence should block non-critical TTS"
    assert should_speak(critical) is True, "combat silence should not block critical TTS"


def test_emit_insight_contract_gate_in_event_modules(_ctx: TestContext) -> None:
    event_dir = os.path.join(ROOT_DIR, "logic", "events")
    required_keywords = {
        "message_id",
        "source",
        "event_type",
        "context",
        "priority",
        "dedup_key",
        "cooldown_scope",
        "cooldown_seconds",
    }
    files_with_emit = 0
    calls_checked = 0

    for filename in os.listdir(event_dir):
        if not filename.endswith(".py"):
            continue
        path = os.path.join(event_dir, filename)
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            source = f.read()
        tree = ast.parse(source, filename=path)
        emit_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "emit_insight"
        ]
        if not emit_calls:
            continue
        files_with_emit += 1
        for call in emit_calls:
            calls_checked += 1
            kw_names = {kw.arg for kw in call.keywords if kw.arg is not None}
            missing = sorted(required_keywords - kw_names)
            assert not missing, (
                f"{path}: emit_insight() missing required contract keywords: {', '.join(missing)}"
            )

    assert files_with_emit > 0, "Expected at least one event module using emit_insight"
    assert calls_checked > 0, "Expected at least one emit_insight call to validate contract"


def test_runtime_free_pro_capabilities_smoke(_ctx: TestContext) -> None:
    settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
    assert isinstance(settings, dict), "Config runtime settings dict is unavailable"

    original = {
        "plan.profile": settings.get("plan.profile"),
        "features.tts.free_policy_enabled": settings.get("features.tts.free_policy_enabled"),
        CAP_TTS_ADVANCED_POLICY: settings.get(CAP_TTS_ADVANCED_POLICY),
        CAP_SETTINGS_FULL: settings.get(CAP_SETTINGS_FULL),
        CAP_UI_EXTENDED_TABS: settings.get(CAP_UI_EXTENDED_TABS),
        CAP_VOICE_STT: settings.get(CAP_VOICE_STT),
    }

    try:
        settings.update(capability_config_patch_from_free_policy(True))
        assert not has_capability(CAP_TTS_ADVANCED_POLICY), "FREE runtime should disable advanced TTS policy"
        assert not has_capability(CAP_SETTINGS_FULL), "FREE runtime should disable full settings capability"
        assert not has_capability(CAP_UI_EXTENDED_TABS), "FREE runtime should disable extended tabs capability"
        assert not has_capability(CAP_VOICE_STT), "FREE runtime should disable STT capability"

        settings.update(capability_config_patch_from_free_policy(False))
        assert has_capability(CAP_TTS_ADVANCED_POLICY), "PRO runtime should enable advanced TTS policy"
        assert has_capability(CAP_SETTINGS_FULL), "PRO runtime should enable full settings capability"
        assert has_capability(CAP_UI_EXTENDED_TABS), "PRO runtime should enable extended tabs capability"
        assert has_capability(CAP_VOICE_STT), "PRO runtime should enable STT capability"
    finally:
        for key, value in original.items():
            if value is None and key in settings:
                settings.pop(key, None)
            else:
                settings[key] = value


def test_f2_sell_intent_route_cross_module(ctx: TestContext) -> None:
    """
    F2 cross-module gate:
    Sell Assist decision -> intent handoff -> route awareness transition.
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    saved_awareness = app_state.get_route_awareness_snapshot()
    saved_nav_route = dict(getattr(app_state, "nav_route", {}) or {})
    saved_current_system = str(getattr(app_state, "current_system", "") or "")
    saved_route = list(route_manager.route)
    saved_route_type = route_manager.route_type
    saved_route_index = int(route_manager.current_index)
    saved_milestones = list(getattr(app_state, "spansh_milestones", []) or [])
    saved_milestone_mode = getattr(app_state, "spansh_milestone_mode", None)

    try:
        route_manager.clear_route()
        app_state.clear_spansh_milestones(source="smoke.f2.cross")
        app_state.clear_nav_route(source="smoke.f2.cross")
        app_state.update_route_awareness(
            route_mode="idle",
            route_target="",
            route_progress_percent=0,
            next_system="",
            is_off_route=False,
            source="smoke.f2.cross",
        )

        rows = [
            {
                "from_system": "SOL",
                "from_station": "Galileo",
                "to_system": "LHS 20",
                "to_station": "Ohm City",
                "total_profit": 1_300_000,
                "profit": 5500,
                "amount": 240,
                "distance_ly": 40.0,
                "jumps": 1,
                "source_status": "ONLINE_LIVE",
                "confidence": "high",
                "data_age_seconds": 600,
                "updated_ago": "10m",
            },
            {
                "from_system": "LHS 20",
                "from_station": "Ohm City",
                "to_system": "TAU CETI",
                "to_station": "Ortiz Moreno City",
                "total_profit": 1_000_000,
                "profit": 4100,
                "amount": 240,
                "distance_ly": 50.0,
                "jumps": 2,
                "source_status": "ONLINE_LIVE",
                "confidence": "high",
                "data_age_seconds": 900,
                "updated_ago": "15m",
            },
        ]

        decision = trade_logic.build_sell_assist_decision_space(rows, jump_range=48.0)
        options = decision.get("options") or []
        assert len(options) in {2, 3}, f"Expected 2-3 options, got: {len(options)}"
        assert (decision.get("skip_action") or {}).get("label") == "Pomijam", (
            f"Expected skip label Pomijam, got: {decision.get('skip_action')}"
        )

        selected = options[0]
        target = str(selected.get("to_system") or "").strip()
        assert target, f"Selected option should expose to_system target, got: {selected}"

        handoff = trade_logic.handoff_sell_assist_to_route_intent(
            selected,
            set_route_intent=app_state.set_route_intent,
            source="smoke.f2.cross",
        )
        assert handoff.get("ok"), f"Expected successful intent handoff, got: {handoff}"

        snap_intent = app_state.get_route_awareness_snapshot()
        assert snap_intent.get("route_mode") == "intent", (
            f"Expected intent mode after handoff, got: {snap_intent}"
        )
        assert str(snap_intent.get("route_target") or "") == target, (
            f"Expected route target {target}, got: {snap_intent}"
        )
        assert not bool(snap_intent.get("is_off_route")), (
            f"Intent handoff should not mark off-route, got: {snap_intent}"
        )

        app_state.set_system("SOL")
        navigation_events.handle_navroute_update(
            {
                "event": "NavRoute",
                "EndSystem": target,
                "Route": [
                    {"StarSystem": "SOL"},
                    {"StarSystem": target},
                ],
            },
            gui_ref=None,
        )

        snap_awareness = app_state.get_route_awareness_snapshot()
        assert snap_awareness.get("route_mode") == "awareness", (
            f"Expected awareness mode after navroute update, got: {snap_awareness}"
        )
        assert str(snap_awareness.get("route_target") or "") == target, (
            f"Expected awareness target {target}, got: {snap_awareness}"
        )
        assert not bool(snap_awareness.get("is_off_route")), (
            f"Expected on-route state after aligned navroute update, got: {snap_awareness}"
        )
    finally:
        app_state.set_system(saved_current_system)
        app_state.update_route_awareness(
            route_mode=str(saved_awareness.get("route_mode") or "idle"),
            route_target=str(saved_awareness.get("route_target") or ""),
            route_progress_percent=int(saved_awareness.get("route_progress_percent") or 0),
            next_system=str(saved_awareness.get("next_system") or ""),
            is_off_route=bool(saved_awareness.get("is_off_route")),
            source="smoke.f2.cross.restore",
        )

        if saved_nav_route.get("systems"):
            app_state.set_nav_route(
                endpoint=saved_nav_route.get("endpoint"),
                systems=saved_nav_route.get("systems"),
                source="smoke.f2.cross.restore",
            )
        else:
            app_state.clear_nav_route(source="smoke.f2.cross.restore")

        if saved_milestones:
            app_state.set_spansh_milestones(
                saved_milestones,
                mode=saved_milestone_mode,
                source="smoke.f2.cross.restore",
            )
        else:
            app_state.clear_spansh_milestones(source="smoke.f2.cross.restore")

        if saved_route:
            route_manager.set_route(saved_route, route_type=str(saved_route_type or "smoke"))
            route_manager.current_index = min(saved_route_index, len(saved_route))
        else:
            route_manager.clear_route()


# --- TESTY: F8 QUALITY PACK --------------------------------------------------


def test_f8_quality_pack_baseline(ctx: TestContext) -> None:
    """
    Smoke dla paczki F8:
    - feed logbook (whitelist + chips),
    - mapowanie Journal -> Entry,
    - pinboard filter,
    - templates (mining + trade),
    - nawigacja przez route intent (bez auto-route).
    """
    ctx.clear_queue()
    ctx.reset_debouncer()

    saved_awareness = app_state.get_route_awareness_snapshot()
    try:
        market_event = {
            "event": "MarketSell",
            "timestamp": "2026-02-16T22:30:00Z",
            "StarSystem": "Diagaundri",
            "StationName": "Ray Gateway",
            "BodyName": "Diagaundri A 1",
            "Type": "Gold",
            "Count": 64,
            "SellPrice": 12000,
        }

        feed_item = build_logbook_feed_item(market_event)
        assert isinstance(feed_item, dict), "Expected logbook feed item for MarketSell"
        assert str(feed_item.get("default_category") or "") == "Handel/Transakcje", (
            f"Unexpected default category: {feed_item}"
        )
        assert str(resolve_logbook_nav_target(feed_item) or "") == "Ray Gateway", (
            f"Expected station target from logbook feed, got: {feed_item}"
        )

        chips = extract_navigation_chips(feed_item)
        assert len(chips) >= 2, f"Expected navigation chips SYSTEM/STATION, got: {chips}"
        chip_targets = [resolve_chip_nav_target(chip) for chip in chips]
        assert "Ray Gateway" in chip_targets, f"Expected STATION chip target, got: {chips}"

        draft = build_mvp_entry_draft(feed_item.get("raw_event") or {})
        assert isinstance(draft, dict), "Expected MVP draft from logbook raw_event"

        with tempfile.TemporaryDirectory() as tmp:
            repo_path = os.path.join(tmp, "entries.jsonl")
            repo = EntryRepository(path=repo_path)

            created = repo.create_entry(draft)
            target = str(resolve_entry_nav_target(created) or "")
            assert target == "Ray Gateway", f"Expected entry nav target to station, got: {created}"

            repo.pin_entry(str(created.get("id")), True)
            pinned = repo.list_entries(filters={"is_pinned": True}, sort="updated_desc")
            assert len(pinned) == 1, f"Expected one pinned entry, got: {pinned}"

            mining_template = build_template_entry(
                "mining_hotspot",
                {
                    "commodity": "Platinum",
                    "system_name": "Colonia",
                    "body_name": "Colonia AB 2 Ring A",
                    "ring_type": "Metallic",
                },
            )
            trade_template = build_template_entry(
                "trade_route",
                {
                    "from_system": "Diagaundri",
                    "from_station": "Ray Gateway",
                    "to_system": "Achenar",
                    "to_station": "Dawes Hub",
                    "profit_per_t": 12000,
                    "pad_size": "L",
                    "distance_ls": 84,
                    "permit_required": False,
                },
            )
            mining_entry = repo.create_entry(mining_template)
            trade_entry = repo.create_entry(trade_template)

            assert str(mining_entry.get("entry_type") or "") == "mining_hotspot", (
                f"Unexpected mining template entry contract: {mining_entry}"
            )
            assert str(trade_entry.get("entry_type") or "") == "trade_route", (
                f"Unexpected trade template entry contract: {trade_entry}"
            )

        snap = app_state.set_route_intent("Ray Gateway", source="smoke.f8.quality.intent")
        assert str(snap.get("route_mode") or "") == "intent", f"Expected intent mode, got: {snap}"
        assert str(snap.get("route_target") or "") == "Ray Gateway", (
            f"Expected route target Ray Gateway, got: {snap}"
        )
        assert int(snap.get("route_progress_percent") or 0) == 0, (
            f"Expected zero progress on intent setup, got: {snap}"
        )
    finally:
        app_state.update_route_awareness(
            route_mode=str(saved_awareness.get("route_mode") or "idle"),
            route_target=str(saved_awareness.get("route_target") or ""),
            route_progress_percent=int(saved_awareness.get("route_progress_percent") or 0),
            next_system=str(saved_awareness.get("next_system") or ""),
            is_off_route=bool(saved_awareness.get("is_off_route")),
            source="smoke.f8.quality.restore",
        )


def test_f9_entry_context_menu_contract(_ctx: TestContext) -> None:
    """
    Smoke dla F9 ticket #1:
    - typowany target wpisu (STATION/BODY/SYSTEM),
    - przeniesienie wpisu miedzy kategoriami bez utraty metadanych.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = EntryRepository(path=os.path.join(tmp, "entries.jsonl"))
        created = repo.create_entry(
            {
                "category_path": "Handel/Trasy",
                "title": "Trasa A-B",
                "body": "Opis",
                "location": {
                    "system_name": "Diagaundri",
                    "station_name": "Ray Gateway",
                    "body_name": "Diagaundri A 1",
                },
                "source": {"kind": "manual"},
                "payload": {"note": "f9"},
            }
        )
        resolved = resolve_entry_nav_target_typed(created)
        assert resolved == ("STATION", "Ray Gateway"), f"Unexpected typed target: {resolved}"

        moved = repo.update_entry(
            str(created.get("id")),
            {"category_path": "Eksploracja/Odkrycia"},
        )
        assert str(moved.get("category_path") or "") == "Eksploracja/Odkrycia", (
            f"Category move failed: {moved}"
        )
        assert str((moved.get("payload") or {}).get("note") or "") == "f9", (
            f"Payload unexpectedly changed after move: {moved}"
        )
        assert resolve_entry_nav_target(moved) == "Ray Gateway", f"Fallback changed: {moved}"


def test_f9_manual_metadata_edit_contract(_ctx: TestContext) -> None:
    """
    Smoke dla F9 ticket #2:
    - reczna zmiana kategorii i tagow,
    - brak naruszenia entry_type/source/payload.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = EntryRepository(path=os.path.join(tmp, "entries.jsonl"))
        created = repo.create_entry(
            {
                "category_path": "Handel/Transakcje",
                "title": "Sprzedaz",
                "body": "Test",
                "tags": ["trade", "auto"],
                "entry_type": "trade_route",
                "source": {"kind": "journal_event", "event_name": "MarketSell"},
                "payload": {"rank": 1},
            }
        )
        updated = repo.update_entry(
            str(created.get("id")),
            {
                "category_path": "Moje/Ulubione",
                "tags": ["auto", "manualny", "manualny"],
            },
        )
        assert str(updated.get("category_path") or "") == "Moje/Ulubione", (
            f"Category edit failed: {updated}"
        )
        assert list(updated.get("tags") or []) == ["auto", "manualny"], (
            f"Tag edit failed: {updated}"
        )
        assert str(updated.get("entry_type") or "") == "trade_route", (
            f"entry_type changed unexpectedly: {updated}"
        )
        assert str((updated.get("source") or {}).get("event_name") or "") == "MarketSell", (
            f"source changed unexpectedly: {updated}"
        )
        assert int((updated.get("payload") or {}).get("rank") or 0) == 1, (
            f"payload changed unexpectedly: {updated}"
        )


def test_f9_filter_popover_contract(_ctx: TestContext) -> None:
    """
    Smoke dla F9 ticket #3:
    - multi-tag mode ALL/ANY,
    - data Do liczona do konca dnia.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = EntryRepository(path=os.path.join(tmp, "entries.jsonl"))
        repo.create_entry(
            {
                "category_path": "Test/A",
                "title": "Trade Safe",
                "body": "",
                "tags": ["trade", "safe"],
                "created_at": "2026-02-17T08:00:00Z",
                "updated_at": "2026-02-17T08:00:00Z",
            }
        )
        repo.create_entry(
            {
                "category_path": "Test/B",
                "title": "Trade Risk",
                "body": "",
                "tags": ["trade", "risk"],
                "created_at": "2026-02-17T22:30:00Z",
                "updated_at": "2026-02-17T22:30:00Z",
            }
        )
        repo.create_entry(
            {
                "category_path": "Test/C",
                "title": "Next Day",
                "body": "",
                "tags": ["exploration"],
                "created_at": "2026-02-18T00:10:00Z",
                "updated_at": "2026-02-18T00:10:00Z",
            }
        )

        all_items = repo.list_entries(
            filters={"tags": ["trade", "safe"], "tags_mode": "all"},
            sort="title_az",
        )
        any_items = repo.list_entries(
            filters={"tags": ["trade", "safe"], "tags_mode": "any"},
            sort="title_az",
        )
        day_items = repo.list_entries(
            filters={
                "date_from": "2026-02-17T00:00:00Z",
                "date_to": "2026-02-17T23:59:59Z",
            },
            sort="title_az",
        )

        assert [item.get("title") for item in all_items] == ["Trade Safe"], (
            f"Unexpected ALL mode result: {all_items}"
        )
        assert [item.get("title") for item in any_items] == ["Trade Risk", "Trade Safe"], (
            f"Unexpected ANY mode result: {any_items}"
        )
        assert [item.get("title") for item in day_items] == ["Trade Risk", "Trade Safe"], (
            f"Unexpected end-of-day range result: {day_items}"
        )


# --- RUNNER ------------------------------------------------------------------


TestFunc = Callable[[TestContext], None]
TestSpec = Tuple[str, TestFunc]


def run_all_tests() -> int:
    ctx = TestContext()
    _ensure_voice_disabled()

    tests: List[TestSpec] = [
        ("test_low_fuel_basic", test_low_fuel_basic),
        ("test_low_fuel_transient_startup_sco_guard", test_low_fuel_transient_startup_sco_guard),
        ("test_trade_jackpot_basic", test_trade_jackpot_basic),
        ("test_fss_progress_basic", test_fss_progress_basic),
        ("test_bio_signals_basic", test_bio_signals_basic),
        ("test_dss_helper_completion_basic", test_dss_helper_completion_basic),
        ("test_first_footfall_basic", test_first_footfall_basic),
        ("test_table_schemas_basic", test_table_schemas_basic),
        ("test_spansh_system_copy_mapping", test_spansh_system_copy_mapping),
        ("test_spansh_copy_mode_actions", test_spansh_copy_mode_actions),
        ("test_spansh_export_actions_and_formats", test_spansh_export_actions_and_formats),
        ("test_trade_station_name_normalization", test_trade_station_name_normalization),
        ("test_trade_multi_commodity_aliases_and_metrics", test_trade_multi_commodity_aliases_and_metrics),
        ("test_trade_updated_buy_sell_pair_from_market_timestamps", test_trade_updated_buy_sell_pair_from_market_timestamps),
        ("test_trade_nested_source_destination_prices_for_details", test_trade_nested_source_destination_prices_for_details),
        ("test_fss_last_body_before_full_9_of_10", test_fss_last_body_before_full_9_of_10),
        ("test_fss_last_body_before_full_11_of_12", test_fss_last_body_before_full_11_of_12),
        ("test_tts_polish_diacritics_global", test_tts_polish_diacritics_global),
        ("test_exobio_sample_progress_sequence", test_exobio_sample_progress_sequence),
        ("test_f3_exploration_cross_module_invariants", test_f3_exploration_cross_module_invariants),
        ("test_f4_exploration_summary_baseline", test_f4_exploration_summary_baseline),
        ("test_f4_cash_in_assistant_baseline", test_f4_cash_in_assistant_baseline),
        ("test_f4_survival_rebuy_awareness_baseline", test_f4_survival_rebuy_awareness_baseline),
        ("test_f5_combat_awareness_baseline", test_f5_combat_awareness_baseline),
        ("test_f5_dispatcher_priority_matrix_baseline", test_f5_dispatcher_priority_matrix_baseline),
        ("test_f5_voice_policy_contract_baseline", test_f5_voice_policy_contract_baseline),
        ("test_f5_anti_spam_regression_baseline", test_f5_anti_spam_regression_baseline),
        ("test_f5_quality_gates_invariants", test_f5_quality_gates_invariants),
        ("test_f6_voice_ethics_compliance_baseline", test_f6_voice_ethics_compliance_baseline),
        ("test_f7_quality_gates_and_smoke_baseline", test_f7_quality_gates_and_smoke_baseline),
        ("test_f4_cross_module_voice_priority_baseline", test_f4_cross_module_voice_priority_baseline),
        ("test_f4_quality_gates_invariants", test_f4_quality_gates_invariants),
        ("test_trade_station_state_reset_on_system_change", test_trade_station_state_reset_on_system_change),
        ("test_trade_station_picker_candidates_and_wiring", test_trade_station_picker_candidates_and_wiring),
        ("test_spansh_feedback_smoke_pack_coverage", test_spansh_feedback_smoke_pack_coverage),
        ("test_neutron_empty_state_skeleton_overlay", test_neutron_empty_state_skeleton_overlay),
        ("test_spansh_empty_state_skeleton_overlay_parity", test_spansh_empty_state_skeleton_overlay_parity),
        ("test_window_resize_hitbox_wiring", test_window_resize_hitbox_wiring),
        ("test_trade_table_first_map_layout_refresh", test_trade_table_first_map_layout_refresh),
        ("test_startup_window_deferred_show", test_startup_window_deferred_show),
        ("test_trade_split_view_layout_wiring", test_trade_split_view_layout_wiring),
        ("test_global_scrollbar_style_and_window_chrome_wiring", test_global_scrollbar_style_and_window_chrome_wiring),
        ("test_insight_dispatcher_conflict_selection_deterministic", test_insight_dispatcher_conflict_selection_deterministic),
        ("test_risk_trust_gate_blocks_low_trust_low_confidence", test_risk_trust_gate_blocks_low_trust_low_confidence),
        ("test_risk_trust_gate_allows_critical_override", test_risk_trust_gate_allows_critical_override),
        ("test_no_wild_emits_in_migrated_event_modules", test_no_wild_emits_in_migrated_event_modules),
        ("test_event_insight_mapping_core_contract", test_event_insight_mapping_core_contract),
        ("test_capabilities_profile_contract", test_capabilities_profile_contract),
        ("test_default_profile_contract_is_free_pub", test_default_profile_contract_is_free_pub),
        ("test_no_plan_checks_in_action_modules", test_no_plan_checks_in_action_modules),
        ("test_combat_silence_invariant_zero_tts_except_critical", test_combat_silence_invariant_zero_tts_except_critical),
        ("test_emit_insight_contract_gate_in_event_modules", test_emit_insight_contract_gate_in_event_modules),
        ("test_runtime_free_pro_capabilities_smoke", test_runtime_free_pro_capabilities_smoke),
        ("test_f2_sell_intent_route_cross_module", test_f2_sell_intent_route_cross_module),
        ("test_ammonia_payload_snapshot", test_ammonia_payload_snapshot),
        ("test_exomastery_payload_snapshot", test_exomastery_payload_snapshot),
        ("test_riches_payload_snapshot", test_riches_payload_snapshot),
        ("test_elw_payload_snapshot", test_elw_payload_snapshot),
        ("test_hmc_payload_snapshot", test_hmc_payload_snapshot),
        ("test_trade_payload_snapshot", test_trade_payload_snapshot),
        ("test_trade_payload_forever_omits_market_age", test_trade_payload_forever_omits_market_age),
        ("test_neutron_payload_snapshot", test_neutron_payload_snapshot),
        ("test_start_system_fallback_source", test_start_system_fallback_source),
        ("test_resolve_planner_jump_range_auto", test_resolve_planner_jump_range_auto),
        ("test_f8_quality_pack_baseline", test_f8_quality_pack_baseline),
        ("test_f9_entry_context_menu_contract", test_f9_entry_context_menu_contract),
        ("test_f9_manual_metadata_edit_contract", test_f9_manual_metadata_edit_contract),
        ("test_f9_filter_popover_contract", test_f9_filter_popover_contract),
        ("test_route_planner_modules_smoke", test_route_planner_modules_smoke),
    ]

    print("=== RenataAI Backend Smoke Tests (T1) ===")
    print(f"Root dir: {ROOT_DIR}")
    print("-----------------------------------------")

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

    print("-----------------------------------------")
    print(f"Summary: {passed} passed, {failed} failed")

    return 1 if failed else 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
