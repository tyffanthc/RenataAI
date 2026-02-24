from __future__ import annotations

from typing import Any, Dict

import config
from app.state import app_state
from logic.events.exploration_awareness import emit_callout_or_summary
from logic.insight_dispatcher import emit_insight
from logic.utils.renata_log import log_event_throttled


DSS_TARGET_HINT_BODIES = set()
DSS_COMPLETED_BODIES = set()
DSS_PROGRESS_MILESTONES_BY_SYSTEM: dict[str, set[int]] = {}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _system_label(ev: Dict[str, Any]) -> str:
    system = _as_text(ev.get("StarSystem")) or _as_text(ev.get("SystemName"))
    if system:
        return system
    return _as_text(getattr(app_state, "current_system", "")) or "unknown"


def _body_label(ev: Dict[str, Any]) -> str:
    return (
        _as_text(ev.get("BodyName"))
        or _as_text(ev.get("Body"))
        or _as_text(ev.get("BodyID"))
        or "unknown"
    )


def _system_key(system_name: str) -> str:
    return _as_text(system_name).lower() or "unknown"


def _body_key(body_name: str) -> str:
    return _as_text(body_name).lower() or "unknown"


def _bool_false(value: Any) -> bool:
    return value is False or value == 0 or str(value).strip().lower() in {"false", "0", "no"}


def _is_first_mapped_confirmed(ev: Dict[str, Any]) -> bool:
    explicit_true = (
        "FirstMapped",
        "first_mapped",
        "IsFirstMapped",
        "is_first_mapped",
    )
    for key in explicit_true:
        if key in ev and bool(ev.get(key)):
            return True

    mapped_state_keys = (
        "WasMapped",
        "was_mapped",
        "AlreadyMapped",
        "already_mapped",
    )
    for key in mapped_state_keys:
        if key in ev and _bool_false(ev.get(key)):
            return True
    return False


