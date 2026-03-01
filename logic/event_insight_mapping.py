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


@dataclass(frozen=True)
class TTSPolicySpec:
    message_id: str
    intent: str
    category: str
    cooldown_policy: str = "NORMAL"  # NORMAL | BYPASS_GLOBAL | ALWAYS_SAY


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
    "MSG.FSS_BODYCOUNT_SYNCED": InsightClassSpec(
        class_id="FSS_BODYCOUNT_SYNCED",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_bodycount_synced:{system}",
    ),
    "MSG.FSS_SIGNALS_COMPLETE_PENDING_CLASSIFY": InsightClassSpec(
        class_id="FSS_SIGNALS_COMPLETE_PENDING_CLASSIFY",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_signals_pending:{system}",
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
    "MSG.FSS_PASSIVE_DATA_INGESTED": InsightClassSpec(
        class_id="FSS_PASSIVE_DATA_INGESTED",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_passive_data:{system}",
    ),
    "MSG.FSS_PASSIVE_DATA_OFFLINE_MAP": InsightClassSpec(
        class_id="FSS_PASSIVE_DATA_OFFLINE_MAP",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_progress",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_passive_data:{system}",
    ),
    "MSG.FSS_PASSIVE_SYSTEM_COMPLETE": InsightClassSpec(
        class_id="FSS_PASSIVE_SYSTEM_COMPLETE",
        canonical_event="SYSTEM_SCANNED",
        kind="exploration",
        decision_space="scan_complete",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="fss_passive_full:{system}",
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
    "MSG.HIGH_VALUE_DSS_HINT": InsightClassSpec(
        class_id="EXP_HIGH_VALUE_DSS_HINT",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="planet_callout",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=30.0,
        dedup_template="exp_callout:{system}:hv_dss:{body}",
    ),
    "MSG.HIGH_VALUE_FIRST_LOGGED_ALERT": InsightClassSpec(
        class_id="EXP_HIGH_VALUE_FIRST_LOGGED",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="exobio_first_logged",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=45.0,
        dedup_template="exp_callout:{system}:first_logged:{body}",
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
    "MSG.DSS_TARGET_HINT": InsightClassSpec(
        class_id="EXP_DSS_TARGET_HINT",
        canonical_event="BODY_DISCOVERED",
        kind="exploration",
        decision_space="dss_value_hint",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=30.0,
        dedup_template="exp_callout:{system}:dss_target:{body}",
    ),
    "MSG.DSS_COMPLETED": InsightClassSpec(
        class_id="EXP_DSS_COMPLETED",
        canonical_event="BODY_MAPPED",
        kind="exploration",
        decision_space="dss_completion",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=45.0,
        dedup_template="dss_complete:{system}:{body}",
    ),
    "MSG.DSS_PROGRESS": InsightClassSpec(
        class_id="EXP_DSS_PROGRESS",
        canonical_event="BODY_MAPPED",
        kind="exploration",
        decision_space="dss_progress",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=45.0,
        dedup_template="dss_progress:{system}",
    ),
    "MSG.FIRST_MAPPED": InsightClassSpec(
        class_id="EXP_FIRST_MAPPED_CONFIRMED",
        canonical_event="BODY_MAPPED",
        kind="exploration",
        decision_space="first_confirmed",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="first_mapped:{body}",
    ),
    "MSG.EXOBIO_SAMPLE_LOGGED": InsightClassSpec(
        class_id="EXOBIO_SAMPLE_PROGRESS",
        canonical_event="BIO_PROGRESS",
        kind="exploration",
        decision_space="exobio_progress",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=0.0,
        dedup_template="exobio_sample:{system}:{body}",
    ),
    "MSG.EXOBIO_SPECIES_COMPLETE": InsightClassSpec(
        class_id="EXOBIO_SPECIES_COMPLETE",
        canonical_event="BIO_PROGRESS",
        kind="exploration",
        decision_space="exobio_completion",
        default_priority="P1_HIGH",
        default_cooldown_scope="entity",
        default_cooldown_seconds=0.0,
        dedup_template="exobio_species_complete:{system}:{body}:{species}",
    ),
    "MSG.EXOBIO_RANGE_READY": InsightClassSpec(
        class_id="EXOBIO_RANGE_READY",
        canonical_event="BIO_PROGRESS",
        kind="exploration",
        decision_space="exobio_distance_gate",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=10.0,
        dedup_template="exobio_ready:{system}:{body}:{species}",
    ),
    "MSG.EXOBIO_NEW_ENTRY": InsightClassSpec(
        class_id="EXOBIO_NEW_ENTRY",
        canonical_event="BIO_DISCOVERED",
        kind="exploration",
        decision_space="exobio_codex",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="exobio_codex:{system}:{species}",
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
    "MSG.EXPLORATION_AWARENESS_SUMMARY": InsightClassSpec(
        class_id="EXP_AWARENESS_SUMMARY",
        canonical_event="SYSTEM_SUMMARY",
        kind="exploration",
        decision_space="awareness_summary",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=45.0,
        dedup_template="exp_awareness_summary:{system}",
    ),
    "MSG.CASH_IN_ASSISTANT": InsightClassSpec(
        class_id="EXP_CASH_IN_ASSISTANT",
        canonical_event="CASH_IN_REVIEW",
        kind="exploration",
        decision_space="cash_in_decision",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=90.0,
        dedup_template="cash_in:{system}",
    ),
    "MSG.CASH_IN_STARTJUMP": InsightClassSpec(
        class_id="EXP_CASH_IN_STARTJUMP",
        canonical_event="CASH_IN_STARTJUMP",
        kind="exploration",
        decision_space="cash_in_checkpoint",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=35.0,
        dedup_template="cash_in_startjump:{system}",
    ),
    "MSG.SURVIVAL_REBUY_HIGH": InsightClassSpec(
        class_id="SURVIVAL_REBUY_HIGH",
        canonical_event="SURVIVAL_RISK_CHANGED",
        kind="risk",
        decision_space="survival_warning",
        default_priority="P1_HIGH",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="survival_high:{system}",
    ),
    "MSG.SURVIVAL_REBUY_CRITICAL": InsightClassSpec(
        class_id="SURVIVAL_REBUY_CRITICAL",
        canonical_event="SURVIVAL_RISK_CHANGED",
        kind="risk",
        decision_space="survival_warning",
        default_priority="P0_CRITICAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=180.0,
        dedup_template="survival_critical:{system}",
    ),
    "MSG.COMBAT_AWARENESS_HIGH": InsightClassSpec(
        class_id="COMBAT_AWARENESS_HIGH",
        canonical_event="COMBAT_RISK_PATTERN",
        kind="risk",
        decision_space="combat_awareness",
        default_priority="P1_HIGH",
        default_cooldown_scope="entity",
        default_cooldown_seconds=75.0,
        dedup_template="combat_awareness_high:{system}",
    ),
    "MSG.COMBAT_AWARENESS_CRITICAL": InsightClassSpec(
        class_id="COMBAT_AWARENESS_CRITICAL",
        canonical_event="COMBAT_RISK_PATTERN",
        kind="risk",
        decision_space="combat_awareness",
        default_priority="P0_CRITICAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=90.0,
        dedup_template="combat_awareness_critical:{system}",
    ),
    "MSG.HIGH_G_WARNING": InsightClassSpec(
        class_id="HIGH_G_WARNING",
        canonical_event="SHIP_HEALTH_CHANGED",
        kind="risk",
        decision_space="high_g_warning",
        default_priority="P1_HIGH",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="high_g:{system}:{body}",
    ),
    "MSG.TRADE_DATA_STALE": InsightClassSpec(
        class_id="TRADE_DATA_STALE",
        canonical_event="TRADE_DATA_QUALITY",
        kind="trade",
        decision_space="trade_data_freshness",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=90.0,
        dedup_template="trade_stale:{system}",
    ),
    "MSG.PPM_SET_TARGET": InsightClassSpec(
        class_id="PPM_SET_TARGET",
        canonical_event="UI_CONTEXT_ACTION",
        kind="ui",
        decision_space="ppm_confirmation",
        default_priority="P2_NORMAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="ppm_set_target:{target}",
    ),
    "MSG.PPM_PIN_ACTION": InsightClassSpec(
        class_id="PPM_PIN_ACTION",
        canonical_event="UI_CONTEXT_ACTION",
        kind="ui",
        decision_space="ppm_confirmation",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="ppm_pin:{entry_id}",
    ),
    "MSG.PPM_COPY_SYSTEM": InsightClassSpec(
        class_id="PPM_COPY_SYSTEM",
        canonical_event="UI_CONTEXT_ACTION",
        kind="ui",
        decision_space="ppm_confirmation",
        default_priority="P3_LOW",
        default_cooldown_scope="entity",
        default_cooldown_seconds=8.0,
        dedup_template="ppm_copy_system:{system}",
    ),
    "MSG.RUNTIME_CRITICAL": InsightClassSpec(
        class_id="RUNTIME_CRITICAL",
        canonical_event="RUNTIME_FAILURE",
        kind="risk",
        decision_space="runtime_critical",
        default_priority="P0_CRITICAL",
        default_cooldown_scope="entity",
        default_cooldown_seconds=120.0,
        dedup_template="runtime_critical:{component}",
    ),
}

TTS_POLICY_BY_MESSAGE_ID: Dict[str, TTSPolicySpec] = {
    "MSG.FUEL_CRITICAL": TTSPolicySpec(
        message_id="MSG.FUEL_CRITICAL",
        intent="critical",
        category="alert",
        cooldown_policy="ALWAYS_SAY",
    ),
    "MSG.ROUTE_DESYNC": TTSPolicySpec(
        message_id="MSG.ROUTE_DESYNC",
        intent="critical",
        category="route",
    ),
    "MSG.ROUTE_FOUND": TTSPolicySpec(
        message_id="MSG.ROUTE_FOUND",
        intent="critical",
        category="route",
    ),
    "MSG.ROUTE_COMPLETE": TTSPolicySpec(
        message_id="MSG.ROUTE_COMPLETE",
        intent="critical",
        category="route",
    ),
    "MSG.NEXT_HOP": TTSPolicySpec(
        message_id="MSG.NEXT_HOP",
        intent="context",
        category="nav",
    ),
    "MSG.JUMPED_SYSTEM": TTSPolicySpec(
        message_id="MSG.JUMPED_SYSTEM",
        intent="context",
        category="nav",
    ),
    "MSG.NEXT_HOP_COPIED": TTSPolicySpec(
        message_id="MSG.NEXT_HOP_COPIED",
        intent="context",
        category="nav",
    ),
    "MSG.DOCKED": TTSPolicySpec(
        message_id="MSG.DOCKED",
        intent="context",
        category="info",
    ),
    "MSG.UNDOCKED": TTSPolicySpec(
        message_id="MSG.UNDOCKED",
        intent="context",
        category="info",
    ),
    "MSG.FIRST_DISCOVERY": TTSPolicySpec(
        message_id="MSG.FIRST_DISCOVERY",
        intent="context",
        category="explore",
    ),
    "MSG.FIRST_DISCOVERY_OPPORTUNITY": TTSPolicySpec(
        message_id="MSG.FIRST_DISCOVERY_OPPORTUNITY",
        intent="context",
        category="explore",
    ),
    "MSG.FOOTFALL": TTSPolicySpec(
        message_id="MSG.FOOTFALL",
        intent="context",
        category="explore",
    ),
    "MSG.HIGH_VALUE_DSS_HINT": TTSPolicySpec(
        message_id="MSG.HIGH_VALUE_DSS_HINT",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.HIGH_VALUE_FIRST_LOGGED_ALERT": TTSPolicySpec(
        message_id="MSG.HIGH_VALUE_FIRST_LOGGED_ALERT",
        intent="context",
        category="explore",
    ),
    "MSG.ELW_DETECTED": TTSPolicySpec(
        message_id="MSG.ELW_DETECTED",
        intent="context",
        category="explore",
    ),
    "MSG.WW_DETECTED": TTSPolicySpec(
        message_id="MSG.WW_DETECTED",
        intent="context",
        category="explore",
    ),
    "MSG.TERRAFORMABLE_DETECTED": TTSPolicySpec(
        message_id="MSG.TERRAFORMABLE_DETECTED",
        intent="context",
        category="explore",
    ),
    "MSG.BIO_SIGNALS_HIGH": TTSPolicySpec(
        message_id="MSG.BIO_SIGNALS_HIGH",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.DSS_TARGET_HINT": TTSPolicySpec(
        message_id="MSG.DSS_TARGET_HINT",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.DSS_COMPLETED": TTSPolicySpec(
        message_id="MSG.DSS_COMPLETED",
        intent="context",
        category="explore",
    ),
    "MSG.DSS_PROGRESS": TTSPolicySpec(
        message_id="MSG.DSS_PROGRESS",
        intent="context",
        category="explore",
    ),
    "MSG.FIRST_MAPPED": TTSPolicySpec(
        message_id="MSG.FIRST_MAPPED",
        intent="context",
        category="explore",
    ),
    "MSG.TRADE_JACKPOT": TTSPolicySpec(
        message_id="MSG.TRADE_JACKPOT",
        intent="context",
        category="info",
    ),
    "MSG.SMUGGLER_ILLEGAL_CARGO": TTSPolicySpec(
        message_id="MSG.SMUGGLER_ILLEGAL_CARGO",
        intent="critical",
        category="alert",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.EXOBIO_SAMPLE_LOGGED": TTSPolicySpec(
        message_id="MSG.EXOBIO_SAMPLE_LOGGED",
        intent="context",
        category="explore",
        cooldown_policy="ALWAYS_SAY",
    ),
    "MSG.EXOBIO_SPECIES_COMPLETE": TTSPolicySpec(
        message_id="MSG.EXOBIO_SPECIES_COMPLETE",
        intent="context",
        category="explore",
        cooldown_policy="ALWAYS_SAY",
    ),
    "MSG.EXOBIO_NEW_ENTRY": TTSPolicySpec(
        message_id="MSG.EXOBIO_NEW_ENTRY",
        intent="context",
        category="explore",
    ),
    "MSG.EXOBIO_RANGE_READY": TTSPolicySpec(
        message_id="MSG.EXOBIO_RANGE_READY",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_PROGRESS_25": TTSPolicySpec(
        message_id="MSG.FSS_PROGRESS_25",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_PROGRESS_50": TTSPolicySpec(
        message_id="MSG.FSS_PROGRESS_50",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_PROGRESS_75": TTSPolicySpec(
        message_id="MSG.FSS_PROGRESS_75",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_LAST_BODY": TTSPolicySpec(
        message_id="MSG.FSS_LAST_BODY",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_BODYCOUNT_SYNCED": TTSPolicySpec(
        message_id="MSG.FSS_BODYCOUNT_SYNCED",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_SIGNALS_COMPLETE_PENDING_CLASSIFY": TTSPolicySpec(
        message_id="MSG.FSS_SIGNALS_COMPLETE_PENDING_CLASSIFY",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.SYSTEM_FULLY_SCANNED": TTSPolicySpec(
        message_id="MSG.SYSTEM_FULLY_SCANNED",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_PASSIVE_DATA_INGESTED": TTSPolicySpec(
        message_id="MSG.FSS_PASSIVE_DATA_INGESTED",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_PASSIVE_DATA_OFFLINE_MAP": TTSPolicySpec(
        message_id="MSG.FSS_PASSIVE_DATA_OFFLINE_MAP",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.FSS_PASSIVE_SYSTEM_COMPLETE": TTSPolicySpec(
        message_id="MSG.FSS_PASSIVE_SYSTEM_COMPLETE",
        intent="context",
        category="explore",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.MILESTONE_PROGRESS": TTSPolicySpec(
        message_id="MSG.MILESTONE_PROGRESS",
        intent="context",
        category="route",
    ),
    "MSG.MILESTONE_REACHED": TTSPolicySpec(
        message_id="MSG.MILESTONE_REACHED",
        intent="context",
        category="route",
    ),
    "MSG.STARTUP_SYSTEMS": TTSPolicySpec(
        message_id="MSG.STARTUP_SYSTEMS",
        intent="context",
        category="info",
    ),
    "MSG.CASH_IN_ASSISTANT": TTSPolicySpec(
        message_id="MSG.CASH_IN_ASSISTANT",
        intent="context",
        category="explore",
    ),
    "MSG.EXPLORATION_AWARENESS_SUMMARY": TTSPolicySpec(
        message_id="MSG.EXPLORATION_AWARENESS_SUMMARY",
        intent="context",
        category="explore",
    ),
    "MSG.CASH_IN_STARTJUMP": TTSPolicySpec(
        message_id="MSG.CASH_IN_STARTJUMP",
        intent="context",
        category="explore",
    ),
    "MSG.SURVIVAL_REBUY_HIGH": TTSPolicySpec(
        message_id="MSG.SURVIVAL_REBUY_HIGH",
        intent="context",
        category="alert",
    ),
    "MSG.SURVIVAL_REBUY_CRITICAL": TTSPolicySpec(
        message_id="MSG.SURVIVAL_REBUY_CRITICAL",
        intent="critical",
        category="alert",
        cooldown_policy="ALWAYS_SAY",
    ),
    "MSG.COMBAT_AWARENESS_HIGH": TTSPolicySpec(
        message_id="MSG.COMBAT_AWARENESS_HIGH",
        intent="context",
        category="alert",
    ),
    "MSG.COMBAT_AWARENESS_CRITICAL": TTSPolicySpec(
        message_id="MSG.COMBAT_AWARENESS_CRITICAL",
        intent="critical",
        category="alert",
        cooldown_policy="ALWAYS_SAY",
    ),
    "MSG.HIGH_G_WARNING": TTSPolicySpec(
        message_id="MSG.HIGH_G_WARNING",
        intent="critical",
        category="alert",
        cooldown_policy="BYPASS_GLOBAL",
    ),
    "MSG.TRADE_DATA_STALE": TTSPolicySpec(
        message_id="MSG.TRADE_DATA_STALE",
        intent="context",
        category="info",
    ),
    "MSG.PPM_SET_TARGET": TTSPolicySpec(
        message_id="MSG.PPM_SET_TARGET",
        intent="context",
        category="info",
    ),
    "MSG.PPM_PIN_ACTION": TTSPolicySpec(
        message_id="MSG.PPM_PIN_ACTION",
        intent="context",
        category="info",
    ),
    "MSG.PPM_COPY_SYSTEM": TTSPolicySpec(
        message_id="MSG.PPM_COPY_SYSTEM",
        intent="context",
        category="info",
    ),
    "MSG.RUNTIME_CRITICAL": TTSPolicySpec(
        message_id="MSG.RUNTIME_CRITICAL",
        intent="critical",
        category="alert",
        cooldown_policy="ALWAYS_SAY",
    ),
}


def get_insight_class(message_id: str) -> InsightClassSpec | None:
    return INSIGHT_CLASS_BY_MESSAGE_ID.get(str(message_id or "").strip())


def get_tts_policy_spec(message_id: str) -> TTSPolicySpec:
    msg_id = str(message_id or "").strip()
    policy = TTS_POLICY_BY_MESSAGE_ID.get(msg_id)
    if policy is not None:
        return policy
    return TTSPolicySpec(
        message_id=msg_id or "UNKNOWN_MESSAGE",
        intent="silent",
        category="info",
        cooldown_policy="NORMAL",
    )


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
    tts_policy = get_tts_policy_spec(msg_id)

    if spec is None:
        runtime_ctx.setdefault("canonical_event", str(event_type or "UNKNOWN_EVENT"))
        runtime_ctx.setdefault("insight_class", msg_id or "UNKNOWN_MESSAGE")
        runtime_ctx.setdefault("insight_kind", "general")
        runtime_ctx.setdefault("decision_space", "default")
        runtime_ctx.setdefault("tts_intent", tts_policy.intent)
        runtime_ctx.setdefault("tts_category", tts_policy.category)
        runtime_ctx.setdefault("tts_cooldown_policy", tts_policy.cooldown_policy)
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
    runtime_ctx.setdefault("tts_intent", tts_policy.intent)
    runtime_ctx.setdefault("tts_category", tts_policy.category)
    runtime_ctx.setdefault("tts_cooldown_policy", tts_policy.cooldown_policy)

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
