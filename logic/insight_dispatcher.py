from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable, Optional

import config
from logic.event_insight_mapping import resolve_emit_contract
from logic.utils import notify as _notify
from logic.utils.renata_log import log_event, log_event_throttled


_PRIORITY_ORDER = {
    "P0_CRITICAL": 0,
    "P1_HIGH": 1,
    "P2_NORMAL": 2,
    "P3_LOW": 3,
}

_DEFAULT_COOLDOWN_BY_PRIORITY = {
    "P0_CRITICAL": 0.0,
    "P1_HIGH": 4.0,
    "P2_NORMAL": 8.0,
    "P3_LOW": 15.0,
}

_CROSS_MODULE_GROUP_BY_MESSAGE = {
    "MSG.EXPLORATION_SYSTEM_SUMMARY": "F4_VOICE",
    "MSG.CASH_IN_ASSISTANT": "F4_VOICE",
    "MSG.SURVIVAL_REBUY_HIGH": "F4_VOICE",
    "MSG.SURVIVAL_REBUY_CRITICAL": "F4_VOICE",
}

_CROSS_MODULE_DEFAULT_WINDOW_SEC = {
    "F4_VOICE": 12.0,
}

_CROSS_MODULE_RUNTIME: dict[str, dict[str, object]] = {}

_MODULE_CLASS_BY_MESSAGE = {
    # Navigation
    "MSG.NEXT_HOP": "NAVIGATION",
    "MSG.JUMPED_SYSTEM": "NAVIGATION",
    "MSG.NEXT_HOP_COPIED": "NAVIGATION",
    "MSG.DOCKED": "NAVIGATION",
    "MSG.UNDOCKED": "NAVIGATION",
    # Exploration (FSS/DSS/Exobio/awareness)
    "MSG.FSS_PROGRESS_25": "EXPLORATION",
    "MSG.FSS_PROGRESS_50": "EXPLORATION",
    "MSG.FSS_PROGRESS_75": "EXPLORATION",
    "MSG.FSS_LAST_BODY": "EXPLORATION",
    "MSG.SYSTEM_FULLY_SCANNED": "EXPLORATION",
    "MSG.FIRST_DISCOVERY": "EXPLORATION",
    "MSG.FIRST_DISCOVERY_OPPORTUNITY": "EXPLORATION",
    "MSG.BODY_NO_PREV_DISCOVERY": "EXPLORATION",
    "MSG.ELW_DETECTED": "EXPLORATION",
    "MSG.WW_DETECTED": "EXPLORATION",
    "MSG.TERRAFORMABLE_DETECTED": "EXPLORATION",
    "MSG.BIO_SIGNALS_HIGH": "EXPLORATION",
    "MSG.DSS_TARGET_HINT": "EXPLORATION",
    "MSG.DSS_COMPLETED": "EXPLORATION",
    "MSG.DSS_PROGRESS": "EXPLORATION",
    "MSG.FIRST_MAPPED": "EXPLORATION",
    "MSG.EXOBIO_SAMPLE_LOGGED": "EXPLORATION",
    "MSG.EXOBIO_RANGE_READY": "EXPLORATION",
    "MSG.EXOBIO_NEW_ENTRY": "EXPLORATION",
    "MSG.FOOTFALL": "EXPLORATION",
    "MSG.EXPLORATION_AWARENESS_SUMMARY": "EXPLORATION",
    # F4
    "MSG.EXPLORATION_SYSTEM_SUMMARY": "F4",
    "MSG.CASH_IN_ASSISTANT": "F4",
    "MSG.SURVIVAL_REBUY_HIGH": "F4",
    "MSG.SURVIVAL_REBUY_CRITICAL": "F4",
    # F5 combat
    "MSG.COMBAT_AWARENESS_HIGH": "COMBAT",
    "MSG.COMBAT_AWARENESS_CRITICAL": "COMBAT",
    "MSG.FUEL_CRITICAL": "COMBAT",
}

_MODULE_CLASS_RANK = {
    "COMBAT": 0,
    "F4": 1,
    "EXPLORATION": 2,
    "NAVIGATION": 3,
    "GENERAL": 4,
}

