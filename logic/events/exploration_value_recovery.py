from __future__ import annotations

import json
from typing import Any, Dict

from app.state import app_state


_SYSTEM_EVENTS = {"Location", "FSDJump", "CarrierJump"}
_VALUE_EVENTS = {"Scan", "ScanOrganic", "CodexEntry", "SAAScanComplete"}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def recover_system_value_from_journal_lines(
    lines: list[str] | tuple[str, ...] | None,
    *,
    max_lines: int = 4000,
) -> Dict[str, Any]:
    if not isinstance(lines, (list, tuple)) or not lines:
        return {
            "recovered": False,
            "events": 0,
            "scan_events": 0,
            "bio_events": 0,
            "meta_events": 0,
            "used_system_fallback": 0,
            "reason": "no_lines",
        }

    engine = getattr(app_state, "system_value_engine", None)
    if engine is None:
        return {
            "recovered": False,
            "events": 0,
            "scan_events": 0,
            "bio_events": 0,
            "meta_events": 0,
            "used_system_fallback": 0,
            "reason": "no_engine",
        }

    current_system = _as_text(getattr(app_state, "current_system", ""))
    recovered_events = 0
    scan_events = 0
    bio_events = 0
    meta_events = 0
    used_system_fallback = 0

    for raw_line in list(lines)[-max_lines:]:
        try:
            ev = json.loads(raw_line)
        except Exception:
            continue
        if not isinstance(ev, dict):
            continue

        event_name = _as_text(ev.get("event"))
        if event_name in _SYSTEM_EVENTS:
            next_system = _as_text(ev.get("StarSystem"))
            if next_system:
                current_system = next_system
                try:
                    engine.set_current_system(next_system)
                except Exception:
                    pass
            continue

        if event_name not in _VALUE_EVENTS:
            continue

        ev_work = dict(ev)
        if not _as_text(ev_work.get("StarSystem")) and current_system:
            ev_work["StarSystem"] = current_system
            used_system_fallback += 1

        try:
            if event_name == "Scan":
                engine.analyze_scan_event(ev_work)
                recovered_events += 1
                scan_events += 1
                continue

            if event_name in {"ScanOrganic", "CodexEntry"}:
                engine.analyze_biology_event(ev_work)
                engine.analyze_discovery_meta_event(ev_work)
                recovered_events += 1
                bio_events += 1
                continue

            if event_name == "SAAScanComplete":
                engine.analyze_dss_scan_complete_event(ev_work)
                engine.analyze_discovery_meta_event(ev_work)
                recovered_events += 1
                meta_events += 1
        except Exception:
            continue

    return {
        "recovered": bool(recovered_events),
        "events": recovered_events,
        "scan_events": scan_events,
        "bio_events": bio_events,
        "meta_events": meta_events,
        "used_system_fallback": used_system_fallback,
        "reason": "ok",
    }


def bootstrap_system_value_from_journal_lines(
    lines: list[str] | tuple[str, ...] | None,
    *,
    max_lines: int = 4000,
) -> Dict[str, Any]:
    return recover_system_value_from_journal_lines(lines, max_lines=max_lines)
