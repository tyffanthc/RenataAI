from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from logic.utils import notify as _notify


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
    return state in {"combat", "enter", "active"}


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


def should_speak(insight: Insight) -> bool:
    message_id = str(insight.message_id or "").strip()
    source = str(insight.source or "").strip()
    if not message_id or not source:
        return False

    if insight.force_tts:
        return True

    gate = evaluate_risk_trust_gate(insight)
    if not gate.allow_emit:
        return False

    priority = str(insight.priority or "P2_NORMAL").strip().upper()
    if insight.combat_silence_sensitive and priority != "P0_CRITICAL":
        if _is_combat_silence_active(insight.context):
            return False

    cooldown_sec = float(
        insight.cooldown_seconds if insight.cooldown_seconds is not None else _default_cooldown(priority)
    )
    gate_key, gate_ctx = _cooldown_gate_for(insight)
    if cooldown_sec > 0 and not _notify.DEBOUNCER.can_send(gate_key, cooldown_sec, context=gate_ctx):
        return False

    if priority == "P0_CRITICAL":
        return True

    return bool(_notify._should_speak_tts(message_id, insight.context))


def emit_insight(
    text: str,
    *,
    gui_ref=None,
    message_id: str,
    source: str,
    context: dict | None = None,
    priority: str = "P2_NORMAL",
    dedup_key: str | None = None,
    cooldown_scope: str = "message",
    cooldown_seconds: float | None = None,
    combat_silence_sensitive: bool = True,
    force_tts: bool = False,
) -> bool:
    insight = Insight(
        text=str(text or ""),
        message_id=str(message_id or ""),
        source=str(source or ""),
        context=dict(context or {}),
        priority=str(priority or "P2_NORMAL"),
        dedup_key=dedup_key,
        cooldown_scope=cooldown_scope,
        cooldown_seconds=cooldown_seconds,
        combat_silence_sensitive=combat_silence_sensitive,
        force_tts=bool(force_tts),
    )

    gate = evaluate_risk_trust_gate(insight)
    allow_tts = should_speak(insight)
    runtime_ctx = dict(insight.context or {})
    runtime_ctx["risk_status"] = gate.risk_status
    runtime_ctx["var_status"] = gate.var_status
    runtime_ctx["trust_status"] = gate.trust_status
    runtime_ctx["confidence"] = gate.confidence_label
    runtime_ctx["confidence_score"] = gate.confidence_score
    runtime_ctx["gate_reason"] = gate.reason
    if allow_tts:
        runtime_ctx["force_tts"] = True
    else:
        runtime_ctx["suppress_tts"] = True

    # Keep log/UI line behavior from existing powiedz() path.
    _notify.powiedz(
        insight.text,
        gui_ref,
        message_id=insight.message_id,
        context=runtime_ctx,
        force=allow_tts,
    )
    return allow_tts


def pick_insight_for_emit(insights: Iterable[Insight]) -> Optional[Insight]:
    items = list(insights or [])
    if not items:
        return None
    # Deterministic: stable sort by priority rank, then original order.
    ranked = sorted(enumerate(items), key=lambda p: (_priority_rank(p[1].priority), p[0]))
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