_MODULE_CLASS_COOLDOWN_DEFAULT_SEC = {
    "COMBAT": 0.0,
    "F4": 0.0,
    "EXPLORATION": 0.0,
    "NAVIGATION": 0.0,
    "GENERAL": 0.0,
}

_PRIORITY_ESCALATION_ORDER = {
    "P3_LOW": 3,
    "P2_NORMAL": 2,
    "P1_HIGH": 1,
    "P0_CRITICAL": 0,
}

_PRIORITY_ESCALATION_NEXT = {
    "P3_LOW": "P2_NORMAL",
    "P2_NORMAL": "P1_HIGH",
    "P1_HIGH": "P0_CRITICAL",
}

_PRIORITY_MATRIX_RUNTIME: dict[str, object] = {}
_PRIORITY_ESCALATION_RUNTIME: dict[str, dict[str, object]] = {}


@dataclass(frozen=True)
class Insight:
    text: str
    message_id: str
    source: str
    context: dict | None = None
    priority: str = "P2_NORMAL"
    dedup_key: str | None = None
    cooldown_scope: str = "message"  # global | action | message | entity
    cooldown_seconds: float | None = None
    combat_silence_sensitive: bool = True
    force_tts: bool = False


@dataclass(frozen=True)
class GateDecision:
    allow_emit: bool
    risk_status: str
    var_status: str
    trust_status: str
    confidence_score: float
    confidence_label: str
    reason: str


def _priority_rank(priority: str) -> int:
    return _PRIORITY_ORDER.get(str(priority or "").strip().upper(), 999)


def _default_cooldown(priority: str) -> float:
    norm = str(priority or "").strip().upper()
    return float(_DEFAULT_COOLDOWN_BY_PRIORITY.get(norm, _DEFAULT_COOLDOWN_BY_PRIORITY["P2_NORMAL"]))


def _cross_module_group(message_id: str) -> str | None:
    return _CROSS_MODULE_GROUP_BY_MESSAGE.get(str(message_id or "").strip())


def _cross_module_window_sec(group_id: str) -> float:
    key = ""
    if group_id == "F4_VOICE":
        key = "dispatcher.f4_voice_priority_window_sec"
    fallback = float(_CROSS_MODULE_DEFAULT_WINDOW_SEC.get(group_id, 10.0))
    if not key:
        return fallback
    try:
        return max(0.0, float(config.get(key, fallback)))
    except Exception:
        return fallback


def _priority_matrix_window_sec() -> float:
    fallback = 10.0
    try:
        return max(0.0, float(config.get("dispatcher.priority_matrix_window_sec", fallback)))
    except Exception:
        return fallback


def _priority_escalation_window_sec() -> float:
    fallback = 20.0
    try:
        return max(0.0, float(config.get("dispatcher.priority_escalation_window_sec", fallback)))
    except Exception:
        return fallback


def _priority_escalation_enabled() -> bool:
    try:
        return bool(config.get("dispatcher.priority_escalation_enabled", True))
    except Exception:
        return True


def _module_class_cooldown_sec(module_class: str) -> float:
    norm = str(module_class or "GENERAL").strip().upper() or "GENERAL"
    setting_key = f"dispatcher.class_cooldown.{norm.lower()}"
    fallback = float(_MODULE_CLASS_COOLDOWN_DEFAULT_SEC.get(norm, 0.0))
    try:
        return max(0.0, float(config.get(setting_key, fallback)))
    except Exception:
        return fallback


def reset_dispatcher_runtime_state() -> None:
    _CROSS_MODULE_RUNTIME.clear()
    _PRIORITY_MATRIX_RUNTIME.clear()
    _PRIORITY_ESCALATION_RUNTIME.clear()


def _normalize_risk(value: object) -> str:
    text = str(value or "").strip().lower()
    if "critical" in text:
        return "RISK_CRITICAL"
    if "high" in text:
        return "RISK_HIGH"
    if "med" in text:
        return "RISK_MEDIUM"
    if "low" in text:
        return "RISK_LOW"
    return "RISK_UNKNOWN"


def _normalize_var(value: object) -> str:
    text = str(value or "").strip().lower()
    if "critical" in text:
        return "VAR_CRITICAL"
    if "high" in text:
        return "VAR_HIGH"
    if "med" in text:
        return "VAR_MEDIUM"
    if "low" in text:
        return "VAR_LOW"
    if "neg" in text or "none" in text:
        return "VAR_NEGLIGIBLE"
    return "VAR_UNKNOWN"


