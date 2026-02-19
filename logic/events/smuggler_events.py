# logic/events/smuggler_events.py

from __future__ import annotations

import time
from typing import Any, Dict

import config
from logic.utils import powiedz
from logic import utils
from logic.utils.renata_log import log_event_throttled


# --- SMUGGLER ALERT (S2-LOGIC-07) ---
CARGO_HAS_ILLEGAL = False           # czy na pokładzie jest nielegalny/stolen towar
SMUGGLER_WARNED_TARGETS = set()     # stacje/osady, dla których już padł alert
_SMUGGLER_WARNED_TS: dict[str, float] = {}
_SMUGGLER_STATE_LOADED = False
_SMUGGLER_LAST_PERSIST_TS = 0.0

_SMUGGLER_STATE_SCHEMA_VERSION = 1
_SMUGGLER_STATE_SECTION = "smuggler_warned_targets"


def _smuggler_ttl_sec() -> float:
    try:
        return max(60.0, float(config.get("anti_spam.smuggler_warned.ttl_sec", 1200.0)))
    except Exception:
        return 1200.0


def _smuggler_max_targets() -> int:
    try:
        return max(16, int(config.get("anti_spam.smuggler_warned.max_targets", 512)))
    except Exception:
        return 512


def _smuggler_persist_min_interval_sec() -> float:
    try:
        return max(0.5, float(config.get("anti_spam.persist_min_interval_sec", 2.0)))
    except Exception:
        return 2.0


def _coerce_ts(value: Any) -> float | None:
    try:
        ts = float(value)
    except Exception:
        return None
    if ts <= 0.0:
        return None
    return ts


def _prune_smuggler_cache(*, now: float | None = None) -> bool:
    global SMUGGLER_WARNED_TARGETS, _SMUGGLER_WARNED_TS

    changed = False
    ts_now = float(now if now is not None else time.time())
    stale_before = ts_now - _smuggler_ttl_sec()

    stale_targets = [
        target
        for target, ts in list(_SMUGGLER_WARNED_TS.items())
        if _coerce_ts(ts) is None or float(ts) < stale_before
    ]
    for target in stale_targets:
        _SMUGGLER_WARNED_TS.pop(target, None)
        SMUGGLER_WARNED_TARGETS.discard(target)
        changed = True

    max_targets = _smuggler_max_targets()
    if len(_SMUGGLER_WARNED_TS) > max_targets:
        ordered = sorted(_SMUGGLER_WARNED_TS.items(), key=lambda item: float(item[1]))
        for target, _ in ordered[: max(0, len(_SMUGGLER_WARNED_TS) - max_targets)]:
            _SMUGGLER_WARNED_TS.pop(target, None)
            SMUGGLER_WARNED_TARGETS.discard(target)
            changed = True
    return changed


def _snapshot_smuggler_cache(*, now: float | None = None) -> dict[str, Any]:
    ts_now = float(now if now is not None else time.time())
    _prune_smuggler_cache(now=ts_now)

    entries: list[dict[str, Any]] = []
    for target_key, ts in _SMUGGLER_WARNED_TS.items():
        if not target_key:
            continue
        entries.append({"target": str(target_key), "ts": float(ts)})
    entries.sort(key=lambda row: float(row.get("ts") or 0.0), reverse=True)
    entries = entries[: _smuggler_max_targets()]

    return {
        "schema_version": _SMUGGLER_STATE_SCHEMA_VERSION,
        "updated_at": int(ts_now),
        "entries": entries,
    }


def _persist_smuggler_cache(*, force: bool = False) -> bool:
    global _SMUGGLER_LAST_PERSIST_TS

    now = time.time()
    if (not force) and (_SMUGGLER_LAST_PERSIST_TS > 0.0):
        if (now - _SMUGGLER_LAST_PERSIST_TS) < _smuggler_persist_min_interval_sec():
            return False

    payload = _snapshot_smuggler_cache(now=now)
    try:
        config.update_anti_spam_state({_SMUGGLER_STATE_SECTION: payload})
        _SMUGGLER_LAST_PERSIST_TS = now
        return True
    except Exception:
        return False


