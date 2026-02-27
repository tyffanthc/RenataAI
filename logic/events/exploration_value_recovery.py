from __future__ import annotations

import json
from typing import Any, Dict

from app.state import app_state
from logic.utils.renata_log import log_event_throttled


_SYSTEM_EVENTS = {"Location", "FSDJump", "CarrierJump"}
_VALUE_EVENTS = {
    "Scan",
    "ScanOrganic",
    "CodexEntry",
    "SAAScanComplete",
    "SellExplorationData",
    "MultiSellExplorationData",
    "SellOrganicData",
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _body_id_from_event(event: Dict[str, Any]) -> str:
    body = (
        event.get("BodyName")
        or event.get("Body")
        or (str(event.get("BodyID")) if event.get("BodyID") is not None else "")
    )
    return _as_text(body)


def recover_system_value_from_journal_lines(
    lines: list[str] | tuple[str, ...] | None,
    *,
    max_lines: int = 12000,
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
    scan_counted = 0
    dss_upgrade_applied = 0
    dss_skipped_missing_prior_scan = 0
    sale_reset_cartography = 0
    sale_reset_exobiology = 0

    for raw_line in list(lines)[-max_lines:]:
        try:
            ev = json.loads(raw_line)
        except Exception:
            log_event_throttled(
                "exploration.value_recovery.json",
                5000,
                "BOOTSTRAP",
                "value recovery skipped invalid journal line",
            )
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
                    log_event_throttled(
                        "exploration.value_recovery.set_system",
                        5000,
                        "BOOTSTRAP",
                        "value recovery failed to sync engine current system",
                        system=next_system,
                    )
            continue

        if event_name not in _VALUE_EVENTS:
            continue

        ev_work = dict(ev)
        if not _as_text(ev_work.get("StarSystem")) and current_system:
            ev_work["StarSystem"] = current_system
            used_system_fallback += 1

        try:
            if event_name == "Scan":
                before_total = float(engine.calculate_totals().get("total") or 0.0)
                engine.analyze_scan_event(ev_work)
                after_total = float(engine.calculate_totals().get("total") or 0.0)
                recovered_events += 1
                scan_events += 1
                if after_total > before_total:
                    scan_counted += 1
                continue

            if event_name in {"ScanOrganic", "CodexEntry"}:
                engine.analyze_biology_event(ev_work)
                engine.analyze_discovery_meta_event(ev_work)
                recovered_events += 1
                bio_events += 1
                continue

            if event_name == "SAAScanComplete":
                system_name = _as_text(ev_work.get("StarSystem")) or current_system
                body_id = _body_id_from_event(ev_work)
                stats_before = None
                row_before = None
                if system_name:
                    try:
                        stats_before = engine.get_system_stats(system_name)
                    except Exception:
                        log_event_throttled(
                            "exploration.value_recovery.get_stats",
                            5000,
                            "BOOTSTRAP",
                            "value recovery failed to read system stats snapshot",
                            system=system_name,
                        )
                        stats_before = None
                if stats_before and body_id:
                    row_before = dict((getattr(stats_before, "cartography_bodies", {}) or {}).get(body_id) or {})
                before_carto = float(engine.calculate_totals().get("c_cartography") or 0.0)
                before_bonus = float(engine.calculate_totals().get("bonus_discovery") or 0.0)
                engine.analyze_dss_scan_complete_event(ev_work)
                engine.analyze_discovery_meta_event(ev_work)
                after_carto = float(engine.calculate_totals().get("c_cartography") or 0.0)
                after_bonus = float(engine.calculate_totals().get("bonus_discovery") or 0.0)
                if (after_carto > before_carto) or (after_bonus > before_bonus):
                    dss_upgrade_applied += 1
                elif body_id and not row_before:
                    dss_skipped_missing_prior_scan += 1
                recovered_events += 1
                meta_events += 1
                continue

            if event_name in {"SellExplorationData", "MultiSellExplorationData"}:
                if hasattr(engine, "clear_value_domain"):
                    engine.clear_value_domain(domain="cartography")
                    sale_reset_cartography += 1
                recovered_events += 1
                meta_events += 1
                continue

            if event_name == "SellOrganicData":
                if hasattr(engine, "clear_value_domain"):
                    engine.clear_value_domain(domain="exobiology")
                    sale_reset_exobiology += 1
                recovered_events += 1
                meta_events += 1
        except Exception:
            log_event_throttled(
                "exploration.value_recovery.process_event",
                5000,
                "BOOTSTRAP",
                "value recovery failed to process event",
                event=event_name,
            )
            continue

    diagnostics = [
        f"Scan counted: {int(scan_counted)}",
        f"DSS upgrade applied: {int(dss_upgrade_applied)}",
        f"DSS skipped (missing prior Scan): {int(dss_skipped_missing_prior_scan)}",
        f"Sell reset cartography: {int(sale_reset_cartography)}",
        f"Sell reset exobiology: {int(sale_reset_exobiology)}",
    ]

    return {
        "recovered": bool(recovered_events),
        "events": recovered_events,
        "scan_events": scan_events,
        "bio_events": bio_events,
        "meta_events": meta_events,
        "used_system_fallback": used_system_fallback,
        "scan_counted": scan_counted,
        "dss_upgrade_applied": dss_upgrade_applied,
        "dss_skipped_missing_prior_scan": dss_skipped_missing_prior_scan,
        "sale_reset_cartography": sale_reset_cartography,
        "sale_reset_exobiology": sale_reset_exobiology,
        "diagnostics": diagnostics,
        "reason": "ok",
    }


def bootstrap_system_value_from_journal_lines(
    lines: list[str] | tuple[str, ...] | None,
    *,
    max_lines: int = 12000,
) -> Dict[str, Any]:
    return recover_system_value_from_journal_lines(lines, max_lines=max_lines)