def _normalize_trust(value: object) -> str:
    text = str(value or "").strip().lower()
    if "high" in text:
        return "TRUST_HIGH"
    if "med" in text:
        return "TRUST_MEDIUM"
    if "low" in text:
        return "TRUST_LOW"
    return "TRUST_UNKNOWN"


def _normalize_confidence(value: object) -> tuple[float, str]:
    if value is None:
        return 0.5, "mid"
    if isinstance(value, (int, float)):
        score = max(0.0, min(1.0, float(value)))
    else:
        text = str(value).strip().lower()
        if text in {"critical", "high", "strong", "certain"}:
            score = 0.9
        elif text in {"medium", "mid", "normal"}:
            score = 0.6
        elif text in {"low", "weak", "uncertain", "maybe"}:
            score = 0.25
        else:
            try:
                score = max(0.0, min(1.0, float(text)))
            except Exception:
                score = 0.5
    if score >= 0.8:
        return score, "high"
    if score >= 0.5:
        return score, "mid"
    return score, "low"


def _gate_context_snapshot(context: dict | None) -> tuple[str, str, str, float, str]:
    ctx = context or {}
    risk_status = _normalize_risk(ctx.get("risk_status") or ctx.get("risk_level") or ctx.get("risk"))
    var_status = _normalize_var(ctx.get("var_status") or ctx.get("var_tier") or ctx.get("value_at_risk"))
    trust_status = _normalize_trust(ctx.get("trust_status") or ctx.get("trust"))
    confidence_score, confidence_label = _normalize_confidence(
        ctx.get("confidence_score", ctx.get("confidence"))
    )
    return risk_status, var_status, trust_status, confidence_score, confidence_label


def _module_class_from_source(source: str) -> str:
    norm = str(source or "").strip().lower()
    if not norm:
        return "GENERAL"
    if norm.startswith("combat_") or "combat" in norm:
        return "COMBAT"
    if norm.startswith("survival_"):
        return "F4"
    if norm.startswith("cash_in_") or norm.startswith("exploration_summary"):
        return "F4"
    if norm.startswith("exploration_"):
        return "EXPLORATION"
    if norm.startswith("navigation_") or "auto_clipboard" in norm:
        return "NAVIGATION"
    if norm.startswith("fuel_"):
        return "COMBAT"
    return "GENERAL"


def _module_class_for(insight: Insight) -> str:
    message_class = _MODULE_CLASS_BY_MESSAGE.get(str(insight.message_id or "").strip())
    if message_class:
        return message_class
    return _module_class_from_source(insight.source)


def _escalation_signature(insight: Insight) -> str:
    dedup = str(insight.dedup_key or "").strip()
    if dedup:
        return dedup
    msg = str(insight.message_id or "").strip() or "UNKNOWN_MSG"
    src = str(insight.source or "").strip() or "unknown_source"
    system = ""
    try:
        system = str((insight.context or {}).get("system") or "").strip()
    except Exception:
        system = ""
    return f"{msg}:{src}:{system or 'unknown'}"


def _try_escalate_priority(insight: Insight, gate: GateDecision) -> tuple[str, str | None]:
    base_priority = str(insight.priority or "P2_NORMAL").strip().upper()
    if not _priority_escalation_enabled():
        return base_priority, None
    if base_priority not in _PRIORITY_ESCALATION_ORDER:
        return base_priority, None
    if base_priority == "P0_CRITICAL":
        return base_priority, None
    if gate.risk_status not in {"RISK_HIGH", "RISK_CRITICAL"} and gate.var_status not in {
        "VAR_HIGH",
        "VAR_CRITICAL",
    }:
        return base_priority, None

    now = time.monotonic()
    window = _priority_escalation_window_sec()
    sig = _escalation_signature(insight)
    state = dict(_PRIORITY_ESCALATION_RUNTIME.get(sig) or {})
    last_ts = float(state.get("ts") or 0.0)
    hits = int(state.get("hits") or 0)
    if last_ts <= 0.0 or (now - last_ts) > window:
        hits = 1
    else:
        hits += 1
    state["ts"] = now
    state["hits"] = hits
    _PRIORITY_ESCALATION_RUNTIME[sig] = state

    if hits < 2:
        return base_priority, None

    next_priority = str(_PRIORITY_ESCALATION_NEXT.get(base_priority) or base_priority)
    if gate.risk_status == "RISK_CRITICAL" and hits >= 3 and next_priority == "P1_HIGH":
        next_priority = "P0_CRITICAL"
    if next_priority == base_priority:
        return base_priority, None
    return next_priority, f"escalated_{base_priority}_to_{next_priority}_hits_{hits}"