def _dss_context(system_name: str, body_name: str, ev: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ctx = {
        "system": system_name,
        "body": body_name,
        "risk_status": "RISK_LOW",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
    }
    event = ev or {}
    for key in ("combat_silence", "in_combat", "combat_state"):
        if key in event:
            ctx[key] = event.get(key)
    return ctx


def _is_high_value_class(planet_class: str, terraform_state: str) -> bool:
    cls = planet_class.lower()
    terra = terraform_state.lower()
    if "earth-like" in cls:
        return True
    if "water world" in cls:
        return True
    if "high metal content" in cls and "terra" in terra:
        return True
    return False


def _estimate_mapped_value_from_carto(ev: Dict[str, Any], gui_ref=None) -> float:
    if gui_ref is None or not hasattr(gui_ref, "carto_df"):
        return 0.0
    carto_df = getattr(gui_ref, "carto_df", None)
    if carto_df is None:
        return 0.0

    planet_class = _as_text(ev.get("PlanetClass")).lower()
    if not planet_class:
        return 0.0

    terraform_state = _as_text(ev.get("TerraformState")).lower()
    try:
        df = carto_df.copy()
        df["Body_Type_norm"] = df["Body_Type"].astype(str).str.lower()
        mask = df["Body_Type_norm"] == planet_class
        if "terra" in terraform_state:
            df["Terraformable_norm"] = df["Terraformable"].astype(str).str.lower()
            mask &= df["Terraformable_norm"] == "yes"
        rows = df[mask]
        if rows.empty:
            return 0.0
        value = float(rows["DSS_Mapped_Value"].max() or 0.0)
        return max(0.0, value)
    except Exception:
        log_event_throttled(
            "dss.estimate_value_from_carto",
            5000,
            "DSS",
            "failed to estimate mapped value from cartography table",
            planet_class=planet_class,
            terraform_state=terraform_state,
        )
        return 0.0


def _is_worth_mapping(ev: Dict[str, Any], gui_ref=None) -> bool:
    if bool(ev.get("WasMapped")):
        return False

    planet_class = _as_text(ev.get("PlanetClass"))
    terraform_state = _as_text(ev.get("TerraformState"))
    if not planet_class:
        return False

    if _is_high_value_class(planet_class, terraform_state):
        return False

    estimated_value = _estimate_mapped_value_from_carto(ev, gui_ref)
    min_value = float(config.get("exploration.dss_helper.min_mapped_value", 600000.0) or 600000.0)
    return estimated_value >= min_value


def _should_emit_progress(count: int) -> bool:
    if count <= 0:
        return False
    if count in {1, 3, 5}:
        return True
    return count > 5 and count % 5 == 0


def reset_dss_helper_state() -> None:
    global DSS_TARGET_HINT_BODIES, DSS_COMPLETED_BODIES, DSS_PROGRESS_MILESTONES_BY_SYSTEM
    DSS_TARGET_HINT_BODIES = set()
    DSS_COMPLETED_BODIES = set()
    DSS_PROGRESS_MILESTONES_BY_SYSTEM = {}


def handle_dss_target_hint(ev: Dict[str, Any], gui_ref=None) -> None:
    """
    Lightweight DSS helper: suggests mapping only when value threshold indicates real ROI.
    """
    if _as_text(ev.get("event")) != "Scan":
        return

    system_name = _system_label(ev)
    body_name = _body_label(ev)
    body_id = (_system_key(system_name), _body_key(body_name))
    if body_id in DSS_TARGET_HINT_BODIES:
        return

    if not _is_worth_mapping(ev, gui_ref):
        return

    raw_text = f"Planeta {body_name} wyglada na warta mapowania DSS."
    emit_callout_or_summary(
        text=raw_text,
        gui_ref=gui_ref,
        message_id="MSG.DSS_TARGET_HINT",
        source="exploration_dss_events",
        system_name=system_name,
        body_name=body_name,
        callout_key=f"dss_target:{body_name}",
        event_type="BODY_DISCOVERED",
        priority="P2_NORMAL",
        context={"raw_text": raw_text, "body": body_name},
    )
    DSS_TARGET_HINT_BODIES.add(body_id)


def handle_dss_scan_complete(ev: Dict[str, Any], gui_ref=None) -> None:
    """
    Event: SAAScanComplete
    - emits one completion callout per body,
    - emits sparse system progress milestones (anti-flood),
    - emits first mapped only when confirmed by payload fields.
    """
    if _as_text(ev.get("event")) != "SAAScanComplete":
        return

    system_name = _system_label(ev)
    body_name = _body_label(ev)
    body_id = (_system_key(system_name), _body_key(body_name))
    if body_id in DSS_COMPLETED_BODIES:
        return

    DSS_COMPLETED_BODIES.add(body_id)
    system_key = body_id[0]
    completed_count = sum(1 for sys_key, _ in DSS_COMPLETED_BODIES if sys_key == system_key)

    probes_used = ev.get("ProbesUsed")
    efficiency_target = ev.get("EfficiencyTarget")
    efficient = False
    try:
        probes_i = int(probes_used)
        target_i = int(efficiency_target)
        efficient = target_i > 0 and probes_i <= target_i
    except Exception:
        log_event_throttled(
            "dss.efficiency_parse",
            5000,
            "DSS",
            "failed to parse DSS efficiency payload",
            probes_used=probes_used,
            efficiency_target=efficiency_target,
            body=body_name,
            system=system_name,
        )
        efficient = False

    completion_text = f"Mapowanie DSS ukonczone: {body_name}."
    if efficient:
        completion_text = f"Mapowanie DSS ukonczone: {body_name}. Bonus efektywnosci zaliczony."

    emit_insight(
        completion_text,
        gui_ref=gui_ref,
        message_id="MSG.DSS_COMPLETED",
        source="exploration_dss_events",
        event_type="BODY_MAPPED",
        context={
            **_dss_context(system_name, body_name, ev),
            "raw_text": completion_text,
        },
        priority="P2_NORMAL",
        dedup_key=f"dss_complete:{system_name}:{body_name}",
        cooldown_scope="entity",
        cooldown_seconds=45.0,
    )

    milestones = DSS_PROGRESS_MILESTONES_BY_SYSTEM.setdefault(system_key, set())
    if _should_emit_progress(completed_count) and completed_count not in milestones:
        milestones.add(completed_count)
        progress_text = (
            "Pierwsze mapowanie DSS w tym systemie zaliczone."
            if completed_count == 1
            else f"Zmapowano DSS {completed_count} cial w tym systemie."
        )
        emit_insight(
            progress_text,
            gui_ref=gui_ref,
            message_id="MSG.DSS_PROGRESS",
            source="exploration_dss_events",
            event_type="BODY_MAPPED",
            context={
                **_dss_context(system_name, body_name, ev),
                "raw_text": progress_text,
            },
            priority="P3_LOW",
            dedup_key=f"dss_progress:{system_name}:{completed_count}",
            cooldown_scope="entity",
            cooldown_seconds=45.0,
        )

    if _is_first_mapped_confirmed(ev):
        first_mapped_text = f"Potwierdzono first mapped dla {body_name}."
        emit_insight(
            first_mapped_text,
            gui_ref=gui_ref,
            message_id="MSG.FIRST_MAPPED",
            source="exploration_dss_events",
            event_type="BODY_MAPPED",
            context={
                **_dss_context(system_name, body_name, ev),
                "first_status_kind": "confirmed",
                "raw_text": first_mapped_text,
            },
            priority="P2_NORMAL",
            dedup_key=f"first_mapped:{body_name}",
            cooldown_scope="entity",
            cooldown_seconds=120.0,
        )
