from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import config
from app.state import app_state
from logic.exit_summary import ExitSummaryData, format_credits
from logic.insight_dispatcher import emit_insight


@dataclass
class ExplorationSummaryPayload:
    system: str
    scanned_bodies: int | None
    total_bodies: int | None
    highlights: list[str]
    next_step: str
    cash_in_signal: str
    cash_in_system_estimated: float
    cash_in_session_estimated: float
    confidence: str
    mode: str
    signature: str


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _build_highlights(data: ExitSummaryData) -> list[str]:
    highlights: list[str] = []

    if data.elw_count > 0:
        highlights.append(f"ELW: {data.elw_count} ({format_credits(data.elw_value)})")
    if data.ww_t_count > 0:
        highlights.append(f"WW terraformowalne: {data.ww_t_count} ({format_credits(data.ww_t_value)})")
    if data.hmc_t_count > 0:
        highlights.append(f"HMC terraformowalne: {data.hmc_t_count} ({format_credits(data.hmc_t_value)})")
    if data.biology_species_count > 0:
        highlights.append(
            f"Biologia: {data.biology_species_count} gat. ({format_credits(data.biology_value)})"
        )
    if data.bonus_discovery > 0:
        highlights.append(f"Bonusy first: {format_credits(data.bonus_discovery)}")

    if (
        data.scanned_bodies is not None
        and data.total_bodies is not None
        and data.total_bodies > data.scanned_bodies
    ):
        remaining = max(0, int(data.total_bodies - data.scanned_bodies))
        highlights.append(f"Do dokończenia FSS: {remaining}")

    return highlights[:5]


def _pick_next_step(data: ExitSummaryData) -> str:
    if (
        data.scanned_bodies is not None
        and data.total_bodies is not None
        and data.total_bodies > data.scanned_bodies
    ):
        return "Dokończ FSS"
    if data.elw_count + data.ww_count + data.hmc_t_count > 0:
        return "Rozważ DSS na top celach"
    if data.biology_species_count > 0:
        return "Rozważ lądowanie pod exobio"
    return "Leć dalej"


def _confidence_for_payload(data: ExitSummaryData) -> str:
    if data.total_value > 0:
        return "mid"
    return "low"


def _cash_in_signal(data: ExitSummaryData) -> str:
    total = _safe_float(data.total_value)
    if total >= 15_000_000:
        return "wysoki"
    if total >= 3_000_000:
        return "średni"
    return "niski"


def _signature_from_payload(payload: ExplorationSummaryPayload) -> str:
    highlights = "|".join(payload.highlights)
    scanned = payload.scanned_bodies if payload.scanned_bodies is not None else "na"
    total = payload.total_bodies if payload.total_bodies is not None else "na"
    system_value = int(round(payload.cash_in_system_estimated))
    return f"{payload.system}:{scanned}/{total}:{system_value}:{payload.next_step}:{highlights}"


def _build_payload(
    *,
    data: ExitSummaryData,
    mode: str,
) -> ExplorationSummaryPayload:
    try:
        totals = app_state.system_value_engine.calculate_totals()
    except Exception:
        totals = {"total": 0.0}

    highlights = _build_highlights(data)
    next_step = _pick_next_step(data)
    cash_signal = _cash_in_signal(data)
    confidence = _confidence_for_payload(data)

    payload = ExplorationSummaryPayload(
        system=_as_text(data.system_name) or "unknown",
        scanned_bodies=data.scanned_bodies,
        total_bodies=data.total_bodies,
        highlights=highlights,
        next_step=next_step,
        cash_in_signal=cash_signal,
        cash_in_system_estimated=_safe_float(data.total_value),
        cash_in_session_estimated=_safe_float((totals or {}).get("total")),
        confidence=confidence,
        mode=_as_text(mode) or "auto",
        signature="",
    )
    payload.signature = _signature_from_payload(payload)
    return payload


def _build_tts_line(payload: ExplorationSummaryPayload) -> str:
    value = _safe_float(payload.cash_in_session_estimated)
    if value <= 0.0:
        value = _safe_float(payload.cash_in_system_estimated)
    return (
        "Podsumowanie gotowe. "
        f"Dane warte {format_credits(value)}. "
        f"{payload.next_step}."
    )


def trigger_exploration_summary(
    *,
    gui_ref=None,
    mode: str = "auto",
    system_name: str | None = None,
    scanned_bodies: int | None = None,
    total_bodies: int | None = None,
) -> bool:
    """
    Build and emit exploration summary through dispatcher.

    mode:
    - "auto": emit only when summary signature changes,
    - "manual": always attempt emit (still guarded by dispatcher policies).
    """
    if not bool(config.get("exit_summary_enabled", True)):
        return False

    system = _as_text(system_name) or _as_text(getattr(app_state, "current_system", "")) or "unknown"

    try:
        data = app_state.exit_summary.build_summary_data(
            system_name=system,
            scanned_bodies=scanned_bodies,
            total_bodies=total_bodies,
        )
    except Exception:
        data = None

    if data is None:
        return False

    payload = _build_payload(data=data, mode=mode)
    previous_signature = _as_text(getattr(app_state, "last_exploration_summary_signature", ""))

    mode_norm = _as_text(mode).lower() or "auto"
    if mode_norm == "auto" and payload.signature == previous_signature:
        return False

    app_state.last_exploration_summary_signature = payload.signature

    tts_enabled = bool(config.get("voice_exit_summary", True))
    raw_text = _build_tts_line(payload) if tts_enabled else "Podsumowanie eksploracji gotowe w panelu."
    context = {
        "system": payload.system,
        "raw_text": raw_text,
        "confidence": payload.confidence,
        "risk_status": "RISK_LOW",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "summary_payload": asdict(payload),
        "summary_mode": payload.mode,
    }

    cooldown_seconds = 0.0 if mode_norm == "manual" else 45.0
    dedup_key = (
        f"exp_summary_manual:{payload.system}:{payload.signature}"
        if mode_norm == "manual"
        else f"exp_summary_auto:{payload.system}:{payload.signature}"
    )

    emit_insight(
        raw_text,
        gui_ref=gui_ref,
        message_id="MSG.EXPLORATION_SYSTEM_SUMMARY",
        source="exploration_summary",
        event_type="SYSTEM_SUMMARY",
        context=context,
        priority="P3_LOW",
        dedup_key=dedup_key,
        cooldown_scope="entity",
        cooldown_seconds=cooldown_seconds,
    )
    try:
        from logic.events.cash_in_assistant import trigger_cash_in_assistant

        trigger_cash_in_assistant(
            gui_ref=gui_ref,
            mode=mode_norm,
            summary_payload=asdict(payload),
        )
    except Exception:
        pass
    return True
