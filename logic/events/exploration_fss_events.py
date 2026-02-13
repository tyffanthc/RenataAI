# logic/events/exploration_fss_events.py

from __future__ import annotations

from typing import Any, Dict
import config

from logic.utils import powiedz, DEBOUNCER
from logic import utils
from app.state import app_state

from logic.events.exploration_high_value_events import (
    check_high_value_planet,
    reset_high_value_flags,
)
from logic.events.exploration_bio_events import reset_bio_flags
from logic.events.exploration_misc_events import reset_footfall_flags


# --- FSS ASSISTANT (S2-LOGIC-02) ---
FSS_TOTAL_BODIES = 0       # ile ciaĹ‚ w systemie (z FSSDiscoveryScan)
FSS_DISCOVERED = 0         # ile juĹĽ â€žzaliczonychâ€ť skanĂłw
FSS_SCANNED_BODIES = set()  # BodyName/BodyID, ĹĽeby nie liczyÄ‡ 2x

FSS_25_WARNED = False
FSS_50_WARNED = False
FSS_75_WARNED = False
FSS_LAST_WARNED = False
FSS_FULL_WARNED = False

# --- FIRST DISCOVERY (S2-LOGIC-05) ---
FIRST_SYS_DISC_WARNED = False           # komunikat o dziewiczym systemie
FIRST_BODY_DISC_WARNED_BODIES = set()   # ciaĹ‚a, dla ktĂłrych padĹ‚ komunikat discovery


def _wire_exit_summary_to_runtime() -> None:
    """
    EXIT-SUMMARY-WIRE-01:
    Build and publish summary when we know FSS scan is complete.

    We keep this path UI-safe:
    - no new TTS in this ticket (log/panel only),
    - one summary snapshot per generated text (dedup),
    - graceful no-op on missing data.
    """
    try:
        if not bool(config.get("exit_summary_enabled", True)):
            return
    except Exception:
        return

    system_name = (getattr(app_state, "current_system", "") or "").strip()
    if not system_name:
        return

    try:
        summary_text = app_state.exit_summary.build_and_format(
            system_name=system_name,
            scanned_bodies=FSS_DISCOVERED if FSS_DISCOVERED > 0 else None,
            total_bodies=FSS_TOTAL_BODIES if FSS_TOTAL_BODIES > 0 else None,
        )
    except Exception:
        return

    if not summary_text:
        return

    previous = getattr(app_state, "last_exit_summary_text", None)
    if summary_text == previous:
        return

    app_state.last_exit_summary_text = summary_text
    for line in summary_text.splitlines():
        line = str(line).strip()
        if not line:
            continue
        utils.MSG_QUEUE.put(("log", f"[EXIT-SUMMARY] {line}"))


def reset_fss_progress() -> None:
    """Reset licznikĂłw FSS oraz powiÄ…zanych flag discovery.

    To jest orkiestrator resetĂłw eksploracyjnych:
    - czyĹ›ci lokalny stan FSS oraz first-discovery,
    - resetuje flagi high-value planet,
    - resetuje flagi biologii,
    - resetuje flagi first footfall.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED, FSS_SCANNED_BODIES
    global FSS_25_WARNED, FSS_50_WARNED, FSS_75_WARNED, FSS_LAST_WARNED, FSS_FULL_WARNED
    global FIRST_SYS_DISC_WARNED, FIRST_BODY_DISC_WARNED_BODIES

    # Lokalny stan FSS
    FSS_TOTAL_BODIES = 0
    FSS_DISCOVERED = 0
    FSS_SCANNED_BODIES = set()
    FSS_25_WARNED = False
    FSS_50_WARNED = False
    FSS_75_WARNED = False
    FSS_LAST_WARNED = False
    FSS_FULL_WARNED = False

    # First discovery (system + ciaĹ‚a)
    FIRST_SYS_DISC_WARNED = False
    FIRST_BODY_DISC_WARNED_BODIES = set()

    # Resety w innych moduĹ‚ach eksploracyjnych
    reset_high_value_flags()
    reset_bio_flags()
    reset_footfall_flags()


def _set_fss_total_bodies(count: int):
    global FSS_TOTAL_BODIES, FSS_DISCOVERED, FSS_SCANNED_BODIES
    FSS_TOTAL_BODIES = max(count, 0)
    FSS_DISCOVERED = 0
    FSS_SCANNED_BODIES = set()


def _check_fss_thresholds(gui_ref=None):
    """
    Sprawdza progi 25/50/75% i moment 'ostatnia planeta'.
    Odpala TTS tylko raz na prĂłg (anty-spam flagami FSS_*_WARNED),
    a dodatkowo zabezpiecza przed glitchami z uĹĽyciem DEBOUNCER-a.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED
    global FSS_25_WARNED, FSS_50_WARNED, FSS_75_WARNED, FSS_LAST_WARNED

    if FSS_TOTAL_BODIES <= 0:
        return

    progress = FSS_DISCOVERED / FSS_TOTAL_BODIES
    system_name = app_state.current_system or None

    # 25%
    if not FSS_25_WARNED and progress >= 0.25:
        # zachowujemy starÄ… logikÄ™ flag (jedno odpalenie na prĂłg)
        FSS_25_WARNED = True
        if DEBOUNCER.can_send("FSS_25", 120, context=system_name):
            powiedz(
                "Dwadzieścia pięć procent systemu przeskanowane.",
                gui_ref,
                message_id="MSG.FSS_PROGRESS_25",
                context={"system": system_name},
            )

    # 50%
    if not FSS_50_WARNED and progress >= 0.5:
        FSS_50_WARNED = True
        if DEBOUNCER.can_send("FSS_50", 120, context=system_name):
            powiedz(
                "PoĹ‚owa systemu przeskanowana.",
                gui_ref,
                message_id="MSG.FSS_PROGRESS_50",
                context={"system": system_name},
            )

    # 75%
    if not FSS_75_WARNED and progress >= 0.75:
        FSS_75_WARNED = True
        if DEBOUNCER.can_send("FSS_75", 120, context=system_name):
            powiedz(
                "Siedemdziesiąt pięć procent systemu przeskanowane.",
                gui_ref,
                message_id="MSG.FSS_PROGRESS_75",
                context={"system": system_name},
            )

    # Ostatnia planeta do skanowania
    remaining = FSS_TOTAL_BODIES - FSS_DISCOVERED
    if not FSS_LAST_WARNED and FSS_TOTAL_BODIES > 1 and remaining == 1:
        FSS_LAST_WARNED = True
        if DEBOUNCER.can_send("FSS_LAST", 120, context=system_name):
            powiedz(
                "Ostatnia planeta do skanowania.",
                gui_ref,
                message_id="MSG.FSS_LAST_BODY",
                context={"system": system_name},
            )


