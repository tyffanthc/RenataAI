from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import config
from app.state import app_state
from logic.insight_dispatcher import emit_insight


@dataclass
class CashInAssistantPayload:
    system: str
    mode: str
    signal: str
    scanned_bodies: int | None
    total_bodies: int | None
    system_value_estimated: float
    session_value_estimated: float
    trust_status: str
    confidence: str
    options: list[dict[str, Any]]
    skip_action: dict[str, str]
    note: str
    signature: str


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _clamp_0_100(value: float) -> int:
    return int(max(0.0, min(100.0, round(value))))


def _trust_score(trust_status: str, confidence: str) -> int:
    trust = _as_text(trust_status).upper()
    confidence_norm = _as_text(confidence).lower()
    if trust == "TRUST_HIGH":
        base = 86
    elif trust == "TRUST_MEDIUM":
        base = 66
    elif trust == "TRUST_LOW":
        base = 44
    else:
        base = 58

    if confidence_norm == "high":
        base += 8
    elif confidence_norm == "low":
        base -= 12
    return _clamp_0_100(base)


def _cash_signal_from_values(system_value: float, session_value: float) -> str:
    top = max(system_value, session_value)
    if top >= 15_000_000:
        return "wysoki"
    if top >= 3_000_000:
        return "sredni"
    return "niski"


def _risk_label(score: int) -> str:
    if score >= 75:
        return "Niskie"
    if score >= 50:
        return "Srednie"
    return "Wysokie"


def _trust_label(score: int) -> str:
    if score >= 75:
        return "Wysoki"
    if score >= 50:
        return "Sredni"
    return "Niski"


def _score_overall(*, time_score: int, profit_score: int, risk_score: int, trust_score: int) -> int:
    return _clamp_0_100(
        (time_score * 0.25)
        + (profit_score * 0.30)
        + (risk_score * 0.25)
        + (trust_score * 0.20)
    )


def _format_cr(value: float) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except Exception:
        return "0"


