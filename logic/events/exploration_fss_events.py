# logic/events/exploration_fss_events.py

from __future__ import annotations

from typing import Any, Dict
import config

from logic.utils import DEBOUNCER
from logic.insight_dispatcher import emit_insight
from logic import utils
from logic.utils.renata_log import log_event_throttled
from app.state import app_state

from logic.events.exploration_high_value_events import (
    check_high_value_planet,
    reset_high_value_flags,
)
from logic.events.exploration_bio_events import reset_bio_flags
from logic.events.exploration_dss_events import reset_dss_helper_state
from logic.events.exploration_misc_events import reset_footfall_flags
from logic.events.exploration_awareness import reset_system_awareness


# --- FSS ASSISTANT (S2-LOGIC-02) ---
FSS_TOTAL_BODIES = 0       # ile cial w systemie (z FSSDiscoveryScan)
FSS_DISCOVERED = 0         # ile juz "zaliczonych" skanow
FSS_SCANNED_BODIES = set()  # BodyName/BodyID, zeby nie liczyc 2x

FSS_25_WARNED = False
FSS_50_WARNED = False
FSS_75_WARNED = False
FSS_LAST_WARNED = False
FSS_FULL_WARNED = False
FSS_HAD_DISCOVERY_SCAN = False
FSS_HAD_MANUAL_PROGRESS_SCAN = False
FSS_PENDING_EXIT_SUMMARY = False
FSS_PENDING_EXIT_SUMMARY_SYSTEM = None
FSS_PENDING_EXIT_SUMMARY_SCANNED = None
FSS_PENDING_EXIT_SUMMARY_TOTAL = None

# --- FIRST DISCOVERY (S2-LOGIC-05) ---
FIRST_SYS_DISC_WARNED = False           # komunikat o dziewiczym systemie
FIRST_BODY_DISC_WARNED_BODIES = set()   # ciala, dla ktorych padl komunikat discovery
FIRST_SYS_OPPORTUNITY_WARNED = False    # ostrozny komunikat "mozliwy first" przy niepelnych danych


def _fss_gate_context(system_name: str | None, *, body_name: str | None = None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "system": system_name,
        "risk_status": "RISK_LOW",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
        "fss_milestone_sequence": True,
    }
    if body_name:
        ctx["body"] = body_name
    return ctx


def _first_status_context(
    system_name: str | None,
    *,
    body_name: str | None = None,
    status_kind: str = "confirmed",
) -> Dict[str, Any]:
    if str(status_kind).strip().lower() == "opportunity":
        trust_status = "TRUST_MEDIUM"
        confidence = "mid"
    else:
        trust_status = "TRUST_HIGH"
        confidence = "high"

    ctx: Dict[str, Any] = {
        "system": system_name,
        "risk_status": "RISK_LOW",
        "var_status": "VAR_MEDIUM",
        "trust_status": trust_status,
        "confidence": confidence,
        "first_status_kind": status_kind,
    }
    if body_name:
        ctx["body"] = body_name
    return ctx


def _wire_exit_summary_to_runtime(gui_ref=None) -> None:
    """
    EXIT-SUMMARY-WIRE-01:
    Build and publish F4 exploration summary when FSS scan is complete.
    Emission goes through dispatcher via logic.events.exploration_summary.
    """
    global FSS_PENDING_EXIT_SUMMARY, FSS_PENDING_EXIT_SUMMARY_SYSTEM
    global FSS_PENDING_EXIT_SUMMARY_SCANNED, FSS_PENDING_EXIT_SUMMARY_TOTAL

    system_name = getattr(app_state, "current_system", None)
    # BUGS_FIX 16.5:
    # Arm summary only when BOTH conditions are met:
    # 1) player explicitly triggered FSS discovery scan (honk/FSS entry path)
    # 2) at least one non-AutoScan body progress event was counted
    # This prevents transit systems from arming summary from auto star scans.
    if not (bool(FSS_HAD_DISCOVERY_SCAN) and bool(FSS_HAD_MANUAL_PROGRESS_SCAN)):
        return

    # BUGS_FIX 16.5:
    # Arm summary on FSS full and emit it on next jump (FSDJump/CarrierJump) so fast
    # transit systems do not spam summary/cash-in while the commander is still busy.
    FSS_PENDING_EXIT_SUMMARY = True
    FSS_PENDING_EXIT_SUMMARY_SYSTEM = str(system_name or "").strip() or None
    FSS_PENDING_EXIT_SUMMARY_SCANNED = int(FSS_DISCOVERED) if int(FSS_DISCOVERED or 0) > 0 else None
    FSS_PENDING_EXIT_SUMMARY_TOTAL = int(FSS_TOTAL_BODIES) if int(FSS_TOTAL_BODIES or 0) > 0 else None


