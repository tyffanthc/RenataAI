from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

import config
from app.state import app_state
from logic.cargo_value_estimator import estimate_cargo_value
from logic.insight_dispatcher import emit_insight


@dataclass
class CombatAwarenessPayload:
    system: str
    mode: str
    level: str
    pattern_id: str
    pattern_count: int
    in_combat: bool
    hull_percent: float | None
    shields_up: bool | None
    under_attack: bool
    being_interdicted: bool
    fsd_cooldown_sec: float | None
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
    cargo_floor_cr: float = 0.0
    cargo_expected_cr: float = 0.0
    cargo_value_confidence: str = "LOW"
    cargo_value_source: str = "fallback"


_RUNTIME: Dict[str, Any] = {
    "system": "",
    "hull_percent": None,
    "shields_up": None,
    "in_combat": False,
    "under_attack": False,
    "being_interdicted": False,
    "fsd_cooldown_sec": None,
    "active_patterns": set(),
    "pattern_hits": {},
    "emitted_patterns": set(),
}

_PATTERN_THRESHOLDS: Dict[str, int] = {
    "combat_hull_critical": 1,
    "combat_shields_down_exposed": 2,
    "combat_escape_window_unstable": 2,
    "combat_high_stake_exposure": 2,
}

_PATTERN_LEVELS: Dict[str, str] = {
    "combat_hull_critical": "critical",
    "combat_shields_down_exposed": "high",
    "combat_escape_window_unstable": "high",
    "combat_high_stake_exposure": "high",
}


def reset_combat_awareness_state() -> None:
    _RUNTIME["system"] = ""
    _RUNTIME["hull_percent"] = None
    _RUNTIME["shields_up"] = None
    _RUNTIME["in_combat"] = False
    _RUNTIME["under_attack"] = False
    _RUNTIME["being_interdicted"] = False
    _RUNTIME["fsd_cooldown_sec"] = None
    _RUNTIME["active_patterns"] = set()
    _RUNTIME["pattern_hits"] = {}
    _RUNTIME["emitted_patterns"] = set()
    app_state.last_combat_awareness_signature = None


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


def _status_under_attack(status: Dict[str, Any]) -> bool:
    if bool(status.get("UnderAttack")) or bool(status.get("InDanger")):
        return True
    flags_val = _safe_float(status.get("Flags"))
    if flags_val is None:
        return False
    try:
        flags = int(flags_val)
    except Exception:
        return False
    return bool(flags & (1 << 22))


def _status_being_interdicted(status: Dict[str, Any]) -> bool:
    if bool(status.get("BeingInterdicted")):
        return True
    flags_val = _safe_float(status.get("Flags"))
    if flags_val is None:
        return False
    try:
        flags = int(flags_val)
    except Exception:
        return False
    return bool(flags & (1 << 23))


def _status_in_combat(status: Dict[str, Any]) -> bool:
    if bool(status.get("InCombat")):
        return True
    if _status_under_attack(status):
        return True
    if _status_being_interdicted(status):
        return True
    state = _as_text(status.get("CombatState")).lower()
    return state in {"combat", "active", "engaged", "under_fire"}


def _status_fsd_cooldown(status: Dict[str, Any]) -> float | None:
    for key in ("FSDCooldown", "FsdCooldown", "FsdJumpCooldown", "JumpCooldown"):
        value = _safe_float(status.get(key))
        if value is not None:
            return max(0.0, value)
    return None


def _value_snapshot() -> tuple[float, float, float, float, float, float, float, str, str]:
    session_value = 0.0
    system_value = 0.0
    cargo_tons = 0.0
    exploration_value = 0.0
    exobio_value = 0.0
    cargo_floor_cr = 0.0
    cargo_expected_cr = 0.0
    cargo_value_confidence = "LOW"
    cargo_value_source = "fallback"

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

    try:
        cargo_estimate = estimate_cargo_value(cargo_tons=cargo_tons)
        cargo_tons = max(cargo_tons, float(cargo_estimate.cargo_tons))
        cargo_floor_cr = float(cargo_estimate.cargo_floor_cr)
        cargo_expected_cr = float(cargo_estimate.cargo_expected_cr)
        cargo_value_confidence = str(cargo_estimate.confidence or "LOW").upper()
        cargo_value_source = str(cargo_estimate.source or "fallback").lower()
    except Exception:
        cargo_floor_cr = 0.0
        cargo_expected_cr = 0.0
        cargo_value_confidence = "LOW"
        cargo_value_source = "fallback"

    return (
        max(0.0, session_value),
        max(0.0, system_value),
        max(0.0, cargo_tons),
        max(0.0, exploration_value),
        max(0.0, exobio_value),
        max(0.0, cargo_floor_cr),
        max(0.0, cargo_expected_cr),
        cargo_value_confidence,
        cargo_value_source,
    )