def _with_priority(insight: Insight, priority: str) -> Insight:
    return Insight(
        text=insight.text,
        message_id=insight.message_id,
        source=insight.source,
        context=dict(insight.context or {}),
        priority=str(priority or insight.priority or "P2_NORMAL"),
        dedup_key=insight.dedup_key,
        cooldown_scope=insight.cooldown_scope,
        cooldown_seconds=insight.cooldown_seconds,
        combat_silence_sensitive=insight.combat_silence_sensitive,
        force_tts=insight.force_tts,
    )


def evaluate_risk_trust_gate(insight: Insight) -> GateDecision:
    risk_status, var_status, trust_status, confidence_score, confidence_label = _gate_context_snapshot(
        insight.context
    )
    priority = str(insight.priority or "P2_NORMAL").strip().upper()

    if insight.force_tts:
        return GateDecision(
            allow_emit=True,
            risk_status=risk_status,
            var_status=var_status,
            trust_status=trust_status,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            reason="force_tts",
        )

    if priority == "P0_CRITICAL":
        return GateDecision(
            allow_emit=True,
            risk_status=risk_status,
            var_status=var_status,
            trust_status=trust_status,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            reason="priority_critical",
        )

    if confidence_score < 0.35 and priority in {"P2_NORMAL", "P3_LOW"}:
        return GateDecision(
            allow_emit=False,
            risk_status=risk_status,
            var_status=var_status,
            trust_status=trust_status,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            reason="low_confidence",
        )

    if trust_status == "TRUST_LOW" and confidence_score < 0.5 and priority != "P1_HIGH":
        return GateDecision(
            allow_emit=False,
            risk_status=risk_status,
            var_status=var_status,
            trust_status=trust_status,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            reason="trust_low_confidence_low",
        )

    if var_status == "VAR_NEGLIGIBLE" and priority == "P3_LOW":
        return GateDecision(
            allow_emit=False,
            risk_status=risk_status,
            var_status=var_status,
            trust_status=trust_status,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            reason="var_negligible_low_priority",
        )

    return GateDecision(
        allow_emit=True,
        risk_status=risk_status,
        var_status=var_status,
        trust_status=trust_status,
        confidence_score=confidence_score,
        confidence_label=confidence_label,
        reason="allow_default",
    )


def _is_combat_silence_active(context: dict | None) -> bool:
    ctx = context or {}
    if bool(ctx.get("combat_silence")):
        return True
    if bool(ctx.get("in_combat")):
        return True
    state = str(ctx.get("combat_state", "")).strip().lower()
    if state in {"combat", "enter", "active"}:
        return True

    # F7 safety overlay: MANUAL mode can keep explicit mode_id while still
    # applying combat silence when AUTO detector sees active combat.
    try:
        from app.state import app_state  # type: ignore

        snapshot = app_state.get_mode_state_snapshot()
        source = str(snapshot.get("mode_source") or "").strip().upper()
        overlay = str(snapshot.get("mode_overlay") or "").strip().upper()
        if source == "MANUAL" and overlay == "COMBAT":
            return True
    except Exception as e:
        log_event_throttled(
            "DISPATCHER:COMBAT_SILENCE_SNAPSHOT_FAILED",
            10000,
            "WARN",
            "combat silence snapshot read failed",
            error=f"{type(e).__name__}: {e}",
        )
        # Failsafe: if we cannot read combat-mode snapshot reliably, stay quiet.
        return True

    return False