def _load_smuggler_cache(*, force: bool = False) -> dict[str, Any]:
    global SMUGGLER_WARNED_TARGETS, _SMUGGLER_WARNED_TS
    global _SMUGGLER_STATE_LOADED

    if _SMUGGLER_STATE_LOADED and not force:
        return {"loaded": False, "reason": "already_loaded"}

    payload: dict[str, Any] = {}
    try:
        anti_spam_state = config.get_anti_spam_state(default={})
        raw = anti_spam_state.get(_SMUGGLER_STATE_SECTION) if isinstance(anti_spam_state, dict) else {}
        if isinstance(raw, dict):
            payload = raw
    except Exception:
        payload = {}

    loaded_ts: dict[str, float] = {}
    entries = payload.get("entries", [])
    if isinstance(entries, list):
        for row in entries:
            if not isinstance(row, dict):
                continue
            target_key = str(row.get("target") or "").strip()
            ts = _coerce_ts(row.get("ts"))
            if target_key and ts is not None:
                loaded_ts[target_key] = ts

    _SMUGGLER_WARNED_TS = loaded_ts
    SMUGGLER_WARNED_TARGETS = set(loaded_ts.keys())
    _SMUGGLER_STATE_LOADED = True
    _prune_smuggler_cache()
    return {"loaded": bool(SMUGGLER_WARNED_TARGETS), "reason": "ok", "targets": len(SMUGGLER_WARNED_TARGETS)}


def reset_smuggler_runtime_state(*, persist: bool = False) -> None:
    global CARGO_HAS_ILLEGAL, SMUGGLER_WARNED_TARGETS
    global _SMUGGLER_WARNED_TS, _SMUGGLER_STATE_LOADED, _SMUGGLER_LAST_PERSIST_TS

    CARGO_HAS_ILLEGAL = False
    SMUGGLER_WARNED_TARGETS = set()
    _SMUGGLER_WARNED_TS = {}
    _SMUGGLER_STATE_LOADED = False
    _SMUGGLER_LAST_PERSIST_TS = 0.0
    if persist:
        _persist_smuggler_cache(force=True)


def update_illegal_cargo(ev: Dict[str, Any]):
    """
    S2-LOGIC-07 — aktualizacja flagi CARGO_HAS_ILLEGAL
    na podstawie eventu Cargo.

    Szukamy w Inventory towarów z flagami typu Illegal / Stolen / IsStolen.

    Przeniesione z EventHandler._update_illegal_cargo.
    """
    global CARGO_HAS_ILLEGAL

    inventory = ev.get("Inventory") or ev.get("Cargo") or []
    if not isinstance(inventory, list):
        return

    has_illegal = False

    for item in inventory:
        if not isinstance(item, dict):
            continue

        # Journal bywa różny, więc sprawdzamy kilka pól
        illegal = item.get("Illegal")
        stolen = item.get("Stolen")
        is_stolen = item.get("IsStolen")

        if illegal or stolen or is_stolen:
            has_illegal = True
            break

    CARGO_HAS_ILLEGAL = has_illegal


def handle_smuggler_alert(ev: Dict[str, Any], gui_ref=None):
    """
    S2-LOGIC-07 — Smuggler Alert (nielegalny ładunek przy zbliżaniu się do stacji).

    Eventy:
    - ApproachSettlement
    - DockingRequested

    Warunek:
    - na pokładzie jest nielegalny ładunek (CARGO_HAS_ILLEGAL == True)
    - dla danej stacji/osady nie padł jeszcze komunikat

    Przeniesione z EventHandler._check_smuggler_alert.
    """
    global CARGO_HAS_ILLEGAL, SMUGGLER_WARNED_TARGETS

    _load_smuggler_cache()
    _prune_smuggler_cache()

    if not CARGO_HAS_ILLEGAL:
        return

    event_name = ev.get("event")
    target_key = None
    target_label = None

    if event_name == "DockingRequested":
        station = ev.get("StationName") or ev.get("Station") or "UNKNOWN_STATION"
        target_key = f"STATION::{station}"
        target_label = station

    elif event_name == "ApproachSettlement":
        settlement = (
            ev.get("Name")
            or ev.get("SettlementName")
            or ev.get("BodyName")
            or "UNKNOWN_SETTLEMENT"
        )
        target_key = f"SETTLEMENT::{settlement}"
        target_label = settlement

    if not target_key:
        return

    # antyspam – tylko jeden komunikat na daną stację/osadę
    if target_key in SMUGGLER_WARNED_TARGETS:
        return

    SMUGGLER_WARNED_TARGETS.add(target_key)
    _SMUGGLER_WARNED_TS[target_key] = time.time()

    msg = "Uwaga. Nielegalny ładunek na pokładzie. Zalecam tryb cichego biegu."
    powiedz(
        msg,
        gui_ref,
        message_id="MSG.SMUGGLER_ILLEGAL_CARGO",
        context={"raw_text": msg},
    )

    # dla czytelności wrzucimy też w log Pulpitu
    try:
        utils.MSG_QUEUE.put(
            ("log", f"[SMUGGLER ALERT] {target_label} — wykryto nielegalny ładunek na pokładzie.")
        )
    except Exception as exc:
        log_event_throttled(
            "SMUGGLER:alert.log",
            10000,
            "SMUGGLER",
            "failed to write smuggler alert log to queue",
            error=f"{type(exc).__name__}: {exc}",
            target=target_label,
        )
    _persist_smuggler_cache()