def _var_status(session_value: float, system_value: float, cargo_floor_cr: float) -> str:
    reference = max(session_value, system_value, cargo_floor_cr)
    if reference >= 20_000_000:
        return "VAR_HIGH"
    if reference >= 5_000_000:
        return "VAR_MEDIUM"
    if reference > 0:
        return "VAR_LOW"
    return "VAR_NEGLIGIBLE"


def _active_patterns(var_status: str) -> set[str]:
    if not bool(_RUNTIME.get("in_combat")):
        return set()

    hull = _clamp_percent(_safe_float(_RUNTIME.get("hull_percent")))
    shields_up = _RUNTIME.get("shields_up")
    under_attack = bool(_RUNTIME.get("under_attack"))
    being_interdicted = bool(_RUNTIME.get("being_interdicted"))
    fsd_cd = _safe_float(_RUNTIME.get("fsd_cooldown_sec"))
    escape_unstable = bool((under_attack or being_interdicted) and fsd_cd is not None and fsd_cd > 0.0)

    active: set[str] = set()
    if hull is not None and hull <= 20.0:
        active.add("combat_hull_critical")
    if shields_up is False and (hull is None or hull <= 60.0):
        active.add("combat_shields_down_exposed")
    if escape_unstable:
        active.add("combat_escape_window_unstable")
    if var_status in {"VAR_HIGH", "VAR_MEDIUM"} and (
        (hull is not None and hull <= 45.0) or shields_up is False
    ):
        active.add("combat_high_stake_exposure")
    return active


def _record_pattern_hits(active_patterns: set[str]) -> None:
    previous = set(_RUNTIME.get("active_patterns") or set())
    entered = active_patterns - previous
    hits: dict[str, int] = dict(_RUNTIME.get("pattern_hits") or {})
    for pattern_id in entered:
        hits[pattern_id] = int(hits.get(pattern_id, 0)) + 1
    _RUNTIME["pattern_hits"] = hits
    _RUNTIME["active_patterns"] = set(active_patterns)


