from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

import config
from app.state import app_state
from logic.insight_dispatcher import emit_insight


@dataclass
class SurvivalRebuyPayload:
    system: str
    mode: str
    level: str
    reason: str
    credits: float | None
    rebuy_cost: float | None
    rebuy_ratio: float | None
    hull_percent: float | None
    shields_up: bool | None
    in_combat: bool
    var_status: str
    risk_status: str
    session_value_estimated: float
    system_value_estimated: float
    cargo_tons: float
    options: list[str]
    note: str
    signature: str
    exploration_value_estimated: float = 0.0
    exobio_value_estimated: float = 0.0


_RUNTIME: Dict[str, Any] = {
    "system": "",
    "credits": None,
    "rebuy_cost": None,
    "hull_percent": None,
    "shields_up": None,
    "in_combat": False,
}


def reset_survival_rebuy_state() -> None:
    _RUNTIME["system"] = ""
    _RUNTIME["credits"] = None
    _RUNTIME["rebuy_cost"] = None
    _RUNTIME["hull_percent"] = None
    _RUNTIME["shields_up"] = None
    _RUNTIME["in_combat"] = False
    app_state.last_survival_rebuy_signature = None


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _clamp_percent(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, float(value)))


def _status_hull_percent(status: Dict[str, Any]) -> float | None:
    for key in ("Hull", "HullHealth", "HullPercent"):
        raw = _safe_float(status.get(key))
        if raw is not None:
            return _clamp_percent(raw)
    return None


def _status_shields_up(status: Dict[str, Any]) -> bool | None:
    if "ShieldsUp" in status:
        return bool(status.get("ShieldsUp"))
    flags = _safe_float(status.get("Flags"))
    if flags is None:
        return None
    try:
        return bool(int(flags) & (1 << 3))
    except Exception:
        return None


def _status_in_combat(status: Dict[str, Any]) -> bool:
    if bool(status.get("InDanger")) or bool(status.get("UnderAttack")):
        return True
    if bool(status.get("BeingInterdicted")):
        return True
    flags_val = _safe_float(status.get("Flags"))
    if flags_val is None:
        return False
    try:
        flags = int(flags_val)
    except Exception:
        return False
    in_danger = bool(flags & (1 << 22))
    interdicted = bool(flags & (1 << 23))
    return in_danger or interdicted


def _extract_credits(payload: Dict[str, Any]) -> float | None:
    for key in ("Credits", "CreditBalance", "Balance", "Bank"):
        value = _safe_float(payload.get(key))
        if value is not None and value >= 0.0:
            return value
    return None


def _extract_rebuy_cost(payload: Dict[str, Any]) -> float | None:
    candidates = (
        "Rebuy",
        "RebuyCost",
        "rebuyCost",
        "Insurance",
        "InsuranceCost",
        "CostToRebuy",
    )
    for key in candidates:
        value = _safe_float(payload.get(key))
        if value is not None and value >= 0.0:
            return value

    insurance = payload.get("Insurance")
    if isinstance(insurance, dict):
        for key in ("Rebuy", "RebuyCost", "Cost"):
            value = _safe_float(insurance.get(key))
            if value is not None and value >= 0.0:
                return value
    return None


def _value_snapshot() -> tuple[float, float, float, float, float]:
    session_value = 0.0
    system_value = 0.0
    cargo_tons = 0.0
    exploration_value = 0.0
    exobio_value = 0.0

    try:
        totals = app_state.system_value_engine.calculate_totals()
        totals = totals or {}
        session_value = float(totals.get("total") or 0.0)
        cartography_value = float(totals.get("c_cartography") or 0.0)
        exobio_value = float(totals.get("c_exobiology") or 0.0)
        discovery_bonus = float(totals.get("bonus_discovery") or 0.0)
        exploration_value = max(0.0, cartography_value + discovery_bonus)
    except Exception:
        session_value = 0.0
        exploration_value = 0.0
        exobio_value = 0.0

    try:
        system = _as_text(_RUNTIME.get("system")) or _as_text(getattr(app_state, "current_system", ""))
        if system:
            data = app_state.exit_summary.build_summary_data(system_name=system)
            if data is not None:
                system_value = float(getattr(data, "total_value", 0.0) or 0.0)
    except Exception:
        system_value = 0.0

    try:
        cargo_tons = float(getattr(app_state.ship_state, "cargo_mass_t", 0.0) or 0.0)
    except Exception:
        cargo_tons = 0.0

    return (
        max(0.0, session_value),
        max(0.0, system_value),
        max(0.0, cargo_tons),
        max(0.0, exploration_value),
        max(0.0, exobio_value),
    )