def _cooldown_gate_for(insight: Insight) -> tuple[str, str | None]:
    scope = str(insight.cooldown_scope or "message").strip().lower()
    dedup_key = str(insight.dedup_key or insight.message_id or "").strip() or None
    if scope == "global":
        return "INSIGHT_GLOBAL", None
    if scope == "action":
        return f"INSIGHT_ACTION:{insight.source}", dedup_key
    if scope == "entity":
        return f"INSIGHT_ENTITY:{insight.message_id}", dedup_key
    return f"INSIGHT_MESSAGE:{insight.message_id}", dedup_key


def _evaluate_should_speak(insight: Insight) -> tuple[bool, str]:
    message_id = str(insight.message_id or "").strip()
    source = str(insight.source or "").strip()
    if not message_id or not source:
        return False, "missing_message_or_source"

    if insight.force_tts:
        return True, "force_tts"

    gate = evaluate_risk_trust_gate(insight)
    if not gate.allow_emit:
        return False, str(gate.reason or "gate_blocked")

    priority = str(insight.priority or "P2_NORMAL").strip().upper()
    if insight.combat_silence_sensitive and priority != "P0_CRITICAL":
        if _is_combat_silence_active(insight.context):
            return False, "combat_silence"

    cooldown_sec = float(
        insight.cooldown_seconds if insight.cooldown_seconds is not None else _default_cooldown(priority)
    )
    gate_key, gate_ctx = _cooldown_gate_for(insight)
    if cooldown_sec > 0 and not _notify.DEBOUNCER.can_send(gate_key, cooldown_sec, context=gate_ctx):
        return False, "insight_cooldown"

    module_class = _module_class_for(insight)
    class_cooldown_sec = _module_class_cooldown_sec(module_class)
    if (
        class_cooldown_sec > 0.0
        and priority != "P0_CRITICAL"
        and not _notify.DEBOUNCER.can_send(
            f"INSIGHT_CLASS:{module_class}",
            class_cooldown_sec,
            context=module_class,
        )
    ):
        return False, "class_cooldown"

    if priority == "P0_CRITICAL":
        return True, "priority_critical"

    # Hard semantic suppress from caller (e.g. auto summary -> cash-in sequence).
    # Must return a distinct reason so _apply_cross_module_voice_priority and
    # _apply_priority_matrix cannot override it via the "notify_policy" path.
    if bool((insight.context or {}).get("suppress_tts")):
        log_event_throttled(
            "dispatcher:suppress_tts_explicit",
            5000,
            "VOICE",
            "voice blocked: suppress_tts_explicit (cross-module override disabled)",
            message_id=message_id,
            voice_sequence_reason=str((insight.context or {}).get("voice_sequence_reason", "")),
        )
        return False, "suppress_tts_explicit"

    if bool(_notify._should_speak_tts(message_id, insight.context)):
        return True, "notify_policy_allow"
    return False, "notify_policy"


def should_speak(insight: Insight) -> bool:
    allow, _reason = _evaluate_should_speak(insight)
    return allow


def _apply_cross_module_voice_priority(
    insight: Insight,
    *,
    allow_tts: bool,
    allow_reason: str,
) -> tuple[bool, str, bool]:
    if bool((insight.context or {}).get("voice_ui_user_action_bypass")):
        return allow_tts, "ui_user_action_bypass", False

    group_id = _cross_module_group(insight.message_id)
    if not group_id:
        return allow_tts, allow_reason, False

    now = time.monotonic()
    state = _CROSS_MODULE_RUNTIME.get(group_id) or {}
    ts_val = state.get("ts")
    ts = float(ts_val) if ts_val is not None else 0.0
    prev_rank_val = state.get("priority_rank")
    prev_rank = int(prev_rank_val) if prev_rank_val is not None else 999
    rank = _priority_rank(insight.priority)
    window_sec = _cross_module_window_sec(group_id)

    if ts <= 0.0 or (now - ts) > window_sec:
        return allow_tts, allow_reason, False

    priority = str(insight.priority or "").strip().upper()
    if priority == "P0_CRITICAL":
        if allow_tts:
            return True, "cross_module_p0_critical", False
        if allow_reason == "notify_policy":
            return True, "cross_module_p0_critical_force", True
        return allow_tts, allow_reason, False

    if rank < prev_rank:
        if allow_tts:
            return True, "cross_module_preempt_higher", False
        if allow_reason == "notify_policy":
            return True, "cross_module_preempt_higher_force", True
        return allow_tts, allow_reason, False

    if allow_tts and rank >= prev_rank:
        return False, "cross_module_suppressed_by_recent_higher_or_equal", False

    return allow_tts, allow_reason, False