def _maybe_speak_fss_full(gui_ref=None) -> bool:
    """Emit full-scan message once; never emit last-body hint at 100%."""
    global FSS_FULL_WARNED

    if FSS_TOTAL_BODIES <= 0 or FSS_DISCOVERED < FSS_TOTAL_BODIES:
        return False

    system_name = app_state.current_system or None

    if FSS_FULL_WARNED:
        return True

    if DEBOUNCER.can_send("FSS_FULL", 120, context=system_name):
        powiedz(
            "System w pe?ni przeskanowany.",
            gui_ref,
            message_id="MSG.SYSTEM_FULLY_SCANNED",
            context={"system": system_name},
        )
        FSS_FULL_WARNED = True
        _wire_exit_summary_to_runtime()
        return True

    return False


def handle_scan(ev: Dict[str, Any], gui_ref=None):
    """
    ObsĹ‚uga eventu Scan â€” FSS progress, Discovery, High Value.
    To jest 1:1 przeniesiony EventHandler._handle_scan.
    """
    body_name = (
        ev.get("BodyName")
        or ev.get("BodyID")
        or ev.get("Body")
        or None
    )

    global FSS_SCANNED_BODIES, FSS_DISCOVERED
    global FIRST_SYS_DISC_WARNED, FIRST_BODY_DISC_WARNED_BODIES

    if not body_name:
        return

    # JeĹ›li nie znamy jeszcze caĹ‚kowitej liczby ciaĹ‚ w systemie,
    # nie liczymy procentĂłw â€“ ale i tak moĹĽemy policzyÄ‡ discovery.
    # Czy to pierwszy skan w systemie (przed dodaniem do setu)?
    first_scan_in_system = len(FSS_SCANNED_BODIES) == 0

    # JeĹ›li to nowe ciaĹ‚o â€“ aktualizujemy licznik FSS
    if body_name not in FSS_SCANNED_BODIES:
        FSS_SCANNED_BODIES.add(body_name)
        FSS_DISCOVERED += 1

        # --- S2-LOGIC-05: First Discovery detection ---
        was_discovered = ev.get("WasDiscovered")
        # W journalu to jest zwykle bool; interesuje nas wyraĹşne False / 0
        if was_discovered is False or was_discovered == 0:
            # System â€“ pierwszy skan w systemie i brak wczeĹ›niejszego odkrycia
            if first_scan_in_system and not FIRST_SYS_DISC_WARNED:
                powiedz(
                    "Gratulacje. JesteĹ› pierwszym czĹ‚owiekiem w tym ukĹ‚adzie.",
                    gui_ref,
                    message_id="MSG.FIRST_DISCOVERY",
                    context={"system": app_state.current_system},
                )
                FIRST_SYS_DISC_WARNED = True

            # Planeta â€“ indywidualny komunikat per ciaĹ‚o
            if body_name not in FIRST_BODY_DISC_WARNED_BODIES:
                powiedz("To ciaĹ‚o nie ma wczeĹ›niejszego odkrywcy.", gui_ref)
                FIRST_BODY_DISC_WARNED_BODIES.add(body_name)

        # --- FSS progi + high-value planets ---
        _check_fss_thresholds(gui_ref)
        check_high_value_planet(ev, gui_ref)
        _maybe_speak_fss_full(gui_ref)


def handle_fss_discovery_scan(ev: Dict[str, Any], gui_ref=None):
    """
    ObsĹ‚uga eventu FSSDiscoveryScan â€” ustawienie liczby ciaĹ‚ w systemie.
    """
    body_count = ev.get("BodyCount") or 0
    try:
        count = int(body_count)
    except Exception:
        count = 0

    reset_fss_progress()
    if count > 0:
        _set_fss_total_bodies(count)
        utils.MSG_QUEUE.put(
            ("log", f"[FSS] System ma {count} ciaĹ‚ (wg FSSDiscoveryScan).")
        )


def handle_fss_all_bodies_found(ev: Dict[str, Any], gui_ref=None):
    """
    ObsĹ‚uga eventu FSSAllBodiesFound â€” wszystko znalezione.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED
    if FSS_TOTAL_BODIES > 0:
        FSS_DISCOVERED = FSS_TOTAL_BODIES
        _check_fss_thresholds(gui_ref)
        _maybe_speak_fss_full(gui_ref)
