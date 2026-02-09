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
from typing import Callable, List, Tuple

# --- ŚCIEŻKI / IMPORTY --------------------------------------------------------


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config  # type: ignore
from logic.utils import MSG_QUEUE, DEBOUNCER  # type: ignore

from app.state import app_state  # type: ignore

from logic.events import fuel_events  # type: ignore
from logic.events import trade_events  # type: ignore
from logic.events import exploration_fss_events as fss_events  # type: ignore
from logic.events import exploration_bio_events as bio_events  # type: ignore
from logic.events import exploration_misc_events as misc_events  # type: ignore
from logic import spansh_payloads
from logic import spansh_client as spansh_client_logic  # type: ignore
from logic import neutron as neutron_logic  # type: ignore
from logic import riches as riches_logic  # type: ignore
from logic import ammonia as ammonia_logic  # type: ignore
from logic import elw_route as elw_logic  # type: ignore
from logic import hmc_route as hmc_logic  # type: ignore
from logic import exomastery as exomastery_logic  # type: ignore
from logic import trade as trade_logic  # type: ignore
from logic.rows_normalizer import normalize_trade_rows
from logic.tts.text_preprocessor import prepare_tts
from gui import common_tables  # type: ignore


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
        "25% systemu przeskanowane.",
        "Połowa systemu przeskanowana.",
        "75% systemu przeskanowane.",
        "Ostatnia planeta do skanowania.",
        "System w pełni przeskanowany.",
    ]
    assert any(fragment in joined for fragment in expected_fragments), (
        "Expected at least one FSS progress message in MSG_QUEUE, "
        f"got: {joined}"
    )


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
    required_labels = ["Kopiuj wiersze", "Kopiuj wiersz", "Kopiuj zaznaczone", "Kopiuj wszystko"]
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

    common_tables_path = os.path.join(ROOT_DIR, "gui/common_tables.py")
    with open(common_tables_path, "r", encoding="utf-8", errors="ignore") as f:
        table_content = f.read()
    assert table_content.count('selectmode="extended"') >= 2, (
        "Expected extended multi-select for listbox and treeview"
    )
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
        "Kopiuj CSV",
        "Kopiuj TSV",
        "CSV",
        "TSV",
        "Naglowki",
        "Wiersz",
        "Wszystko",
    ]
    for rel_path in files:
        path = os.path.join(ROOT_DIR, rel_path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for label in required_labels:
            assert label in content, f"Missing '{label}' export option in {rel_path}"
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

# --- RUNNER ------------------------------------------------------------------


TestFunc = Callable[[TestContext], None]
TestSpec = Tuple[str, TestFunc]


def run_all_tests() -> int:
    ctx = TestContext()
    _ensure_voice_disabled()

    tests: List[TestSpec] = [
        ("test_low_fuel_basic", test_low_fuel_basic),
        ("test_trade_jackpot_basic", test_trade_jackpot_basic),
        ("test_fss_progress_basic", test_fss_progress_basic),
        ("test_bio_signals_basic", test_bio_signals_basic),
        ("test_first_footfall_basic", test_first_footfall_basic),
        ("test_table_schemas_basic", test_table_schemas_basic),
        ("test_spansh_system_copy_mapping", test_spansh_system_copy_mapping),
        ("test_spansh_copy_mode_actions", test_spansh_copy_mode_actions),
        ("test_spansh_export_actions_and_formats", test_spansh_export_actions_and_formats),
        ("test_trade_station_name_normalization", test_trade_station_name_normalization),
        ("test_tts_polish_diacritics_global", test_tts_polish_diacritics_global),
        ("test_exobio_sample_progress_sequence", test_exobio_sample_progress_sequence),
        ("test_ammonia_payload_snapshot", test_ammonia_payload_snapshot),
        ("test_exomastery_payload_snapshot", test_exomastery_payload_snapshot),
        ("test_riches_payload_snapshot", test_riches_payload_snapshot),
        ("test_elw_payload_snapshot", test_elw_payload_snapshot),
        ("test_hmc_payload_snapshot", test_hmc_payload_snapshot),
        ("test_trade_payload_snapshot", test_trade_payload_snapshot),
        ("test_neutron_payload_snapshot", test_neutron_payload_snapshot),
        ("test_start_system_fallback_source", test_start_system_fallback_source),
        ("test_resolve_planner_jump_range_auto", test_resolve_planner_jump_range_auto),
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