def _build_options(
    *,
    signal: str,
    system_value: float,
    session_value: float,
    trust_status: str,
    confidence: str,
    scanned_bodies: int | None,
    total_bodies: int | None,
) -> list[dict[str, Any]]:
    trust_score = _trust_score(trust_status, confidence)
    remaining = 0
    if scanned_bodies is not None and total_bodies is not None and total_bodies > scanned_bodies:
        remaining = max(0, int(total_bodies - scanned_bodies))
    remaining_ratio = 0.0
    if total_bodies and total_bodies > 0:
        remaining_ratio = max(0.0, min(1.0, float(remaining) / float(total_bodies)))

    potential_gain = max(0.0, system_value * remaining_ratio * 0.60)
    session_high = session_value >= 20_000_000
    session_mid = session_value >= 8_000_000
    signal_norm = _as_text(signal).lower()

    profit_now = 84 if signal_norm == "wysoki" else 70 if signal_norm == "sredni" else 58
    if session_high:
        profit_now = min(95, profit_now + 6)

    option_now = {
        "option_id": "cash_in_now",
        "label": "Rozwaz cash-in teraz",
        "strategy": "secure_now",
        "estimated_value": int(round(session_value)),
        "eta_minutes": 18,
        "risk_label": _risk_label(92 if session_high else 82 if session_mid else 72),
        "trust_label": _trust_label(trust_score),
        "scores": {
            "time_score": 92,
            "profit_score": profit_now,
            "risk_score": 92 if session_high else 82 if session_mid else 72,
            "trust_score": trust_score,
        },
        "reasoning": {
            "time_text": "najszybsze domkniecie ryzyka",
            "profit_text": f"zabezpiecza ok. {_format_cr(session_value)} Cr",
            "risk_text": "maleje ekspozycja na utrate danych",
            "trust_text": _trust_label(trust_score),
        },
    }
    option_now["scores"]["overall_score"] = _score_overall(
        time_score=option_now["scores"]["time_score"],
        profit_score=option_now["scores"]["profit_score"],
        risk_score=option_now["scores"]["risk_score"],
        trust_score=option_now["scores"]["trust_score"],
    )

    options: list[dict[str, Any]] = [option_now]

    if remaining > 0:
        profit_finish = 76 if potential_gain >= 1_500_000 else 66
        option_finish = {
            "option_id": "cash_in_finish_system",
            "label": "Rozwaz domkniecie systemu i cash-in pozniej",
            "strategy": "finish_then_cash_in",
            "estimated_value": int(round(session_value + potential_gain)),
            "eta_minutes": int(40 + min(35, remaining * 3)),
            "risk_label": _risk_label(58 if session_high else 68),
            "trust_label": _trust_label(trust_score),
            "scores": {
                "time_score": 62,
                "profit_score": profit_finish,
                "risk_score": 58 if session_high else 68,
                "trust_score": trust_score,
            },
            "reasoning": {
                "time_text": f"wymaga domkniecia ok. {remaining} obiektow",
                "profit_text": f"potencjalnie +{_format_cr(potential_gain)} Cr",
                "risk_text": "umiarkowany wzrost ekspozycji czasowej",
                "trust_text": _trust_label(trust_score),
            },
        }
        option_finish["scores"]["overall_score"] = _score_overall(
            time_score=option_finish["scores"]["time_score"],
            profit_score=option_finish["scores"]["profit_score"],
            risk_score=option_finish["scores"]["risk_score"],
            trust_score=option_finish["scores"]["trust_score"],
        )
        options.append(option_finish)

    option_later = {
        "option_id": "cash_in_later",
        "label": "Rozwaz dalsza eksploracje przed cash-in",
        "strategy": "continue_then_cash_in",
        "estimated_value": int(round(session_value + max(system_value * 0.4, 500_000.0))),
        "eta_minutes": 75,
        "risk_label": _risk_label(46 if session_high else 56 if session_mid else 64),
        "trust_label": _trust_label(trust_score),
        "scores": {
            "time_score": 38,
            "profit_score": 66 if signal_norm != "niski" else 72,
            "risk_score": 46 if session_high else 56 if session_mid else 64,
            "trust_score": trust_score,
        },
        "reasoning": {
            "time_text": "najdluzszy horyzont decyzji",
            "profit_text": "wyzszy potencjal, ale niepewny",
            "risk_text": "najwieksza ekspozycja czasowa",
            "trust_text": _trust_label(trust_score),
        },
    }
    option_later["scores"]["overall_score"] = _score_overall(
        time_score=option_later["scores"]["time_score"],
        profit_score=option_later["scores"]["profit_score"],
        risk_score=option_later["scores"]["risk_score"],
        trust_score=option_later["scores"]["trust_score"],
    )
    options.append(option_later)

    if len(options) < 2:
        fallback = dict(option_now)
        fallback["option_id"] = "cash_in_after_short_leg"
        fallback["label"] = "Rozwaz cash-in po 1-2 skokach"
        fallback["strategy"] = "short_delay"
        fallback["eta_minutes"] = 35
        fallback["scores"] = dict(option_now["scores"])
        fallback["scores"]["time_score"] = 74
        fallback["scores"]["risk_score"] = 66
        fallback["scores"]["overall_score"] = _score_overall(
            time_score=fallback["scores"]["time_score"],
            profit_score=fallback["scores"]["profit_score"],
            risk_score=fallback["scores"]["risk_score"],
            trust_score=fallback["scores"]["trust_score"],
        )
        options.append(fallback)

    if len(options) > 3:
        options = options[:3]
    return options


def _signature(payload: CashInAssistantPayload) -> str:
    return (
        f"{payload.system}:{int(round(payload.system_value_estimated))}:"
        f"{int(round(payload.session_value_estimated))}:{payload.signal}:"
        f"{payload.scanned_bodies or 'na'}/{payload.total_bodies or 'na'}:"
        f"{payload.trust_status}:{payload.confidence}"
    )


