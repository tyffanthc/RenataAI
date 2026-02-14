from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class InsightClassSpec:
    class_id: str
    canonical_event: str
    kind: str
    decision_space: str
    default_priority: str
    default_cooldown_scope: str
    default_cooldown_seconds: float
    dedup_template: str


INSIGHT_CLASS_BY_MESSAGE_ID: Dict[str, InsightClassSpec] = {
    "MSG.NEXT_HOP": InsightClassSpec(
        class_id="NAV_NEXT_HOP",
        canonical_event="ROUTE_PROGRESS",
        kind="route",
        decision_space="route_follow",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="next_hop:{system}",
    ),
    "MSG.JUMPED_SYSTEM": InsightClassSpec(
        class_id="NAV_JUMPED_SYSTEM",
        canonical_event="JUMP_COMPLETED",
        kind="route",
        decision_space="route_status",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="jumped:{system}",
    ),
    "MSG.NEXT_HOP_COPIED": InsightClassSpec(
        class_id="NAV_TARGET_COPIED",
        canonical_event="ROUTE_PROGRESS",
        kind="route",
        decision_space="clipboard_hint",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="target_copy:{system}",
    ),
    "MSG.DOCKED": InsightClassSpec(
        class_id="NAV_DOCKED",
        canonical_event="ROUTE_PROGRESS",
        kind="route",
        decision_space="status_update",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="docked:{station}",
    ),
    "MSG.UNDOCKED": InsightClassSpec(
        class_id="NAV_UNDOCKED",
        canonical_event="ROUTE_PROGRESS",
        kind="route",
        decision_space="status_update",
        default_priority="P2_NORMAL",
        default_cooldown_scope="message",
        default_cooldown_seconds=6.0,
        dedup_template="undocked",
    ),
    "MSG.FUEL_CRITICAL": InsightClassSpec(
        class_id="FUEL_CRITICAL",
        canonical_event="SHIP_HEALTH_CHANGED",
        kind="risk",
        decision_space="critical_warning",
        default_priority="P0_CRITICAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=300.0,
        dedup_template="low_fuel:{system}",
    ),
    "MSG.FSS_PROGRESS_25": InsightClassSpec(
        class_id="FSS_PROGRESS_25",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss25:{system}",
    ),
    "MSG.FSS_PROGRESS_50": InsightClassSpec(
        class_id="FSS_PROGRESS_50",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss50:{system}",
    ),
    "MSG.FSS_PROGRESS_75": InsightClassSpec(
        class_id="FSS_PROGRESS_75",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss75:{system}",
    ),
    "MSG.FSS_LAST_BODY": InsightClassSpec(
        class_id="FSS_LAST_BODY",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_last:{system}",
    ),
    "MSG.SYSTEM_FULLY_SCANNED": InsightClassSpec(
        class_id="FSS_FULLY_SCANNED",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_complete",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_full:{system}",
    ),
    "MSG.FIRST_DISCOVERY": InsightClassSpec(
        class_id="FSS_FIRST_DISCOVERY",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="first_confirmed",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="first_discovery_system:{system}",
    ),
    "MSG.FIRST_DISCOVERY_OPPORTUNITY": InsightClassSpec(
        class_id="FSS_FIRST_DISCOVERY_OPPORTUNITY",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="first_opportunity",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="first_opportunity_system:{system}",
    ),
    "MSG.BODY_NO_PREV_DISCOVERY": InsightClassSpec(
        class_id="FSS_BODY_NO_PREV_DISCOVERY",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="first_confirmed",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="first_body:{body}",
    ),
    "MSG.ELW_DETECTED": InsightClassSpec(
        class_id="EXP_ELW_CALLOUT",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="planet_callout",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=30.0,
        dedup_template="exp_callout:{system}:elw:{body}",
    ),
    "MSG.WW_DETECTED": InsightClassSpec(
        class_id="EXP_WW_CALLOUT",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="planet_callout",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=30.0,
        dedup_template="exp_callout:{system}:ww:{body}",
    ),
    "MSG.TERRAFORMABLE_DETECTED": InsightClassSpec(
        class_id="EXP_TERRAFORMABLE_CALLOUT",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="planet_callout",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=30.0,
        dedup_template="exp_callout:{system}:terraformable:{body}",
    ),
    "MSG.BIO_SIGNALS_HIGH": InsightClassSpec(
        class_id="EXP_BIO_CALLOUT",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="planet_callout",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=30.0,
        dedup_template="exp_callout:{system}:bio:{body}",
    ),
    "MSG.FOOTFALL": InsightClassSpec(
        class_id="EXP_FOOTFALL_CONFIRMED",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="first_confirmed",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="footfall:{body}",
    ),
    "MSG.EXPLORATION_SYSTEM_SUMMARY": InsightClassSpec(
        class_id="EXP_SYSTEM_SUMMARY",
        canonical_event="SYSTEM_SUMMARY",
        kind="exploration",
        decision_space="system_summary",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=45.0,
        dedup_template="exp_summary:{system}",
    ),
}


def get_insight_class(message_id: str) -> InsightClassSpec | None:
    return INSIGHT_CLASS_BY_MESSAGE_ID.get(str(message_id or "").strip())


def _render_dedup_template(template: str, context: Dict[str, Any], message_id: str) -> str:
    if not template:
        return str(message_id or "insight")

    safe_context: Dict[str, str] = {}
    for key, value in (context or {}).items():
        text = str(value or "").strip()
        safe_context[str(key)] = text or "unknown"

    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "unknown"

    try:
        return template.format_map(_SafeDict(safe_context))
    except Exception:
        return str(message_id or "insight")


def resolve_emit_contract(
    *,
    message_id: str,
    context: Dict[str, Any] | None,
    event_type: str | None = None,
    priority: str | None = None,
    dedup_key: str | None = None,
    cooldown_scope: str | None = None,
    cooldown_seconds: float | None = None,
) -> Dict[str, Any]:
    msg_id = str(message_id or "").strip()
    runtime_ctx: Dict[str, Any] = dict(context or {})
    spec = get_insight_class(msg_id)

    if spec is None:
        runtime_ctx.setdefault("canonical_event", str(event_type or "UNKNOWN_EVENT"))
        runtime_ctx.setdefault("insight_class", msg_id or "UNKNOWN_MESSAGE")
        runtime_ctx.setdefault("insight_kind", "general")
        runtime_ctx.setdefault("decision_space", "default")
        return {
            "context": runtime_ctx,
            "priority": str(priority or "P2_NORMAL"),
            "dedup_key": dedup_key,
            "cooldown_scope": str(cooldown_scope or "message"),
            "cooldown_seconds": cooldown_seconds,
        }

    runtime_ctx.setdefault("canonical_event", str(event_type or spec.canonical_event))
    runtime_ctx.setdefault("insight_class", spec.class_id)
    runtime_ctx.setdefault("insight_kind", spec.kind)
    runtime_ctx.setdefault("decision_space", spec.decision_space)

    resolved_priority = str(priority or spec.default_priority)
    resolved_scope = str(cooldown_scope or spec.default_cooldown_scope)
    resolved_cooldown = spec.default_cooldown_seconds if cooldown_seconds is None else float(cooldown_seconds)
    resolved_dedup = dedup_key or _render_dedup_template(spec.dedup_template, runtime_ctx, msg_id)

    return {
        "context": runtime_ctx,
        "priority": resolved_priority,
        "dedup_key": resolved_dedup,
        "cooldown_scope": resolved_scope,
        "cooldown_seconds": resolved_cooldown,
    }