def _apply_priority_matrix(
    insight: Insight,
    *,
    allow_tts: bool,
    allow_reason: str,
) -> tuple[bool, str, bool]:
    if bool((insight.context or {}).get("voice_ui_user_action_bypass")):
        return allow_tts, "ui_user_action_bypass", False

    if bool((insight.context or {}).get("fss_milestone_sequence")):
        return allow_tts, allow_reason, False

    if str(allow_reason or "").startswith("cross_module_"):
        return allow_tts, allow_reason, False

    module_class = _module_class_for(insight)
    class_rank = int(_MODULE_CLASS_RANK.get(module_class, _MODULE_CLASS_RANK["GENERAL"]))
    now = time.monotonic()
    state = dict(_PRIORITY_MATRIX_RUNTIME.get("last_voice") or {})
    ts_val = state.get("ts")
    ts = float(ts_val) if ts_val is not None else 0.0
    if ts <= 0.0 or (now - ts) > _priority_matrix_window_sec():
        return allow_tts, allow_reason, False

    prev_priority_rank_val = state.get("priority_rank")
    prev_priority_rank = int(prev_priority_rank_val) if prev_priority_rank_val is not None else 999
    prev_class_rank_val = state.get("class_rank")
    prev_class_rank = (
        int(prev_class_rank_val)
        if prev_class_rank_val is not None
        else int(_MODULE_CLASS_RANK["GENERAL"])
    )
    current_priority_rank = _priority_rank(insight.priority)
    current_pair = (class_rank, current_priority_rank)
    previous_pair = (prev_class_rank, prev_priority_rank)

    priority = str(insight.priority or "").strip().upper()
    if priority == "P0_CRITICAL":
        if allow_tts:
            return True, "matrix_p0_critical", False
        if allow_reason == "notify_policy":
            return True, "matrix_p0_critical_force", True
        return allow_tts, allow_reason, False

    if current_pair < previous_pair:
        if allow_tts:
            return True, "matrix_preempt_higher", False
        if allow_reason == "notify_policy":
            return True, "matrix_preempt_higher_force", True
        return allow_tts, allow_reason, False

    if allow_tts and current_pair >= previous_pair:
        return False, "matrix_suppressed_by_recent_higher_or_equal", False

    return allow_tts, allow_reason, False


def _remember_cross_module_voice(insight: Insight) -> None:
    group_id = _cross_module_group(insight.message_id)
    if not group_id:
        pass
    else:
        _CROSS_MODULE_RUNTIME[group_id] = {
            "message_id": str(insight.message_id or ""),
            "priority_rank": _priority_rank(insight.priority),
            "ts": time.monotonic(),
        }

    module_class = _module_class_for(insight)
    _PRIORITY_MATRIX_RUNTIME["last_voice"] = {
        "message_id": str(insight.message_id or ""),
        "module_class": module_class,
        "class_rank": int(_MODULE_CLASS_RANK.get(module_class, _MODULE_CLASS_RANK["GENERAL"])),
        "priority_rank": _priority_rank(insight.priority),
        "ts": time.monotonic(),
    }


