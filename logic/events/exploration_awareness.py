from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict

import config

from logic.insight_dispatcher import emit_insight
from logic.utils.renata_log import log_event_throttled


@dataclass
class _SystemAwarenessState:
    callouts_emitted: int = 0
    summary_emitted: bool = False
    suppressed_count: int = 0
    emitted_keys: set[str] = field(default_factory=set)


_LOCK = Lock()
_SYSTEM_STATE: dict[str, _SystemAwarenessState] = {}
_SESSION_CALLOUTS_EMITTED = 0

_DEFAULT_MAX_CALLOUTS_PER_SYSTEM = 3
_DEFAULT_MAX_CALLOUTS_PER_SESSION = 60

_REQUIRED_EXPLORATION_CALLOUTS = {
    "MSG.HIGH_VALUE_DSS_HINT",
    "MSG.HIGH_VALUE_FIRST_LOGGED_ALERT",
    "MSG.ELW_DETECTED",
    "MSG.WW_DETECTED",
    "MSG.TERRAFORMABLE_DETECTED",
    "MSG.DSS_TARGET_HINT",
    "MSG.BIO_SIGNALS_HIGH",
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _system_key(system_name: str | None) -> str:
    return _as_text(system_name).lower() or "unknown"


def _max_callouts_per_system() -> int:
    try:
        raw = int(config.get("exploration.awareness.max_callouts_per_system", _DEFAULT_MAX_CALLOUTS_PER_SYSTEM))
    except Exception:
        log_event_throttled(
            "exploration.awareness.max_per_system",
            10000,
            "EXPL",
            "invalid exploration awareness per-system limit; using default",
        )
        raw = _DEFAULT_MAX_CALLOUTS_PER_SYSTEM
    return max(1, raw)


def _max_callouts_per_session() -> int:
    try:
        raw = int(config.get("exploration.awareness.max_callouts_per_session", _DEFAULT_MAX_CALLOUTS_PER_SESSION))
    except Exception:
        log_event_throttled(
            "exploration.awareness.max_per_session",
            10000,
            "EXPL",
            "invalid exploration awareness per-session limit; using default",
        )
        raw = _DEFAULT_MAX_CALLOUTS_PER_SESSION
    return max(1, raw)


def reset_exploration_awareness() -> None:
    global _SESSION_CALLOUTS_EMITTED
    with _LOCK:
        _SYSTEM_STATE.clear()
        _SESSION_CALLOUTS_EMITTED = 0


def reset_system_awareness(system_name: str | None) -> None:
    key = _system_key(system_name)
    with _LOCK:
        _SYSTEM_STATE.pop(key, None)


def get_awareness_snapshot(system_name: str | None) -> Dict[str, Any]:
    key = _system_key(system_name)
    with _LOCK:
        state = _SYSTEM_STATE.get(key) or _SystemAwarenessState()
        return {
            "system": key,
            "callouts_emitted": int(state.callouts_emitted),
            "summary_emitted": bool(state.summary_emitted),
            "suppressed_count": int(state.suppressed_count),
            "session_callouts_emitted": int(_SESSION_CALLOUTS_EMITTED),
        }


def _default_context(system_name: str | None, body_name: str | None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "system": _as_text(system_name) or None,
        "risk_status": "RISK_LOW",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
    }
    body = _as_text(body_name)
    if body:
        ctx["body"] = body
    return ctx


def emit_callout_or_summary(
    *,
    text: str,
    gui_ref=None,
    message_id: str,
    source: str,
    system_name: str | None,
    body_name: str | None = None,
    callout_key: str,
    event_type: str = "BODY_DISCOVERED",
    priority: str = "P2_NORMAL",
    context: Dict[str, Any] | None = None,
    summary_text: str = (
        "W tym systemie są jeszcze obiekty warte uwagi eksploracyjnej. "
        "Oznaczyłam najlepsze kandydaty."
    ),
    summary_message_id: str = "MSG.EXPLORATION_AWARENESS_SUMMARY",
    required_callout: bool = False,
) -> str:
    """
    Exploration awareness anti-spam gate:
    - limits callouts per system and per session,
    - emits one compact system summary when limit is reached,
    - keeps deterministic dedup keying by message/body scope.

    Returns:
    - "callout" when callout was emitted,
    - "summary" when summary was emitted due to limits,
    - "dropped_duplicate" when callout key already emitted in system,
    - "dropped_limit" when suppressed after summary.
    """
    global _SESSION_CALLOUTS_EMITTED

    system_key = _system_key(system_name)
    key_norm = _as_text(callout_key).lower() or "unknown"
    state: _SystemAwarenessState

    emit_mode = "callout"
    is_required = bool(required_callout) or str(message_id or "").strip().upper() in _REQUIRED_EXPLORATION_CALLOUTS
    with _LOCK:
        state = _SYSTEM_STATE.setdefault(system_key, _SystemAwarenessState())

        if key_norm in state.emitted_keys:
            return "dropped_duplicate"

        if is_required:
            # Required exploration callouts are deterministic and must not be
            # dropped by the awareness limiter. We still dedupe by key.
            state.emitted_keys.add(key_norm)
        else:
            per_system_limit = _max_callouts_per_system()
            per_session_limit = _max_callouts_per_session()
            over_system_limit = state.callouts_emitted >= per_system_limit
            over_session_limit = _SESSION_CALLOUTS_EMITTED >= per_session_limit

            if over_system_limit or over_session_limit:
                state.suppressed_count += 1
                if state.summary_emitted:
                    return "dropped_limit"
                state.summary_emitted = True
                emit_mode = "summary"
            else:
                state.emitted_keys.add(key_norm)
                state.callouts_emitted += 1
                _SESSION_CALLOUTS_EMITTED += 1

    ctx = _default_context(system_name, body_name)
    if context:
        ctx.update(dict(context))
    if is_required:
        ctx["exploration_awareness_required"] = True

    if emit_mode == "summary":
        ctx["raw_text"] = summary_text
        ctx["suppressed_count"] = int(state.suppressed_count)
        emit_insight(
            summary_text,
            gui_ref=gui_ref,
            message_id=summary_message_id,
            source=source,
            event_type="SYSTEM_SUMMARY",
            context=ctx,
            priority="P3_LOW",
            dedup_key=f"exp_awareness_summary:{system_key}",
            cooldown_scope="entity",
            cooldown_seconds=45.0,
        )
        return "summary"

    emit_insight(
        text,
        gui_ref=gui_ref,
        message_id=message_id,
        source=source,
        event_type=event_type,
        context=ctx,
        priority=priority,
        dedup_key=f"exp_callout:{system_key}:{key_norm}",
        cooldown_scope="entity",
        cooldown_seconds=30.0,
    )
    return "callout"