def _build_tts_line(payload: CashInAssistantPayload) -> str:
    count = len(payload.options or [])
    if count >= 3:
        return "Cash-in: mam trzy opcje w panelu. Rozwaz teraz, po domknieciu systemu albo pozniej."
    if count == 2:
        return "Cash-in: mam dwie opcje w panelu. Rozwaz teraz albo pozniej."
    return "Cash-in: sprawdz opcje w panelu i zdecyduj."


def trigger_cash_in_assistant(
    *,
    gui_ref=None,
    mode: str = "auto",
    summary_payload: dict[str, Any] | None = None,
) -> bool:
    if not bool(config.get("cash_in_assistant_enabled", True)):
        return False

    mode_norm = _as_text(mode).lower() or "auto"
    raw = dict(summary_payload or {})

    system = _as_text(raw.get("system")) or _as_text(getattr(app_state, "current_system", "")) or "unknown"
    scanned = _safe_int(raw.get("scanned_bodies"))
    total = _safe_int(raw.get("total_bodies"))
    system_value = _safe_float(raw.get("cash_in_system_estimated"))
    session_value = _safe_float(raw.get("cash_in_session_estimated"))
    signal = _as_text(raw.get("cash_in_signal")).lower() or _cash_signal_from_values(system_value, session_value)
    trust_status = _as_text(raw.get("trust_status")).upper() or "TRUST_HIGH"
    confidence = _as_text(raw.get("confidence")).lower() or "mid"

    options = _build_options(
        signal=signal,
        system_value=system_value,
        session_value=session_value,
        trust_status=trust_status,
        confidence=confidence,
        scanned_bodies=scanned,
        total_bodies=total,
    )

    payload = CashInAssistantPayload(
        system=system,
        mode=mode_norm,
        signal=signal,
        scanned_bodies=scanned,
        total_bodies=total,
        system_value_estimated=system_value,
        session_value_estimated=session_value,
        trust_status=trust_status,
        confidence=confidence,
        options=options,
        skip_action={"id": "skip", "label": "Pomijam"},
        note="To jest rekomendacja orientacyjna. Ostateczna decyzja nalezy do Ciebie.",
        signature="",
    )
    payload.signature = _signature(payload)

    if mode_norm == "auto":
        last_sig = _as_text(getattr(app_state, "last_cash_in_signature", ""))
        skip_sig = _as_text(getattr(app_state, "cash_in_skip_signature", ""))
        if payload.signature == last_sig:
            return False
        if skip_sig and payload.signature == skip_sig:
            return False
        app_state.last_cash_in_signature = payload.signature

    risk_status = "RISK_MEDIUM" if signal == "wysoki" else "RISK_LOW"
    var_status = "VAR_HIGH" if signal == "wysoki" else "VAR_MEDIUM" if signal == "sredni" else "VAR_LOW"

    context = {
        "system": payload.system,
        "raw_text": _build_tts_line(payload),
        "risk_status": risk_status,
        "var_status": var_status,
        "trust_status": payload.trust_status,
        "confidence": payload.confidence,
        "cash_in_payload": asdict(payload),
    }

    dedup_key = (
        f"cash_in_manual:{payload.system}:{payload.signature}"
        if mode_norm == "manual"
        else f"cash_in_auto:{payload.system}:{payload.signature}"
    )
    cooldown_seconds = 0.0 if mode_norm == "manual" else 90.0

    emit_insight(
        context["raw_text"],
        gui_ref=gui_ref,
        message_id="MSG.CASH_IN_ASSISTANT",
        source="cash_in_assistant",
        event_type="CASH_IN_REVIEW",
        context=context,
        priority="P2_NORMAL",
        dedup_key=dedup_key,
        cooldown_scope="entity",
        cooldown_seconds=cooldown_seconds,
    )
    return True