def emit_insight(
    text: str,
    *,
    gui_ref=None,
    message_id: str,
    source: str,
    context: dict | None = None,
    event_type: str | None = None,
    priority: str = "P2_NORMAL",
    dedup_key: str | None = None,
    cooldown_scope: str = "message",
    cooldown_seconds: float | None = None,
    combat_silence_sensitive: bool = True,
    force_tts: bool = False,
) -> bool:
    contract = resolve_emit_contract(
        message_id=message_id,
        context=context,
        event_type=event_type,
        priority=priority,
        dedup_key=dedup_key,
        cooldown_scope=cooldown_scope,
        cooldown_seconds=cooldown_seconds,
    )

    insight = Insight(
        text=str(text or ""),
        message_id=str(message_id or ""),
        source=str(source or ""),
        context=dict(contract.get("context") or {}),
        priority=str(contract.get("priority") or "P2_NORMAL"),
        dedup_key=contract.get("dedup_key"),
        cooldown_scope=str(contract.get("cooldown_scope") or "message"),
        cooldown_seconds=contract.get("cooldown_seconds"),
        combat_silence_sensitive=combat_silence_sensitive,
        force_tts=bool(force_tts),
    )

    initial_gate = evaluate_risk_trust_gate(insight)
    effective_priority, escalation_reason = _try_escalate_priority(insight, initial_gate)
    effective_insight = insight if effective_priority == insight.priority else _with_priority(insight, effective_priority)

    gate = initial_gate if effective_insight is insight else evaluate_risk_trust_gate(effective_insight)
    allow_tts, allow_reason = _evaluate_should_speak(effective_insight)
    allow_tts, allow_reason, forced_by_cross_module = _apply_cross_module_voice_priority(
        effective_insight,
        allow_tts=allow_tts,
        allow_reason=allow_reason,
    )
    allow_tts, allow_reason, forced_by_matrix = _apply_priority_matrix(
        effective_insight,
        allow_tts=allow_tts,
        allow_reason=allow_reason,
    )
    runtime_ctx = dict(insight.context or {})
    runtime_ctx["module_class"] = _module_class_for(effective_insight)
    runtime_ctx["base_priority"] = str(insight.priority or "P2_NORMAL")
    runtime_ctx["effective_priority"] = str(effective_insight.priority or "P2_NORMAL")
    if escalation_reason:
        runtime_ctx["priority_escalation_reason"] = escalation_reason
    runtime_ctx["risk_status"] = gate.risk_status
    runtime_ctx["var_status"] = gate.var_status
    runtime_ctx["trust_status"] = gate.trust_status
    runtime_ctx["confidence"] = gate.confidence_label
    runtime_ctx["confidence_score"] = gate.confidence_score
    runtime_ctx["gate_reason"] = gate.reason
    runtime_ctx["voice_priority_reason"] = allow_reason
    if allow_tts:
        runtime_ctx["force_tts"] = True
    else:
        runtime_ctx["suppress_tts"] = True
    if forced_by_cross_module:
        runtime_ctx["voice_priority_forced"] = True
    if forced_by_matrix:
        runtime_ctx["voice_priority_forced"] = True

    log_event(
        "INSIGHT",
        "emit_decision",
        message_id=str(effective_insight.message_id or ""),
        source=str(effective_insight.source or ""),
        event_type=str(event_type or ""),
        allow_tts=bool(allow_tts),
        gate_reason=str(gate.reason or ""),
        voice_reason=str(allow_reason or ""),
        base_priority=str(insight.priority or "P2_NORMAL"),
        effective_priority=str(effective_insight.priority or "P2_NORMAL"),
        dedup_key=str(effective_insight.dedup_key or ""),
        system=str(runtime_ctx.get("system") or ""),
    )

    # Keep log/UI line behavior from existing powiedz() path.
    _notify.powiedz(
        effective_insight.text,
        gui_ref,
        message_id=effective_insight.message_id,
        context=runtime_ctx,
        force=allow_tts,
    )
    if allow_tts:
        _remember_cross_module_voice(effective_insight)
    return allow_tts


def pick_insight_for_emit(insights: Iterable[Insight]) -> Optional[Insight]:
    items = list(insights or [])
    if not items:
        return None
    # Deterministic: severity first, then module class matrix, then original order.
    ranked = sorted(
        enumerate(items),
        key=lambda p: (
            _priority_rank(p[1].priority),
            int(_MODULE_CLASS_RANK.get(_module_class_for(p[1]), _MODULE_CLASS_RANK["GENERAL"])),
            p[0],
        ),
    )
    return ranked[0][1] if ranked else None


def emit_best_insight(insights: Iterable[Insight], *, gui_ref=None) -> Optional[Insight]:
    selected = pick_insight_for_emit(insights)
    if not selected:
        return None
    emit_insight(
        selected.text,
        gui_ref=gui_ref,
        message_id=selected.message_id,
        source=selected.source,
        context=selected.context,
        priority=selected.priority,
        dedup_key=selected.dedup_key,
        cooldown_scope=selected.cooldown_scope,
        cooldown_seconds=selected.cooldown_seconds,
        combat_silence_sensitive=selected.combat_silence_sensitive,
        force_tts=selected.force_tts,
    )
    return selected