def _var_status(session_value: float, system_value: float, cargo_tons: float) -> str:
    reference = max(session_value, system_value)
    if reference >= 20_000_000 or cargo_tons >= 120:
        return "VAR_HIGH"
    if reference >= 5_000_000 or cargo_tons >= 30:
        return "VAR_MEDIUM"
    if reference > 0 or cargo_tons > 0:
        return "VAR_LOW"
    return "VAR_NEGLIGIBLE"


def _build_payload(mode: str) -> SurvivalRebuyPayload | None:
    system = _as_text(_RUNTIME.get("system")) or _as_text(getattr(app_state, "current_system", "")) or "unknown"
    credits = _safe_float(_RUNTIME.get("credits"))
    rebuy_cost = _safe_float(_RUNTIME.get("rebuy_cost"))
    hull_percent = _clamp_percent(_safe_float(_RUNTIME.get("hull_percent")))
    shields_up = _RUNTIME.get("shields_up")
    if shields_up is not None:
        shields_up = bool(shields_up)
    in_combat = bool(_RUNTIME.get("in_combat"))

    session_value, system_value, cargo_tons, exploration_value, exobio_value = _value_snapshot()
    var_status = _var_status(session_value, system_value, cargo_tons)

    rebuy_ratio = None
    if credits is not None and rebuy_cost is not None and rebuy_cost > 0.0:
        rebuy_ratio = credits / rebuy_cost

    no_rebuy = bool(credits is not None and rebuy_cost is not None and rebuy_cost > 0.0 and credits < rebuy_cost)
    rebuy_borderline = bool(
        not no_rebuy
        and credits is not None
        and rebuy_cost is not None
        and rebuy_cost > 0.0
        and credits < (rebuy_cost * 1.2)
    )
    hull_critical = bool(hull_percent is not None and hull_percent <= 12.0)
    hull_high = bool(hull_percent is not None and hull_percent <= 25.0)
    high_var = var_status in {"VAR_HIGH", "VAR_MEDIUM"}

    level = "none"
    reason = "none"
    risk_status = "RISK_LOW"
    options = [
        "Rozwaz wycofanie i zabezpieczenie danych.",
        "Rozwaz szybki cash-in przy bezpiecznej stacji.",
        "Kontynuuj swiadomie i monitoruj kadlub oraz ryzyko.",
    ]
    note = "Renata sygnalizuje konsekwencje, ale decyzja pozostaje po stronie pilota."

    if no_rebuy:
        level = "critical"
        reason = "no_rebuy"
        risk_status = "RISK_CRITICAL"
    elif in_combat and hull_critical:
        level = "critical"
        reason = "combat_hull_critical"
        risk_status = "RISK_CRITICAL"
    elif rebuy_borderline and (in_combat or high_var):
        level = "high"
        reason = "rebuy_borderline"
        risk_status = "RISK_HIGH"
    elif in_combat and hull_high and high_var:
        level = "high"
        reason = "combat_hull_high_var"
        risk_status = "RISK_HIGH"
    elif in_combat and var_status == "VAR_HIGH":
        level = "high"
        reason = "combat_var_high"
        risk_status = "RISK_HIGH"
    elif hull_critical and high_var:
        level = "high"
        reason = "hull_critical_with_var"
        risk_status = "RISK_HIGH"

    if level == "none":
        return None

    hull_bucket = "na" if hull_percent is None else str(int(hull_percent // 5))
    var_bucket = "H" if var_status == "VAR_HIGH" else "M" if var_status == "VAR_MEDIUM" else "L"
    value_bucket = str(int(max(session_value, system_value) // 1_000_000))
    rebuy_bucket = "na"
    if rebuy_ratio is not None:
        rebuy_bucket = f"{int(rebuy_ratio * 100):03d}"
    signature = (
        f"{system}:{level}:{reason}:{hull_bucket}:{int(in_combat)}:"
        f"{var_bucket}:{value_bucket}:{rebuy_bucket}"
    )

    return SurvivalRebuyPayload(
        system=system,
        mode=_as_text(mode).lower() or "auto",
        level=level,
        reason=reason,
        credits=credits,
        rebuy_cost=rebuy_cost,
        rebuy_ratio=rebuy_ratio,
        hull_percent=hull_percent,
        shields_up=shields_up,
        in_combat=in_combat,
        var_status=var_status,
        risk_status=risk_status,
        session_value_estimated=session_value,
        system_value_estimated=system_value,
        cargo_tons=cargo_tons,
        options=options,
        note=note,
        signature=signature,
        exploration_value_estimated=exploration_value,
        exobio_value_estimated=exobio_value,
    )


def _tts_line(payload: SurvivalRebuyPayload) -> str:
    if payload.reason == "no_rebuy":
        return (
            "Brak rebuy. Jedna strata oznacza utrate statku i postepu. "
            "Rozwaz wycofanie i zabezpieczenie danych."
        )
    if payload.reason == "combat_hull_critical":
        return (
            "Kadlub jest krytyczny w warunkach walki. "
            "Rozwaz wycofanie i bezpieczny cash-in."
        )
    if payload.reason == "rebuy_borderline":
        return (
            "Rebuy jest na granicy. Jedna strata moze mocno cofnac progres. "
            "Rozwaz bezpieczny cash-in."
        )
    if payload.reason == "combat_hull_high_var":
        return (
            "Ryzyko jest wysokie wzgledem danych lub ladunku. "
            "Rozwaz wycofanie i domkniecie zysku."
        )
    return "Ryzyko przetrwania wzroslo. Sprawdz opcje zabezpieczenia postepu."


def trigger_survival_rebuy_awareness(*, gui_ref=None, mode: str = "auto") -> bool:
    if not bool(config.get("survival_rebuy_awareness_enabled", True)):
        return False

    payload = _build_payload(mode)
    if payload is None:
        app_state.last_survival_rebuy_signature = None
        return False

    mode_norm = _as_text(mode).lower() or "auto"
    if mode_norm == "auto":
        last_sig = _as_text(getattr(app_state, "last_survival_rebuy_signature", ""))
        if last_sig and last_sig == payload.signature:
            return False
        app_state.last_survival_rebuy_signature = payload.signature

    is_critical = payload.level == "critical"
    message_id = "MSG.SURVIVAL_REBUY_CRITICAL" if is_critical else "MSG.SURVIVAL_REBUY_HIGH"
    priority = "P0_CRITICAL" if is_critical else "P1_HIGH"
    cooldown_seconds = 0.0 if mode_norm == "manual" else (180.0 if is_critical else 120.0)
    dedup_prefix = "survival_critical" if is_critical else "survival_high"
    dedup_key = (
        f"{dedup_prefix}_manual:{payload.system}:{payload.signature}"
        if mode_norm == "manual"
        else f"{dedup_prefix}_auto:{payload.system}:{payload.signature}"
    )

    context = {
        "system": payload.system,
        "raw_text": _tts_line(payload),
        "risk_status": payload.risk_status,
        "var_status": payload.var_status,
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
        "in_combat": payload.in_combat,
        "combat_state": "active" if payload.in_combat else "idle",
        "survival_payload": asdict(payload),
    }

    emit_insight(
        context["raw_text"],
        gui_ref=gui_ref,
        message_id=message_id,
        source="survival_rebuy_awareness",
        event_type="SURVIVAL_RISK_CHANGED",
        context=context,
        priority=priority,
        dedup_key=dedup_key,
        cooldown_scope="entity",
        cooldown_seconds=cooldown_seconds,
    )
    return True


def handle_status_update(status: Dict[str, Any], gui_ref=None) -> None:
    if not isinstance(status, dict):
        return

    system = _as_text(status.get("StarSystem") or status.get("SystemName"))
    if system:
        _RUNTIME["system"] = system

    hull = _status_hull_percent(status)
    if hull is not None:
        _RUNTIME["hull_percent"] = hull

    shields = _status_shields_up(status)
    if shields is not None:
        _RUNTIME["shields_up"] = shields

    _RUNTIME["in_combat"] = _status_in_combat(status)

    credits = _extract_credits(status)
    if credits is not None:
        _RUNTIME["credits"] = credits

    rebuy = _extract_rebuy_cost(status)
    if rebuy is not None:
        _RUNTIME["rebuy_cost"] = rebuy

    trigger_survival_rebuy_awareness(gui_ref=gui_ref, mode="auto")


def handle_journal_event(ev: Dict[str, Any], gui_ref=None) -> None:
    if not isinstance(ev, dict):
        return

    changed = False
    system = _as_text(ev.get("StarSystem") or ev.get("SystemName") or ev.get("StarSystemName"))
    if system and system != _RUNTIME.get("system"):
        _RUNTIME["system"] = system
        changed = True

    credits = _extract_credits(ev)
    if credits is not None and credits != _RUNTIME.get("credits"):
        _RUNTIME["credits"] = credits
        changed = True

    rebuy = _extract_rebuy_cost(ev)
    if rebuy is not None and rebuy != _RUNTIME.get("rebuy_cost"):
        _RUNTIME["rebuy_cost"] = rebuy
        changed = True

    event_name = _as_text(ev.get("event"))
    if event_name in {"LoadGame", "Resurrect", "ShipDestroyed", "Died"}:
        changed = True

    if changed:
        trigger_survival_rebuy_awareness(gui_ref=gui_ref, mode="auto")