def flush_pending_exit_summary_on_jump(gui_ref=None) -> bool:
    """Emit armed FSS exit summary on the next system jump (before FSS reset)."""
    global FSS_PENDING_EXIT_SUMMARY, FSS_PENDING_EXIT_SUMMARY_SYSTEM
    global FSS_PENDING_EXIT_SUMMARY_SCANNED, FSS_PENDING_EXIT_SUMMARY_TOTAL
    if not bool(FSS_PENDING_EXIT_SUMMARY):
        return False

    system_name = str(FSS_PENDING_EXIT_SUMMARY_SYSTEM or "").strip() or None
    scanned_bodies = FSS_PENDING_EXIT_SUMMARY_SCANNED
    total_bodies = FSS_PENDING_EXIT_SUMMARY_TOTAL

    # Clear first to avoid sticky repeat on exceptions.
    FSS_PENDING_EXIT_SUMMARY = False
    FSS_PENDING_EXIT_SUMMARY_SYSTEM = None
    FSS_PENDING_EXIT_SUMMARY_SCANNED = None
    FSS_PENDING_EXIT_SUMMARY_TOTAL = None

    try:
        from logic.events.exploration_summary import trigger_exploration_summary

        trigger_exploration_summary(
            gui_ref=gui_ref,
            mode="auto",
            system_name=system_name,
            scanned_bodies=scanned_bodies,
            total_bodies=total_bodies,
        )
        return True
    except Exception:
        log_event_throttled(
            "exploration.fss.exit_summary_wire",
            5000,
            "FSS",
            "failed to trigger exploration summary after full scan",
            system=system_name,
            scanned_bodies=int(scanned_bodies or 0),
            total_bodies=int(total_bodies or 0),
        )
        return False


