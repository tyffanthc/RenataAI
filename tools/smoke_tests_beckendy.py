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
