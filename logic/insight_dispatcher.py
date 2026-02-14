from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import config
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


def _priority_rank(priority: str) -> int:
    return _PRIORITY_ORDER.get(str(priority or "").strip().upper(), 999)


def _default_cooldown(priority: str) -> float:
    norm = str(priority or "").strip().upper()
    return float(_DEFAULT_COOLDOWN_BY_PRIORITY.get(norm, _DEFAULT_COOLDOWN_BY_PRIORITY["P2_NORMAL"]))


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

    allow_tts = should_speak(insight)
    runtime_ctx = dict(insight.context or {})
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