def reset_fss_progress() -> None:
    """Reset licznikow FSS oraz powiazanych flag discovery.

    To jest orkiestrator resetow eksploracyjnych:
    - czysci lokalny stan FSS oraz first-discovery,
    - resetuje flagi high-value planet,
    - resetuje flagi biologii,
    - resetuje flagi first footfall.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED, FSS_SCANNED_BODIES
    global FSS_25_WARNED, FSS_50_WARNED, FSS_75_WARNED, FSS_LAST_WARNED, FSS_FULL_WARNED
    global FSS_HAD_DISCOVERY_SCAN, FSS_HAD_MANUAL_PROGRESS_SCAN
    global FSS_PENDING_EXIT_SUMMARY, FSS_PENDING_EXIT_SUMMARY_SYSTEM
    global FSS_PENDING_EXIT_SUMMARY_SCANNED, FSS_PENDING_EXIT_SUMMARY_TOTAL
    global FIRST_SYS_DISC_WARNED, FIRST_BODY_DISC_WARNED_BODIES, FIRST_SYS_OPPORTUNITY_WARNED

    previous_system = str(getattr(app_state, "current_system", "") or "").strip()

    # Lokalny stan FSS
    FSS_TOTAL_BODIES = 0
    FSS_DISCOVERED = 0
    FSS_SCANNED_BODIES = set()
    FSS_25_WARNED = False
    FSS_50_WARNED = False
    FSS_75_WARNED = False
    FSS_LAST_WARNED = False
    FSS_FULL_WARNED = False
    FSS_HAD_DISCOVERY_SCAN = False
    FSS_HAD_MANUAL_PROGRESS_SCAN = False
    FSS_PENDING_EXIT_SUMMARY = False
    FSS_PENDING_EXIT_SUMMARY_SYSTEM = None
    FSS_PENDING_EXIT_SUMMARY_SCANNED = None
    FSS_PENDING_EXIT_SUMMARY_TOTAL = None

    # First discovery (system + ciala)
    FIRST_SYS_DISC_WARNED = False
    FIRST_BODY_DISC_WARNED_BODIES = set()
    FIRST_SYS_OPPORTUNITY_WARNED = False

    # Resety w innych modulach eksploracyjnych
    reset_high_value_flags()
    reset_bio_flags()
    reset_dss_helper_state()
    reset_footfall_flags()
    reset_system_awareness(previous_system)


def _set_fss_total_bodies(count: int):
    global FSS_TOTAL_BODIES, FSS_DISCOVERED, FSS_SCANNED_BODIES
    FSS_TOTAL_BODIES = max(count, 0)
    FSS_DISCOVERED = 0
    FSS_SCANNED_BODIES = set()


def _scan_body_label(ev: Dict[str, Any]) -> Any:
    return ev.get("BodyName") or ev.get("BodyID") or ev.get("Body") or None


def _scan_body_keys(ev: Dict[str, Any]) -> set[str]:
    """
    Build a small alias set for one body scan so mixed payloads (`BodyName` vs `BodyID`)
    do not double-count the same body.
    """
    keys: set[str] = set()
    body_id = ev.get("BodyID")
    if body_id is not None and str(body_id).strip() != "":
        keys.add(f"id:{body_id}")
    body_name = ev.get("BodyName") or ev.get("Body")
    if body_name is not None:
        text = str(body_name).strip()
        if text:
            keys.add(f"name:{text.casefold()}")
    return keys


def _sync_milestone_flags_after_late_body_count() -> None:
    """
    BUGS_FIX 16.2 follow-up:
    If BodyCount arrives late (after some bodies were already scanned), sync milestone
    flags to current progress without emitting retro catch-up TTS on the next scan.
    """
    global FSS_25_WARNED, FSS_50_WARNED, FSS_75_WARNED
    if FSS_TOTAL_BODIES <= 0:
        return
    try:
        progress = float(FSS_DISCOVERED or 0) / float(FSS_TOTAL_BODIES or 1)
    except Exception:
        return
    if progress >= 0.25:
        FSS_25_WARNED = True
    if progress >= 0.5:
        FSS_50_WARNED = True
    if progress >= 0.75:
        FSS_75_WARNED = True


def _check_fss_thresholds(gui_ref=None):
    """
    Sprawdza progi 25/50/75% i moment 'ostatnia planeta'.
    Odpala TTS tylko raz na prog (anty-spam flagami FSS_*_WARNED),
    a dodatkowo zabezpiecza przed glitchami z uzyciem DEBOUNCER-a.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED
    global FSS_25_WARNED, FSS_50_WARNED, FSS_75_WARNED, FSS_LAST_WARNED

    if FSS_TOTAL_BODIES <= 0:
        return

    progress = FSS_DISCOVERED / FSS_TOTAL_BODIES
    system_name = app_state.current_system or None

    # Milestone catch-up rule: when progress jumps over multiple thresholds in one step
    # (e.g. startup/recovery/system with many stars scanned quickly), emit only the
    # highest newly reached threshold to avoid 25% -> 50% -> 75% spam in sequence.
    threshold_specs: list[tuple[float, str, str, str]] = [
        (0.25, "FSS_25", "MSG.FSS_PROGRESS_25", "Dwadzieścia pięć procent systemu przeskanowane."),
        (0.5, "FSS_50", "MSG.FSS_PROGRESS_50", "Połowa systemu przeskanowana."),
        (0.75, "FSS_75", "MSG.FSS_PROGRESS_75", "Siedemdziesiąt pięć procent systemu przeskanowane."),
    ]
    warned_map = {
        "FSS_25": bool(FSS_25_WARNED),
        "FSS_50": bool(FSS_50_WARNED),
        "FSS_75": bool(FSS_75_WARNED),
    }
    newly_reached = [spec for spec in threshold_specs if progress >= spec[0] and not warned_map.get(spec[1], False)]
    if newly_reached:
        # Mark all crossed thresholds as warned so catch-up doesn't replay them later.
        if any(spec[1] == "FSS_25" for spec in newly_reached):
            FSS_25_WARNED = True
        if any(spec[1] == "FSS_50" for spec in newly_reached):
            FSS_50_WARNED = True
        if any(spec[1] == "FSS_75" for spec in newly_reached):
            FSS_75_WARNED = True
        _, deb_key, msg_id, text = newly_reached[-1]
        if DEBOUNCER.can_send(deb_key, 120, context=system_name):
            dedup_suffix = "25" if deb_key.endswith("25") else ("50" if deb_key.endswith("50") else "75")
            emit_insight(
                text,
                gui_ref=gui_ref,
                message_id=msg_id,
                source="exploration_fss_events",
                event_type="SYSTEM_SCANNED",
                context=_fss_gate_context(system_name),
                priority="P2_NORMAL",
                dedup_key=f"fss{dedup_suffix}:{system_name or 'unknown'}",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
            )

    # Ostatnia planeta do skanowania
    remaining = FSS_TOTAL_BODIES - FSS_DISCOVERED
    if not FSS_LAST_WARNED and FSS_TOTAL_BODIES > 1 and remaining == 1:
        FSS_LAST_WARNED = True
        if DEBOUNCER.can_send("FSS_LAST", 120, context=system_name):
            emit_insight(
                "Ostatnia planeta do skanowania.",
                gui_ref=gui_ref,
                message_id="MSG.FSS_LAST_BODY",
                source="exploration_fss_events",
                event_type="SYSTEM_SCANNED",
                context=_fss_gate_context(system_name),
                priority="P2_NORMAL",
                dedup_key=f"fss_last:{system_name or 'unknown'}",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
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
        emit_insight(
            "System w pełni przeskanowany.",
            gui_ref=gui_ref,
            message_id="MSG.SYSTEM_FULLY_SCANNED",
            source="exploration_fss_events",
            event_type="SYSTEM_SCANNED",
            context=_fss_gate_context(system_name),
            priority="P2_NORMAL",
            dedup_key=f"fss_full:{system_name or 'unknown'}",
            cooldown_scope="entity",
            cooldown_seconds=120.0,
        )
        FSS_FULL_WARNED = True
        _wire_exit_summary_to_runtime(gui_ref=gui_ref)
        return True

    return False


def handle_scan(ev: Dict[str, Any], gui_ref=None):
    """
    Obsluga eventu Scan - FSS progress, Discovery, High Value.
    To jest 1:1 przeniesiony EventHandler._handle_scan.
    """
    body_name = _scan_body_label(ev)
    body_keys = _scan_body_keys(ev)

    global FSS_SCANNED_BODIES, FSS_DISCOVERED, FSS_HAD_MANUAL_PROGRESS_SCAN
    global FIRST_SYS_DISC_WARNED, FIRST_BODY_DISC_WARNED_BODIES, FIRST_SYS_OPPORTUNITY_WARNED

    if not body_name:
        return

    # Jesli nie znamy jeszcze calkowitej liczby cial w systemie,
    # nie liczymy procentow - ale i tak mozemy policzyc discovery.
    # Czy to pierwszy skan w systemie (przed dodaniem do setu)?
    first_scan_in_system = len(FSS_SCANNED_BODIES) == 0

    # Jesli to nowe cialo - aktualizujemy licznik FSS
    already_counted = False
    if body_keys:
        already_counted = any(key in FSS_SCANNED_BODIES for key in body_keys)
    else:
        already_counted = body_name in FSS_SCANNED_BODIES

    if not already_counted:
        if body_keys:
            FSS_SCANNED_BODIES.update(body_keys)
        else:
            FSS_SCANNED_BODIES.add(body_name)
        FSS_DISCOVERED += 1
        scan_type = str(ev.get("ScanType") or "").strip().casefold()
        if scan_type != "autoscan":
            FSS_HAD_MANUAL_PROGRESS_SCAN = True

        # --- S2-LOGIC-05: First Discovery detection ---
        was_discovered = ev.get("WasDiscovered")
        # W journalu to jest zwykle bool; interesuje nas wyrazne False / 0
        if was_discovered is False or was_discovered == 0:
            # System - pierwszy skan w systemie i brak wczesniejszego odkrycia
            if first_scan_in_system and not FIRST_SYS_DISC_WARNED:
                emit_insight(
                    "Potwierdzono pierwsze odkrycie. Jesteś pierwszym odkrywcą tego układu.",
                    gui_ref=gui_ref,
                    message_id="MSG.FIRST_DISCOVERY",
                    source="exploration_fss_events",
                    event_type="BODY_DISCOVERED",
                    context=_first_status_context(app_state.current_system, status_kind="confirmed"),
                    priority="P2_NORMAL",
                    dedup_key=f"first_discovery_system:{app_state.current_system or 'unknown'}",
                    cooldown_scope="entity",
                    cooldown_seconds=120.0,
                )
                FIRST_SYS_DISC_WARNED = True

            # Planeta - indywidualny komunikat per cialo
            if body_name not in FIRST_BODY_DISC_WARNED_BODIES:
                emit_insight(
                    "Potwierdzono. To ciało nie ma wcześniejszego odkrywcy.",
                    gui_ref=gui_ref,
                    message_id="MSG.BODY_NO_PREV_DISCOVERY",
                    source="exploration_fss_events",
                    event_type="BODY_DISCOVERED",
                    context=_first_status_context(
                        app_state.current_system,
                        body_name=str(body_name),
                        status_kind="confirmed",
                    ),
                    priority="P3_LOW",
                    dedup_key=f"first_body:{body_name}",
                    cooldown_scope="entity",
                    cooldown_seconds=120.0,
                )
                FIRST_BODY_DISC_WARNED_BODIES.add(body_name)
        elif was_discovered is None and first_scan_in_system and not FIRST_SYS_OPPORTUNITY_WARNED:
            emit_insight(
                "Wygląda na okazję pierwszego odkrycia, ale czekam na potwierdzenie.",
                gui_ref=gui_ref,
                message_id="MSG.FIRST_DISCOVERY_OPPORTUNITY",
                source="exploration_fss_events",
                event_type="BODY_DISCOVERED",
                context=_first_status_context(app_state.current_system, status_kind="opportunity"),
                priority="P3_LOW",
                dedup_key=f"first_opportunity_system:{app_state.current_system or 'unknown'}",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
            )
            FIRST_SYS_OPPORTUNITY_WARNED = True

        # --- FSS progi + high-value planets ---
        _check_fss_thresholds(gui_ref)
        check_high_value_planet(ev, gui_ref)
        _maybe_speak_fss_full(gui_ref)


def handle_fss_discovery_scan(ev: Dict[str, Any], gui_ref=None):
    """
    Obsluga eventu FSSDiscoveryScan - ustawienie liczby cial w systemie.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED, FSS_SCANNED_BODIES, FSS_HAD_DISCOVERY_SCAN
    body_count = ev.get("BodyCount") or 0
    try:
        count = int(body_count)
    except Exception:
        log_event_throttled(
            "exploration.fss.body_count_parse",
            5000,
            "FSS",
            "invalid FSSDiscoveryScan BodyCount; ignoring event",
            body_count=body_count,
        )
        count = 0

    if count <= 0:
        return
    FSS_HAD_DISCOVERY_SCAN = True

    # Navigation events (Location/FSDJump/CarrierJump) already reset FSS state on
    # system entry. Repeating FSSDiscoveryScan in the same system should NOT wipe
    # current progress, otherwise milestones can be re-triggered from 0% and the
    # player hears stale percentages after partial scans.
    has_progress = bool(FSS_SCANNED_BODIES) or int(FSS_DISCOVERED or 0) > 0
    if has_progress:
        previous_total = int(FSS_TOTAL_BODIES or 0)
        # Keep progress and only refresh total body count metadata.
        FSS_TOTAL_BODIES = max(count, int(FSS_DISCOVERED or 0))
        if previous_total <= 0 and int(FSS_DISCOVERED or 0) > 0:
            _sync_milestone_flags_after_late_body_count()
        if FSS_TOTAL_BODIES != previous_total:
            utils.MSG_QUEUE.put(
                ("log", f"[FSS] Zaktualizowano BodyCount (bez resetu progresu): {previous_total} -> {FSS_TOTAL_BODIES}.")
            )
        return

    _set_fss_total_bodies(count)
    utils.MSG_QUEUE.put(
        ("log", f"[FSS] System ma {count} cial (wg FSSDiscoveryScan).")
    )


def handle_fss_all_bodies_found(ev: Dict[str, Any], gui_ref=None):
    """
    Obsluga eventu FSSAllBodiesFound - wszystko znalezione.
    """
    global FSS_TOTAL_BODIES, FSS_DISCOVERED
    if FSS_TOTAL_BODIES <= 0:
        return

    # FSSAllBodiesFound confirms discovery coverage in FSS, but should not
    # overwrite our Scan-based progress counter. Otherwise Renata can announce
    # "System w pelni przeskanowany" before the player actually reaches N/N scans.
    if FSS_DISCOVERED >= FSS_TOTAL_BODIES:
        _check_fss_thresholds(gui_ref)
        _maybe_speak_fss_full(gui_ref)