def _build_payload(mode: str) -> CombatAwarenessPayload | None:
    system = _as_text(_RUNTIME.get("system")) or _as_text(getattr(app_state, "current_system", "")) or "unknown"
    in_combat = bool(_RUNTIME.get("in_combat"))
    if not in_combat:
        return None

    (
        session_value,
        system_value,
        cargo_tons,
        exploration_value,
        exobio_value,
        cargo_floor_cr,
        cargo_expected_cr,
        cargo_value_confidence,
        cargo_value_source,
    ) = _value_snapshot()
    var_status = _var_status(session_value, system_value, cargo_floor_cr)
    active = _active_patterns(var_status)
    _record_pattern_hits(active)
    if not active:
        return None

    hits: dict[str, int] = dict(_RUNTIME.get("pattern_hits") or {})
    candidates: list[tuple[int, int, str, str]] = []
    for pattern_id in active:
        count = int(hits.get(pattern_id, 0))
        threshold = int(_PATTERN_THRESHOLDS.get(pattern_id, 2))
        if count < threshold:
            continue
        level = str(_PATTERN_LEVELS.get(pattern_id, "high"))
        rank = 0 if level == "critical" else 1
        candidates.append((rank, -count, pattern_id, level))

    if not candidates:
        return None

    candidates.sort()
    _rank, _neg_count, pattern_id, level = candidates[0]
    pattern_count = int(hits.get(pattern_id, 0))
    risk_status = "RISK_CRITICAL" if level == "critical" else "RISK_HIGH"
    hull = _clamp_percent(_safe_float(_RUNTIME.get("hull_percent")))
    shields_up = _RUNTIME.get("shields_up")
    if shields_up is not None:
        shields_up = bool(shields_up)
    fsd_cd = _safe_float(_RUNTIME.get("fsd_cooldown_sec"))
    under_attack = bool(_RUNTIME.get("under_attack"))
    being_interdicted = bool(_RUNTIME.get("being_interdicted"))

    options = [
        "Rozważ przerwanie eskalacji i odzyskanie kontroli sytuacji.",
        "Rozważ oddzielenie się od zagrożenia i zabezpieczenie postępu.",
        "Jeśli chcesz, sprawdź panel ryzyka i konsekwencji.",
    ]
    note = "Renata sygnalizuje wzorzec ryzyka; decyzja pozostaje po stronie pilota."

    hull_bucket = "na" if hull is None else str(int(hull // 5))
    count_bucket = str(min(pattern_count, 9))
    signature = f"{system}:{level}:{pattern_id}:{count_bucket}:{hull_bucket}:{var_status}"

    return CombatAwarenessPayload(
        system=system,
        mode=_as_text(mode).lower() or "auto",
        level=level,
        pattern_id=pattern_id,
        pattern_count=pattern_count,
        in_combat=in_combat,
        hull_percent=hull,
        shields_up=shields_up,
        under_attack=under_attack,
        being_interdicted=being_interdicted,
        fsd_cooldown_sec=fsd_cd,
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
        cargo_floor_cr=cargo_floor_cr,
        cargo_expected_cr=cargo_expected_cr,
        cargo_value_confidence=cargo_value_confidence,
        cargo_value_source=cargo_value_source,
    )


def _tts_line(payload: CombatAwarenessPayload) -> str:
    if payload.pattern_id == "combat_hull_critical":
        return "Wzorzec ryzyka. Kadlub jest krytyczny i stawka jest wysoka."
    if payload.pattern_id == "combat_shields_down_exposed":
        return "Wzorzec ryzyka. Osłony są poza walką ochronną przy aktywnym zagrożeniu."
    if payload.pattern_id == "combat_escape_window_unstable":
        return "Wzorzec ryzyka. Okno bezpiecznego wyjscia jest niestabilne."
    if payload.pattern_id == "combat_high_stake_exposure":
        return "Wzorzec ryzyka. Wysoka stawka i walka przestaja byc proporcjonalne."
    return "Wzorzec ryzyka bojowego jest aktywny."


def trigger_combat_awareness(*, gui_ref=None, mode: str = "auto") -> bool:
    if not bool(config.get("combat_awareness_enabled", True)):
        return False

    payload = _build_payload(mode)
    if payload is None:
        app_state.last_combat_awareness_signature = None
        return False

    mode_norm = _as_text(mode).lower() or "auto"
    emitted_patterns = set(_RUNTIME.get("emitted_patterns") or set())
    if mode_norm == "auto":
        if payload.pattern_id in emitted_patterns:
            return False
        last_sig = _as_text(getattr(app_state, "last_combat_awareness_signature", ""))
        if last_sig and last_sig == payload.signature:
            return False

    is_critical = payload.level == "critical"
    message_id = "MSG.COMBAT_AWARENESS_CRITICAL" if is_critical else "MSG.COMBAT_AWARENESS_HIGH"
    priority = "P0_CRITICAL" if is_critical else "P1_HIGH"
    cooldown_seconds = 0.0 if mode_norm == "manual" else (90.0 if is_critical else 75.0)
    dedup_prefix = "combat_awareness_critical" if is_critical else "combat_awareness_high"
    dedup_key = f"{dedup_prefix}:{payload.system}:{payload.pattern_id}:{payload.signature}"

    context = {
        "system": payload.system,
        "raw_text": _tts_line(payload),
        "risk_status": payload.risk_status,
        "var_status": payload.var_status,
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
        "in_combat": payload.in_combat,
        "combat_state": "active" if payload.in_combat else "idle",
        "combat_payload": asdict(payload),
    }

    emit_insight(
        context["raw_text"],
        gui_ref=gui_ref,
        message_id=message_id,
        source="combat_awareness",
        event_type="COMBAT_RISK_PATTERN",
        context=context,
        priority=priority,
        dedup_key=dedup_key,
        cooldown_scope="entity",
        cooldown_seconds=cooldown_seconds,
        combat_silence_sensitive=True,
    )

    if mode_norm == "auto":
        app_state.last_combat_awareness_signature = payload.signature
        emitted_patterns.add(payload.pattern_id)
        _RUNTIME["emitted_patterns"] = emitted_patterns
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

    _RUNTIME["under_attack"] = _status_under_attack(status)
    _RUNTIME["being_interdicted"] = _status_being_interdicted(status)
    _RUNTIME["in_combat"] = _status_in_combat(status)

    fsd_cd = _status_fsd_cooldown(status)
    if fsd_cd is not None:
        _RUNTIME["fsd_cooldown_sec"] = fsd_cd

    if not _RUNTIME["in_combat"]:
        _RUNTIME["active_patterns"] = set()

    trigger_combat_awareness(gui_ref=gui_ref, mode="auto")


def handle_journal_event(ev: Dict[str, Any], gui_ref=None) -> None:
    if not isinstance(ev, dict):
        return

    system = _as_text(ev.get("StarSystem") or ev.get("SystemName") or ev.get("StarSystemName"))
    if system:
        _RUNTIME["system"] = system

    event_name = _as_text(ev.get("event"))
    if event_name in {"LoadGame", "Resurrect"}:
        _RUNTIME["active_patterns"] = set()
        _RUNTIME["pattern_hits"] = {}
        _RUNTIME["emitted_patterns"] = set()
        app_state.last_combat_awareness_signature = None
    elif event_name in {"Died", "Docked", "Undocked"}:
        _RUNTIME["active_patterns"] = set()
        _RUNTIME["pattern_hits"] = {}
        _RUNTIME["emitted_patterns"] = set()
        app_state.last_combat_awareness_signature = None
