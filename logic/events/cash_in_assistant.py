from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import time
from typing import Any

import config
from app.state import app_state
from logic.cash_in_station_candidates import (
    build_station_candidates,
    filter_candidates_by_service,
    station_candidates_from_playerdb,
    station_candidates_from_offline_index,
    station_candidates_cross_system_from_providers,
    station_candidates_for_system_from_providers,
)
from logic.insight_dispatcher import emit_insight
from logic.utils.http_edsm import edsm_provider_resilience_snapshot
from logic.utils import DEBOUNCER


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
    service: str = "uc"
    payout_contract: dict[str, Any] = field(default_factory=dict)
    station_candidates: list[dict[str, Any]] = field(default_factory=list)
    station_candidates_meta: dict[str, Any] = field(default_factory=dict)
    ranking_meta: dict[str, Any] = field(default_factory=dict)
    edge_case_meta: dict[str, Any] = field(default_factory=dict)


_CASH_IN_SWR_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CASH_IN_LOCAL_KNOWN_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _reset_cash_in_swr_cache_for_tests() -> None:
    _CASH_IN_SWR_CACHE.clear()


def _reset_cash_in_local_known_cache_for_tests() -> None:
    _CASH_IN_LOCAL_KNOWN_CACHE.clear()


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


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return float(value)
        except Exception:
            return None
    text = _as_text(value).replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _safe_optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except Exception:
        return None


def _normalize_vista_fc_policy_mode(value: Any) -> str:
    mode = _as_text(value).upper()
    if mode == "UNKNOWN":
        return "UNKNOWN"
    return "ASSUMED_100"


def _target_type_normalized(value: Any) -> str:
    target = _as_text(value).lower()
    if target in {"carrier", "fleet_carrier", "fleetcarrier"}:
        return "fleet_carrier"
    return "non_carrier"


def _ui_target_type_label(value: Any) -> str:
    target = _target_type_normalized(value)
    if target == "fleet_carrier":
        return "carrier"
    return "non-carrier"


def _build_breakdown(*, gross_value: float, payout_ratio: float) -> dict[str, int]:
    gross = int(round(max(0.0, float(gross_value or 0.0))))
    ratio = max(0.0, min(1.0, float(payout_ratio)))
    net = int(round(float(gross) * ratio))
    fee = max(0, gross - net)
    return {
        "brutto": gross,
        "fee": fee,
        "netto": net,
    }


def _build_single_payout_contract(
    *,
    service: str,
    target_type: str,
    gross_value: float,
    tariff_percent: float | None,
    vista_fc_policy_mode: str,
    freshness_ts: str,
) -> dict[str, Any]:
    svc = _as_text(service).upper() or "UC"
    target = _target_type_normalized(target_type)
    tariff_meta = {
        "tariff_percent": tariff_percent,
        "available": tariff_percent is not None,
        "applies_to_payout": False,
        "note": "Tariff % jest meta-info i nie zmienia payout UC w MVP.",
    }

    status = "CONFIRMED"
    assumption = False
    fallback_applied = False
    policy_source = "MVP_POLICY"
    fee_note = ""

    if svc == "UC":
        payout_ratio = 0.75 if target == "fleet_carrier" else 1.0
        if target == "fleet_carrier":
            fee_note = "UC fee 25% (fixed on carriers)"
    else:
        # Vista policy: non-carrier confirmed 100%, FC assumption/unknown with fallback ASSUMED_100.
        if target == "fleet_carrier":
            payout_ratio = 1.0
            if vista_fc_policy_mode == "UNKNOWN":
                status = "UNKNOWN"
                fallback_applied = True
                assumption = True
                policy_source = "UNKNOWN_FALLBACK_ASSUMED_100"
                fee_note = "Vista payout unknown; applied ASSUMED_100 fallback."
            else:
                status = "ASSUMED_100"
                assumption = True
                policy_source = "ASSUMED_100_NEEDS_REVALIDATION"
                fee_note = "Vista payout on FC is assumption (needs revalidation)."
        else:
            payout_ratio = 1.0

    breakdown = _build_breakdown(gross_value=gross_value, payout_ratio=payout_ratio)
    return {
        "service": svc,
        "target_type": target,
        "status": status,
        "assumption": assumption,
        "fallback_applied": fallback_applied,
        "policy_source": policy_source,
        "payout_ratio": payout_ratio,
        "fee_note": fee_note,
        "freshness_ts": freshness_ts,
        "tariff_meta": tariff_meta,
        **breakdown,
    }


def _build_payout_contract(
    *,
    gross_value: float,
    tariff_percent: float | None,
    vista_fc_policy_mode: str,
    freshness_ts: str,
) -> dict[str, Any]:
    uc_non_carrier = _build_single_payout_contract(
        service="UC",
        target_type="non_carrier",
        gross_value=gross_value,
        tariff_percent=tariff_percent,
        vista_fc_policy_mode=vista_fc_policy_mode,
        freshness_ts=freshness_ts,
    )
    uc_fleet_carrier = _build_single_payout_contract(
        service="UC",
        target_type="fleet_carrier",
        gross_value=gross_value,
        tariff_percent=tariff_percent,
        vista_fc_policy_mode=vista_fc_policy_mode,
        freshness_ts=freshness_ts,
    )
    vista_non_carrier = _build_single_payout_contract(
        service="VISTA",
        target_type="non_carrier",
        gross_value=gross_value,
        tariff_percent=tariff_percent,
        vista_fc_policy_mode=vista_fc_policy_mode,
        freshness_ts=freshness_ts,
    )
    vista_fleet_carrier = _build_single_payout_contract(
        service="VISTA",
        target_type="fleet_carrier",
        gross_value=gross_value,
        tariff_percent=tariff_percent,
        vista_fc_policy_mode=vista_fc_policy_mode,
        freshness_ts=freshness_ts,
    )

    # Runtime default preview: UC non-carrier (safe baseline in current F4/F11 flow).
    return {
        "brutto": uc_non_carrier["brutto"],
        "fee": uc_non_carrier["fee"],
        "netto": uc_non_carrier["netto"],
        "reference_service": "UC",
        "reference_target_type": "non_carrier",
        "vista_fc_policy_mode": vista_fc_policy_mode,
        "tariff_meta": dict(uc_non_carrier.get("tariff_meta") or {}),
        "contracts": {
            "uc_non_carrier": uc_non_carrier,
            "uc_fleet_carrier": uc_fleet_carrier,
            "vista_non_carrier": vista_non_carrier,
            "vista_fleet_carrier": vista_fleet_carrier,
        },
    }


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


def _option_has_target(option: dict[str, Any] | None) -> bool:
    payload = option if isinstance(option, dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    target_system = _as_text(
        target.get("system_name")
        or target.get("system")
        or payload.get("target_system")
        or payload.get("system")
    )
    if target_system:
        return True

    ui = payload.get("ui_contract") if isinstance(payload.get("ui_contract"), dict) else {}
    ui_target = ui.get("target") if isinstance(ui.get("target"), dict) else {}
    return bool(_as_text(ui_target.get("system")))


def _option_has_real_target(option: dict[str, Any] | None) -> bool:
    payload = option if isinstance(option, dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    ui = payload.get("ui_contract") if isinstance(payload.get("ui_contract"), dict) else {}
    ui_target = ui.get("target") if isinstance(ui.get("target"), dict) else {}

    target_system = _as_text(
        target.get("system_name")
        or target.get("system")
        or payload.get("target_system")
        or payload.get("system")
        or ui_target.get("system")
    )
    target_station = _as_text(
        target.get("name")
        or payload.get("target_station")
        or payload.get("station")
        or ui_target.get("name")
    )
    if not target_system or not target_station:
        return False
    if bool(payload.get("fallback_target_attached")):
        return False
    return True


def _pick_fallback_station_candidate(
    *,
    candidates: list[dict[str, Any]],
    service: str,
) -> dict[str, Any] | None:
    rows = [dict(item) for item in candidates if isinstance(item, dict)]
    if not rows:
        return None

    service_norm = _normalize_cash_in_service(service)
    if service_norm == "uc":
        # Dla UC preferujemy non-carrier, gdy brakuje pelnego pokrycia uslug.
        rows.sort(
            key=lambda row: (
                1 if _candidate_is_carrier(row) else 0,
                _candidate_distance_ly(row),
                _candidate_distance_ls(row),
                _candidate_name(row).casefold(),
            )
        )
    else:
        rows.sort(
            key=lambda row: (
                _candidate_distance_ly(row),
                _candidate_distance_ls(row),
                _candidate_name(row).casefold(),
            )
        )

    for row in rows:
        if _as_text(row.get("system_name")):
            return row
    return None


def _attach_fallback_target_to_options(
    options: list[dict[str, Any]],
    *,
    station_candidates: list[dict[str, Any]],
    service: str,
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in options if isinstance(item, dict)]
    if not rows:
        return []

    if all(_option_has_target(item) for item in rows):
        return rows

    fallback_candidate = _pick_fallback_station_candidate(
        candidates=station_candidates,
        service=service,
    )
    if not isinstance(fallback_candidate, dict):
        return rows

    target_system = _as_text(fallback_candidate.get("system_name"))
    if not target_system:
        return rows

    target_name = _as_text(fallback_candidate.get("name"))
    target_type = _as_text(fallback_candidate.get("type")) or "station"
    target_source = _as_text(fallback_candidate.get("source"))
    target_freshness = _as_text(fallback_candidate.get("freshness_ts"))
    target_distance_ly = _safe_optional_float(fallback_candidate.get("distance_ly"))
    target_distance_ls = _safe_optional_float(fallback_candidate.get("distance_ls"))

    enriched: list[dict[str, Any]] = []
    for raw in rows:
        item = dict(raw)
        if _option_has_target(item):
            enriched.append(item)
            continue

        existing_target = item.get("target") if isinstance(item.get("target"), dict) else {}
        target_payload = dict(existing_target)
        target_payload.setdefault("name", target_name)
        target_payload.setdefault("system_name", target_system)
        target_payload.setdefault("type", target_type)
        if target_distance_ly is not None:
            target_payload.setdefault("distance_ly", target_distance_ly)
        if target_distance_ls is not None:
            target_payload.setdefault("distance_ls", target_distance_ls)
        if target_source:
            target_payload.setdefault("source", target_source)
        if target_freshness:
            target_payload.setdefault("freshness_ts", target_freshness)

        item["target"] = target_payload
        item["target_system"] = target_system
        if target_name:
            item["target_station"] = target_name
        if target_type:
            item["target_type"] = target_type
        item["fallback_target_attached"] = True
        item["fallback_target_reason"] = "station_candidates_without_service_match"
        enriched.append(item)
    return enriched


def _infer_profile_for_option(option: dict[str, Any]) -> str:
    profile = _as_text(option.get("profile")).upper()
    if profile in {"SAFE", "FAST", "SECURE"}:
        return profile
    option_id = _as_text(option.get("option_id")).lower()
    strategy = _as_text(option.get("strategy")).lower()
    combined = f"{option_id}:{strategy}"
    if "now" in combined or "secure" in combined:
        return "SECURE"
    if "later" in combined or "fast" in combined:
        return "FAST"
    return "SAFE"


def _build_ui_contract_for_option(option: dict[str, Any]) -> dict[str, Any]:
    profile = _infer_profile_for_option(option)
    target = dict(option.get("target") or {})
    target_name = _as_text(target.get("name") or option.get("target_station"))
    target_system = _as_text(
        target.get("system_name")
        or option.get("target_system")
        or option.get("system")
    )
    target_type = _as_text(target.get("type") or option.get("target_type") or "station")
    target_kind = _ui_target_type_label(target_type)

    target_display = target_system
    if target_name and target_system:
        target_display = f"{target_name} ({target_system})"
    elif target_name:
        target_display = target_name

    payout_raw = dict(option.get("payout") or {})
    brutto = _safe_optional_int(payout_raw.get("brutto"))
    fee = _safe_optional_int(payout_raw.get("fee"))
    netto = _safe_optional_int(
        payout_raw.get("netto")
        if payout_raw.get("netto") is not None
        else option.get("estimated_value")
    )
    payout_unknown = any(item is None for item in (brutto, fee, netto))
    payout_status = _as_text(payout_raw.get("status")) or ("UNKNOWN" if payout_unknown else "CONFIRMED")
    payout_assumption = bool(payout_raw.get("assumption"))
    payout_freshness = _as_text(payout_raw.get("freshness_ts") or target.get("freshness_ts"))
    tariff_meta = dict(payout_raw.get("tariff_meta") or {})
    tariff_percent = _safe_optional_float(tariff_meta.get("tariff_percent"))
    show_tariff_meta = bool(config.get("cash_in.show_tariff_meta", True))
    assumption_label = ""
    if payout_assumption or payout_status in {"ASSUMED_100", "UNKNOWN"}:
        assumption_label = "assumption"

    reasoning = dict(option.get("reasoning") or {})
    risk_reason = _as_text(reasoning.get("risk_text"))
    if not risk_reason and (option.get("warnings") or []):
        risk_reason = ",".join(str(item) for item in (option.get("warnings") or []))
    why_parts = [
        _as_text(reasoning.get("time_text")),
        _as_text(reasoning.get("profit_text")),
        _as_text(reasoning.get("risk_text")),
    ]
    why = " | ".join(part for part in why_parts if part)

    risk_tier = _as_text(option.get("risk_label")).upper() or "UNKNOWN"
    eta_minutes = _safe_optional_int(option.get("eta_minutes"))
    return {
        "label": profile,
        "target": {
            "name": target_name,
            "system": target_system,
            "kind": target_kind,
            "display": target_display or "-",
        },
        "payout": {
            "brutto": brutto,
            "fee": fee,
            "netto": netto,
            "unknown": payout_unknown,
            "status": payout_status,
            "assumption": payout_assumption,
            "assumption_label": assumption_label,
            "freshness_ts": payout_freshness,
            "fee_note": _as_text(payout_raw.get("fee_note")),
            "tariff_meta": {
                "show": show_tariff_meta,
                "available": bool(tariff_meta.get("available")),
                "percent": tariff_percent,
                "applies_to_payout": bool(tariff_meta.get("applies_to_payout")),
                "note": _as_text(tariff_meta.get("note")),
            },
        },
        "eta": {
            "minutes": eta_minutes,
            "text": "-" if eta_minutes is None else f"{eta_minutes} min",
        },
        "risk": {
            "tier": risk_tier,
            "reason": risk_reason,
        },
        "why": why,
        "actions": ["set_route", "copy_next_hop", "skip"],
    }


def _apply_ui_transparency_contract(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in options or []:
        if not isinstance(raw, dict):
            continue
        option = dict(raw)
        option["profile"] = _infer_profile_for_option(option)
        option["ui_contract_version"] = "F11_UI_V1"
        option["ui_contract"] = _build_ui_contract_for_option(option)
        normalized.append(option)
    return normalized


def _normalize_cash_in_service(value: Any) -> str:
    svc = _as_text(value).lower()
    if svc in {"vista", "exobio", "exobiology", "genomics"}:
        return "vista"
    return "uc"


def _candidate_is_carrier(candidate: dict[str, Any]) -> bool:
    return _target_type_normalized(candidate.get("type")) == "fleet_carrier"


def _candidate_name(candidate: dict[str, Any]) -> str:
    return _as_text(candidate.get("name")) or "Unknown Station"


def _candidate_system(candidate: dict[str, Any]) -> str:
    return _as_text(candidate.get("system_name")) or "unknown"


def _candidate_distance_ly(candidate: dict[str, Any]) -> float:
    value = _safe_optional_float(candidate.get("distance_ly"))
    if value is None:
        return 1e12
    return max(0.0, value)


def _candidate_distance_ls(candidate: dict[str, Any]) -> float:
    value = _safe_optional_float(candidate.get("distance_ls"))
    if value is None:
        return 1e12
    return max(0.0, value)


def _is_hutton_guard(candidate: dict[str, Any], *, threshold_ls: float) -> bool:
    distance_ls = _safe_optional_float(candidate.get("distance_ls"))
    if distance_ls is None:
        return False
    return distance_ls >= max(0.0, float(threshold_ls))


def _candidate_sort_key(
    candidate: dict[str, Any],
    *,
    profile: str,
    service: str,
    avoid_carriers_for_uc: bool,
    carrier_ok_for_fast_mode: bool,
    hutton_threshold_ls: float,
) -> tuple[float, float, float, float, str]:
    is_carrier = _candidate_is_carrier(candidate)
    hutton_guard = _is_hutton_guard(candidate, threshold_ls=hutton_threshold_ls)
    dist_ly = _candidate_distance_ly(candidate)
    dist_ls = _candidate_distance_ls(candidate)
    name_key = _candidate_name(candidate).casefold()

    carrier_penalty = 0.0
    hutton_penalty = 1.0 if hutton_guard else 0.0

    if profile == "SAFE":
        if service == "uc" and is_carrier:
            carrier_penalty += 1.0
            if avoid_carriers_for_uc:
                carrier_penalty += 2.0
        return (carrier_penalty, hutton_penalty, dist_ly, dist_ls, name_key)

    if profile == "FAST":
        if service == "uc" and is_carrier and not carrier_ok_for_fast_mode:
            carrier_penalty += 2.0
        return (carrier_penalty, dist_ly, hutton_penalty, dist_ls, name_key)

    # SECURE fallback path uses SAFE key.
    if service == "uc" and is_carrier:
        carrier_penalty += 1.0
    return (carrier_penalty, hutton_penalty, dist_ly, dist_ls, name_key)


def _resolve_payout_for_candidate(
    *,
    service: str,
    candidate: dict[str, Any],
    payout_contract: dict[str, Any],
) -> dict[str, Any]:
    contracts = dict(payout_contract.get("contracts") or {})
    contract_key = (
        f"{service}_fleet_carrier"
        if _candidate_is_carrier(candidate)
        else f"{service}_non_carrier"
    )
    row = dict(contracts.get(contract_key) or {})
    if row:
        return row
    return {
        "service": service.upper(),
        "target_type": "fleet_carrier" if _candidate_is_carrier(candidate) else "non_carrier",
        "status": "UNKNOWN",
        "assumption": True,
        "fallback_applied": False,
        "policy_source": "MISSING_CONTRACT",
        "payout_ratio": 1.0,
        "fee_note": "",
        "freshness_ts": "",
        "tariff_meta": {},
        "brutto": int(round(float(payout_contract.get("brutto") or 0))),
        "fee": int(round(float(payout_contract.get("fee") or 0))),
        "netto": int(round(float(payout_contract.get("netto") or 0))),
    }


def _estimate_eta_minutes(
    *,
    profile: str,
    distance_ly: float | None,
    docked_here: bool = False,
) -> int | None:
    if docked_here and profile == "SECURE":
        return 0
    if distance_ly is None:
        return None
    ly = max(0.0, float(distance_ly))
    factor = 0.42
    if profile == "FAST":
        factor = 0.30
    elif profile == "SAFE":
        factor = 0.45
    return max(2, int(round(ly * factor)) + 2)


def _build_profile_option(
    *,
    profile: str,
    candidate: dict[str, Any],
    service: str,
    trust_score: int,
    payout_contract: dict[str, Any],
    hutton_threshold_ls: float,
    hutton_penalty_score: int,
    secure_fallback_to_safe: bool = False,
    docked_here: bool = False,
) -> dict[str, Any]:
    payout = _resolve_payout_for_candidate(
        service=service,
        candidate=candidate,
        payout_contract=payout_contract,
    )
    dist_ly_raw = _safe_optional_float(candidate.get("distance_ly"))
    eta_minutes = _estimate_eta_minutes(
        profile=profile,
        distance_ly=dist_ly_raw,
        docked_here=docked_here,
    )

    time_score = 55
    if eta_minutes is not None:
        time_score = _clamp_0_100(100 - min(90, eta_minutes * 2))
    if docked_here and profile == "SECURE":
        time_score = 99

    payout_ratio = float(payout.get("payout_ratio") or 1.0)
    profit_score = _clamp_0_100(55 + (payout_ratio * 40.0))
    risk_score = 72
    if profile == "SAFE":
        risk_score = 84
    elif profile == "FAST":
        risk_score = 68
    elif profile == "SECURE":
        risk_score = 90 if docked_here else 78

    hutton_guard = _is_hutton_guard(candidate, threshold_ls=hutton_threshold_ls)
    warnings: list[str] = []
    if hutton_guard:
        risk_score = max(0, risk_score - int(max(0, hutton_penalty_score)))
        warnings.append("distance_ls_high")

    option_id = f"cash_in_{profile.lower()}_{_candidate_name(candidate).lower().replace(' ', '_')[:24]}"
    option = {
        "option_id": option_id,
        "label": f"{profile} -> {_candidate_name(candidate)} ({_candidate_system(candidate)})",
        "strategy": f"{profile.lower()}_station_candidate",
        "profile": profile,
        "service": service,
        "target": {
            "name": _candidate_name(candidate),
            "system_name": _candidate_system(candidate),
            "type": _as_text(candidate.get("type")) or "station",
            "distance_ly": dist_ly_raw,
            "distance_ls": _safe_optional_float(candidate.get("distance_ls")),
            "source": _as_text(candidate.get("source")),
            "freshness_ts": _as_text(candidate.get("freshness_ts")),
        },
        "estimated_value": int(round(float(payout.get("netto") or 0.0))),
        "eta_minutes": eta_minutes,
        "risk_label": _risk_label(risk_score),
        "trust_label": _trust_label(trust_score),
        "payout": {
            "brutto": int(round(float(payout.get("brutto") or 0.0))),
            "fee": int(round(float(payout.get("fee") or 0.0))),
            "netto": int(round(float(payout.get("netto") or 0.0))),
            "status": _as_text(payout.get("status")),
            "assumption": bool(payout.get("assumption")),
            "freshness_ts": _as_text(payout.get("freshness_ts")),
            "fee_note": _as_text(payout.get("fee_note")),
            "tariff_meta": dict(payout.get("tariff_meta") or {}),
        },
        "scores": {
            "time_score": time_score,
            "profit_score": profit_score,
            "risk_score": risk_score,
            "trust_score": trust_score,
        },
        "warnings": warnings,
        "secure_fallback_to_safe": bool(secure_fallback_to_safe),
    }
    option["scores"]["overall_score"] = _score_overall(
        time_score=option["scores"]["time_score"],
        profit_score=option["scores"]["profit_score"],
        risk_score=option["scores"]["risk_score"],
        trust_score=option["scores"]["trust_score"],
    )
    option["reasoning"] = {
        "time_text": (
            "docked i usluga dostepna, cash-in tu i teraz"
            if docked_here and profile == "SECURE"
            else f"ETA ~{eta_minutes} min" if eta_minutes is not None else "ETA nieznane"
        ),
        "profit_text": (
            f"netto {_format_cr(option['estimated_value'])} Cr (brutto {_format_cr(option['payout']['brutto'])})"
        ),
        "risk_text": (
            "Hutton guard: bardzo duzy dystans LS"
            if hutton_guard
            else "profil ryzyka dopasowany do trybu"
        ),
        "trust_text": _trust_label(trust_score),
    }
    return option


def _build_profiled_options(
    *,
    service: str,
    candidates: list[dict[str, Any]],
    payout_contract: dict[str, Any],
    trust_status: str,
    confidence: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    trust_score = _trust_score(trust_status, confidence)
    service_norm = _normalize_cash_in_service(service)
    filtered = filter_candidates_by_service(candidates, service=service_norm)
    if not filtered:
        return [], {
            "enabled": False,
            "reason": "no_service_candidates",
            "service": service_norm,
            "service_candidates_count": 0,
            "service_non_carrier_count": 0,
            "service_carrier_count": 0,
        }

    non_carrier_count = sum(1 for row in filtered if not _candidate_is_carrier(row))
    carrier_count = max(0, len(filtered) - non_carrier_count)

    avoid_carriers_for_uc = bool(config.get("cash_in.avoid_carriers_for_uc", True))
    carrier_ok_for_fast_mode = bool(config.get("cash_in.carrier_ok_for_fast_mode", True))
    hutton_threshold_ls = float(config.get("cash_in.hutton_guard_ls_threshold", 500_000.0) or 500_000.0)
    hutton_penalty_score = int(config.get("cash_in.hutton_guard_score_penalty", 18) or 18)

    docked = bool(getattr(app_state, "is_docked", False))
    current_station = _as_text(getattr(app_state, "current_station", ""))
    current_system = _as_text(getattr(app_state, "current_system", ""))
    secure_candidate: dict[str, Any] | None = None
    secure_fallback = False

    if docked and current_station:
        for candidate in filtered:
            if _candidate_name(candidate).casefold() != current_station.casefold():
                continue
            candidate_system = _candidate_system(candidate)
            if current_system and candidate_system and candidate_system.casefold() != current_system.casefold():
                continue
            secure_candidate = candidate
            break

    safe_sorted = sorted(
        filtered,
        key=lambda row: _candidate_sort_key(
            row,
            profile="SAFE",
            service=service_norm,
            avoid_carriers_for_uc=avoid_carriers_for_uc,
            carrier_ok_for_fast_mode=carrier_ok_for_fast_mode,
            hutton_threshold_ls=hutton_threshold_ls,
        ),
    )
    fast_sorted = sorted(
        filtered,
        key=lambda row: _candidate_sort_key(
            row,
            profile="FAST",
            service=service_norm,
            avoid_carriers_for_uc=avoid_carriers_for_uc,
            carrier_ok_for_fast_mode=carrier_ok_for_fast_mode,
            hutton_threshold_ls=hutton_threshold_ls,
        ),
    )

    safe_candidate = safe_sorted[0] if safe_sorted else None
    fast_candidate = fast_sorted[0] if fast_sorted else None
    if secure_candidate is None:
        secure_candidate = safe_candidate
        secure_fallback = docked and safe_candidate is not None

    options: list[dict[str, Any]] = []
    if secure_candidate is not None:
        options.append(
            _build_profile_option(
                profile="SECURE",
                candidate=secure_candidate,
                service=service_norm,
                trust_score=trust_score,
                payout_contract=payout_contract,
                hutton_threshold_ls=hutton_threshold_ls,
                hutton_penalty_score=hutton_penalty_score,
                secure_fallback_to_safe=secure_fallback,
                docked_here=(not secure_fallback and docked),
            )
        )
    if safe_candidate is not None:
        options.append(
            _build_profile_option(
                profile="SAFE",
                candidate=safe_candidate,
                service=service_norm,
                trust_score=trust_score,
                payout_contract=payout_contract,
                hutton_threshold_ls=hutton_threshold_ls,
                hutton_penalty_score=hutton_penalty_score,
            )
        )
    if fast_candidate is not None:
        options.append(
            _build_profile_option(
                profile="FAST",
                candidate=fast_candidate,
                service=service_norm,
                trust_score=trust_score,
                payout_contract=payout_contract,
                hutton_threshold_ls=hutton_threshold_ls,
                hutton_penalty_score=hutton_penalty_score,
            )
        )

    if len(options) > 3:
        options = options[:3]

    ranking_meta = {
        "enabled": True,
        "service": service_norm,
        "profiles": [str((opt or {}).get("profile") or "") for opt in options],
        "docked": docked,
        "secure_fallback_to_safe": secure_fallback,
        "hard_filter_count": len(filtered),
        "service_candidates_count": len(filtered),
        "service_non_carrier_count": non_carrier_count,
        "service_carrier_count": carrier_count,
        "hutton_guard_threshold_ls": hutton_threshold_ls,
        "avoid_carriers_for_uc": avoid_carriers_for_uc,
        "carrier_ok_for_fast_mode": carrier_ok_for_fast_mode,
    }
    return options, ranking_meta


def resolve_cash_in_option_target(option: dict[str, Any] | None) -> dict[str, str]:
    payload = option if isinstance(option, dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    ui = payload.get("ui_contract") if isinstance(payload.get("ui_contract"), dict) else {}
    ui_target = ui.get("target") if isinstance(ui.get("target"), dict) else {}

    target_system = str(
        target.get("system_name")
        or target.get("system")
        or ui_target.get("system")
        or payload.get("target_system")
        or payload.get("system")
        or ""
    ).strip()
    target_station = str(
        target.get("name")
        or ui_target.get("name")
        or payload.get("target_station")
        or payload.get("station")
        or ""
    ).strip()
    profile = str(payload.get("profile") or "").strip().upper()

    target_display = target_system
    if target_station and target_system:
        target_display = f"{target_system} ({target_station})"
    elif target_station:
        target_display = target_station

    route_profile = "SAFE"
    if profile == "FAST":
        route_profile = "FAST_NEUTRON"
    elif profile == "SECURE":
        route_profile = "SECURE"

    is_real = _option_has_real_target(payload)
    target_quality = "real_target" if is_real else "incomplete_or_placeholder"

    return {
        "target_system": target_system,
        "target_station": target_station,
        "target_display": target_display,
        "profile": profile,
        "route_profile": route_profile,
        "target_is_real": is_real,
        "target_quality": target_quality,
    }


def handoff_cash_in_to_route_intent(
    option: dict[str, Any] | None,
    *,
    set_route_intent: Any,
    source: str = "cash_in.intent",
    allow_auto_route: bool = False,
    persist_route_profile: bool = False,
) -> dict[str, Any]:
    """
    Handoff contract for Cash-In Assistant -> Route Intent.

    Guardrail:
    - this function only sets route intent,
    - auto-route side effects are forbidden.
    """
    if allow_auto_route:
        raise ValueError("AUTO_ROUTE_FORBIDDEN_CASH_IN")

    if not callable(set_route_intent):
        return {
            "ok": False,
            "reason": "intent_setter_missing",
            "target_system": "",
            "target_station": "",
            "target_display": "",
            "profile": "",
            "route_profile": "",
            "snapshot": {},
        }

    target = resolve_cash_in_option_target(option)
    target_system = str(target.get("target_system") or "").strip()
    target_station = str(target.get("target_station") or "").strip()
    target_is_real = bool(target.get("target_is_real"))
    route_profile = str(target.get("route_profile") or "").strip().upper()
    if not target_system:
        return {
            "ok": False,
            "reason": "target_missing_system",
            "target_system": "",
            "target_station": target_station,
            "target_display": str(target.get("target_display") or "").strip(),
            "profile": str(target.get("profile") or "").strip(),
            "route_profile": route_profile,
            "route_profile_persisted": False,
            "snapshot": {},
        }
    if not target_station:
        return {
            "ok": False,
            "reason": "target_missing_station",
            "target_system": target_system,
            "target_station": "",
            "target_display": str(target.get("target_display") or "").strip(),
            "profile": str(target.get("profile") or "").strip(),
            "route_profile": route_profile,
            "route_profile_persisted": False,
            "snapshot": {},
        }
    if not target_is_real:
        return {
            "ok": False,
            "reason": "target_not_real",
            "target_system": target_system,
            "target_station": target_station,
            "target_display": str(target.get("target_display") or "").strip(),
            "profile": str(target.get("profile") or "").strip(),
            "route_profile": route_profile,
            "route_profile_persisted": False,
            "snapshot": {},
        }

    profile_persisted = False
    if persist_route_profile and route_profile:
        try:
            snapshot = set_route_intent(
                target_system,
                source=source,
                route_profile=route_profile,
            ) or {}
            profile_persisted = True
        except TypeError:
            snapshot = set_route_intent(target_system, source=source) or {}
    else:
        snapshot = set_route_intent(target_system, source=source) or {}

    return {
        "ok": True,
        "reason": "intent_set",
        "target_system": target_system,
        "target_station": str(target.get("target_station") or "").strip(),
        "target_display": str(target.get("target_display") or "").strip(),
        "profile": str(target.get("profile") or "").strip(),
        "route_profile": route_profile,
        "route_profile_persisted": profile_persisted,
        "snapshot": snapshot,
    }


def persist_cash_in_route_profile(
    option: dict[str, Any] | None,
    *,
    update_route_awareness: Any,
    source: str = "cash_in.intent.profile",
    enabled: bool | None = None,
) -> dict[str, Any]:
    target = resolve_cash_in_option_target(option)
    route_profile = str(target.get("route_profile") or "").strip().upper()
    is_enabled = bool(
        config.get("cash_in.persist_route_profile_to_route_state", False)
        if enabled is None
        else enabled
    )
    if not is_enabled:
        return {
            "ok": False,
            "reason": "persistence_disabled",
            "route_profile": route_profile,
            "snapshot": {},
        }
    if not callable(update_route_awareness):
        return {
            "ok": False,
            "reason": "awareness_setter_missing",
            "route_profile": route_profile,
            "snapshot": {},
        }
    if not route_profile:
        return {
            "ok": False,
            "reason": "route_profile_missing",
            "route_profile": "",
            "snapshot": {},
        }
    snapshot = update_route_awareness(route_profile=route_profile, source=source) or {}
    return {
        "ok": True,
        "reason": "route_profile_persisted",
        "route_profile": route_profile,
        "snapshot": snapshot,
    }


def _station_candidates_confidence(
    *,
    candidates_count: int,
    uc_count: int,
    vista_count: int,
    source_status: str,
    swr_freshness: str = "",
    offline_index_age_days: int = -1,
    playerdb_query_mode: str = "",
) -> str:
    source = _as_text(source_status).lower()
    freshness = _as_text(swr_freshness).upper()
    playerdb_mode = _as_text(playerdb_query_mode).lower()
    if candidates_count <= 0:
        return "low"
    if source == "local_known_fallback":
        return "low"
    if source == "playerdb":
        if playerdb_mode == "nearest" and (uc_count > 0 or vista_count > 0):
            return "high"
        return "mid" if (uc_count > 0 or vista_count > 0) else "low"
    if source == "offline_index":
        if offline_index_age_days < 0:
            return "low"
        med_limit = int(config.get("cash_in.offline_index_confidence_med_age_days", 30) or 30)
        return "mid" if int(offline_index_age_days) <= max(0, med_limit) else "low"
    base = "low"
    if source.startswith("providers") and (uc_count > 0 or vista_count > 0):
        base = "high"
    elif uc_count > 0 or vista_count > 0:
        base = "mid"
    if freshness == "STALE":
        return "mid" if base == "high" else "low"
    if freshness == "EXPIRED":
        return "low"
    return base


def _resolve_offline_index_path() -> str:
    raw = _as_text(config.get("cash_in.offline_index_path", ""))
    if not raw:
        return ""
    if os.path.isabs(raw):
        return raw
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if appdata:
        appdata_candidates = [
            os.path.join(appdata, "RenataAI", "data", "cash_in", raw),
            os.path.join(appdata, "RenataAI", "data", raw),
        ]
        for candidate in appdata_candidates:
            if os.path.isfile(candidate):
                return candidate
    return os.path.abspath(os.path.join(config.BASE_DIR, raw))


def _swr_cache_ttls() -> tuple[float, float]:
    fresh_raw = config.get("cash_in.swr_cache_fresh_ttl_sec", 900.0)
    stale_raw = config.get("cash_in.swr_cache_stale_ttl_sec", 21600.0)
    try:
        fresh_ttl = float(900.0 if fresh_raw is None else fresh_raw)
    except Exception:
        fresh_ttl = 900.0
    try:
        stale_ttl = float(21600.0 if stale_raw is None else stale_raw)
    except Exception:
        stale_ttl = 21600.0
    fresh_ttl = max(0.0, fresh_ttl)
    stale_ttl = max(fresh_ttl, stale_ttl)
    return fresh_ttl, stale_ttl


def _swr_cache_max_items() -> int:
    return max(4, int(config.get("cash_in.swr_cache_max_items", 64) or 64))


def _swr_cache_enabled() -> bool:
    return bool(config.get("cash_in.swr_cache_enabled", True))


def _build_swr_cache_key(
    *,
    system: str,
    service: str,
    radius_ly: float,
    max_systems: int,
    include_edsm: bool,
    include_spansh: bool,
    cross_enabled: bool,
) -> str:
    return (
        f"system={_as_text(system).casefold()}|service={_as_text(service).casefold()}|"
        f"cross={int(bool(cross_enabled))}|radius={round(float(radius_ly), 2)}|"
        f"max_systems={int(max_systems)}|edsm={int(bool(include_edsm))}|"
        f"spansh={int(bool(include_spansh))}"
    )


def _prune_swr_cache(*, stale_ttl_sec: float, max_items: int) -> None:
    now = time.monotonic()
    stale_ttl = max(0.0, float(stale_ttl_sec))
    for key, item in list(_CASH_IN_SWR_CACHE.items()):
        if not isinstance(item, tuple) or len(item) != 2:
            _CASH_IN_SWR_CACHE.pop(key, None)
            continue
        ts = float(item[0] or 0.0)
        if stale_ttl > 0.0 and (now - ts) > stale_ttl:
            _CASH_IN_SWR_CACHE.pop(key, None)

    if len(_CASH_IN_SWR_CACHE) <= max_items:
        return
    for key, _ in sorted(_CASH_IN_SWR_CACHE.items(), key=lambda kv: kv[1][0])[: len(_CASH_IN_SWR_CACHE) - max_items]:
        _CASH_IN_SWR_CACHE.pop(key, None)


def _store_swr_snapshot(
    *,
    cache_key: str,
    candidates: list[dict[str, Any]],
    source_status: str,
    service: str,
    radius_ly: float,
    max_systems: int,
) -> None:
    if not _swr_cache_enabled():
        return
    if not candidates:
        return
    fresh_ttl, stale_ttl = _swr_cache_ttls()
    if stale_ttl <= 0.0:
        return

    saved_at_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    snapshot_candidates: list[dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        snapshot_candidates.append(dict(row))

    if not snapshot_candidates:
        return

    uc_count = len(filter_candidates_by_service(snapshot_candidates, service="uc"))
    vista_count = len(filter_candidates_by_service(snapshot_candidates, service="vista"))
    payload = {
        "saved_at_utc": saved_at_utc,
        "source_status": _as_text(source_status) or "providers",
        "service": _normalize_cash_in_service(service),
        "radius_ly": float(radius_ly),
        "max_systems": int(max_systems),
        "uc_count": int(uc_count),
        "vista_count": int(vista_count),
        "candidates": snapshot_candidates,
    }
    _CASH_IN_SWR_CACHE[cache_key] = (time.monotonic(), payload)
    _prune_swr_cache(stale_ttl_sec=max(stale_ttl, fresh_ttl), max_items=_swr_cache_max_items())


def _load_swr_snapshot(
    *,
    cache_key: str,
) -> dict[str, Any]:
    if not _swr_cache_enabled():
        return {"status": "DISABLED", "age_sec": 0.0, "entry": {}}

    fresh_ttl, stale_ttl = _swr_cache_ttls()
    item = _CASH_IN_SWR_CACHE.get(cache_key)
    _prune_swr_cache(stale_ttl_sec=stale_ttl, max_items=_swr_cache_max_items())
    if not item:
        return {"status": "MISSING", "age_sec": 0.0, "entry": {}}

    ts_mono, entry = item
    age_sec = max(0.0, time.monotonic() - float(ts_mono or 0.0))
    if age_sec > stale_ttl:
        _CASH_IN_SWR_CACHE.pop(cache_key, None)
        return {"status": "EXPIRED", "age_sec": age_sec, "entry": {}}

    status = "FRESH" if age_sec <= fresh_ttl else "STALE"
    return {
        "status": status,
        "age_sec": age_sec,
        "entry": dict(entry or {}),
    }


def _local_known_cache_enabled() -> bool:
    return bool(config.get("cash_in.local_known_fallback_enabled", True))


def _local_known_cache_ttl_sec() -> float:
    raw = config.get("cash_in.local_known_fallback_ttl_sec", 86400.0)
    try:
        ttl = float(86400.0 if raw is None else raw)
    except Exception:
        ttl = 86400.0
    return max(60.0, ttl)


def _local_known_cache_max_items() -> int:
    raw = config.get("cash_in.local_known_fallback_max_items", 256)
    try:
        items = int(256 if raw is None else raw)
    except Exception:
        items = 256
    return max(16, items)


def _local_known_cache_key(*, service: str) -> str:
    return _normalize_cash_in_service(service)


def _prune_local_known_cache() -> None:
    ttl_sec = _local_known_cache_ttl_sec()
    max_items = _local_known_cache_max_items()
    now = time.monotonic()
    for key, item in list(_CASH_IN_LOCAL_KNOWN_CACHE.items()):
        if not isinstance(item, tuple) or len(item) != 2:
            _CASH_IN_LOCAL_KNOWN_CACHE.pop(key, None)
            continue
        ts = float(item[0] or 0.0)
        if (now - ts) > ttl_sec:
            _CASH_IN_LOCAL_KNOWN_CACHE.pop(key, None)
            continue
        rows = item[1]
        if not isinstance(rows, list):
            _CASH_IN_LOCAL_KNOWN_CACHE.pop(key, None)
            continue
        if len(rows) > max_items:
            _CASH_IN_LOCAL_KNOWN_CACHE[key] = (ts, [dict(r) for r in rows[:max_items] if isinstance(r, dict)])


def _store_local_known_candidates(
    *,
    service: str,
    candidates: list[dict[str, Any]],
    max_items_hint: int,
) -> None:
    if not _local_known_cache_enabled():
        return
    svc = _local_known_cache_key(service=service)
    filtered = filter_candidates_by_service(candidates, service=svc)
    if not filtered:
        return

    rows: list[dict[str, Any]] = []
    for row in filtered:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("source", "LOCAL_KNOWN")
        rows.append(item)
    if not rows:
        return

    merged = build_station_candidates(
        rows,
        source_hint="LOCAL_KNOWN",
        limit=max(max_items_hint, _local_known_cache_max_items()),
    )
    if not merged:
        return
    _CASH_IN_LOCAL_KNOWN_CACHE[svc] = (time.monotonic(), merged[: _local_known_cache_max_items()])
    _prune_local_known_cache()


def _load_local_known_candidates(
    *,
    service: str,
    limit: int,
) -> dict[str, Any]:
    if not _local_known_cache_enabled():
        return {"used": False, "age_sec": 0.0, "count": 0, "candidates": []}

    _prune_local_known_cache()
    svc = _local_known_cache_key(service=service)
    item = _CASH_IN_LOCAL_KNOWN_CACHE.get(svc)
    if not item:
        return {"used": False, "age_sec": 0.0, "count": 0, "candidates": []}

    ts, rows = item
    age_sec = max(0.0, time.monotonic() - float(ts or 0.0))
    out = [
        dict(row)
        for row in (rows or [])
        if isinstance(row, dict)
    ]
    if limit > 0:
        out = out[:limit]
    return {
        "used": bool(out),
        "age_sec": age_sec,
        "count": len(out),
        "candidates": out,
    }


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = _as_text(value).lower()
    return text in {"1", "true", "yes", "y", "on", "enabled"}


def _append_unique_reason(reasons: list[str], reason: str) -> None:
    value = _as_text(reason).lower()
    if value and value not in reasons:
        reasons.append(value)


def _playerdb_bridge_alias_source_status(value: Any) -> str:
    source = _as_text(value).lower()
    if source == "local_known_fallback":
        return "playerdb_bridge"
    return source or "none"


def _detect_offline_or_interrupted(raw_payload: dict[str, Any]) -> bool:
    payload = dict(raw_payload or {})
    explicit_flags = (
        "offline",
        "offline_mode",
        "runtime_offline",
        "provider_offline",
        "providers_offline",
        "journal_interrupted",
        "logs_interrupted",
        "journal_stream_interrupted",
    )
    for key in explicit_flags:
        if _is_truthy(payload.get(key)):
            return True

    if bool(getattr(app_state, "bootstrap_replay", False)):
        return True

    has_live_system_event = bool(getattr(app_state, "has_live_system_event", False))
    if has_live_system_event:
        return False
    current_system = _as_text(getattr(app_state, "current_system", ""))
    if current_system.lower() in {"", "-", "unknown", "nieznany"}:
        return True
    return False


def _build_edge_case_meta(
    *,
    raw_payload: dict[str, Any],
    service: str,
    station_candidates: list[dict[str, Any]],
    station_candidates_meta: dict[str, Any],
    ranking_meta: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(raw_payload or {})
    service_norm = _normalize_cash_in_service(service)
    station_meta = dict(station_candidates_meta or {})
    rank_meta = dict(ranking_meta or {})
    reasons: list[str] = []

    source_status = _as_text(station_meta.get("source_status")).lower()
    provider_lookup_status = _as_text(station_meta.get("provider_lookup_status")).lower()
    provider_lookup_attempted = bool(station_meta.get("provider_lookup_attempted"))
    swr_cache_used = bool(station_meta.get("swr_cache_used"))
    swr_freshness = _as_text(station_meta.get("swr_freshness")).upper()
    local_known_fallback_used = bool(station_meta.get("local_known_fallback_used"))
    offline_index_lookup_attempted = bool(station_meta.get("offline_index_lookup_attempted"))
    offline_index_lookup_status = _as_text(station_meta.get("offline_index_lookup_status")).lower()
    offline_index_used = bool(station_meta.get("offline_index_used")) or source_status == "offline_index"
    offline_index_date = _as_text(station_meta.get("offline_index_date"))
    offline_index_age_days = _safe_int(station_meta.get("offline_index_age_days"))
    cross_system_lookup_attempted = bool(station_meta.get("cross_system_lookup_attempted"))
    candidate_count = int(station_meta.get("count") or 0)
    nearby_requested_radius_ly = _safe_float(station_meta.get("nearby_requested_radius_ly"))
    nearby_effective_radius_ly = _safe_float(station_meta.get("nearby_effective_radius_ly"))
    nearby_provider_response_count = int(station_meta.get("nearby_provider_response_count") or 0)
    nearby_reason = _as_text(station_meta.get("nearby_reason")).lower()

    if (
        (source_status == "providers_empty" or provider_lookup_status == "providers_empty")
        and not offline_index_used
    ):
        _append_unique_reason(reasons, "providers_empty")
    if provider_lookup_status == "provider_down_503":
        _append_unique_reason(reasons, "provider_down_503")
    if provider_lookup_status == "provider_circuit_open":
        _append_unique_reason(reasons, "provider_circuit_open")
    if swr_cache_used and swr_freshness == "STALE":
        _append_unique_reason(reasons, "stale_cache")
    if local_known_fallback_used:
        _append_unique_reason(reasons, "local_known_fallback")
        _append_unique_reason(reasons, "playerdb_bridge")
    if candidate_count <= 0 and not offline_index_used:
        _append_unique_reason(reasons, "no_station_data")
    if offline_index_used:
        _append_unique_reason(reasons, "offline_index")
    elif offline_index_lookup_attempted and offline_index_lookup_status == "no_offline_index_hit":
        _append_unique_reason(reasons, "no_offline_index_hit")
    if nearby_reason == "provider_radius_cap":
        _append_unique_reason(reasons, "provider_radius_cap")
    if nearby_reason == "provider_empty":
        _append_unique_reason(reasons, "provider_empty")
    if (
        nearby_requested_radius_ly > 0.0
        and nearby_effective_radius_ly > 0.0
        and nearby_requested_radius_ly > nearby_effective_radius_ly
    ):
        _append_unique_reason(reasons, "provider_radius_cap")
    if (
        cross_system_lookup_attempted
        and nearby_effective_radius_ly >= 100.0
        and nearby_provider_response_count == 0
    ):
        _append_unique_reason(reasons, "provider_empty")

    profiled_reason = _as_text(rank_meta.get("profiled_reason") or rank_meta.get("reason")).lower()
    if profiled_reason == "no_service_candidates":
        _append_unique_reason(reasons, "no_service_candidates")

    service_candidates = filter_candidates_by_service(station_candidates, service=service_norm)
    non_carrier_candidates = [row for row in service_candidates if not _candidate_is_carrier(row)]
    carrier_candidates = [row for row in service_candidates if _candidate_is_carrier(row)]
    if service_candidates and not non_carrier_candidates:
        _append_unique_reason(reasons, "no_non_carrier")

    if _detect_offline_or_interrupted(payload):
        _append_unique_reason(reasons, "offline")

    confidence = _as_text(station_meta.get("confidence")).lower() or "low"
    if any(
        reason in {
            "providers_empty",
            "provider_down_503",
            "provider_circuit_open",
            "stale_cache",
            "local_known_fallback",
            "provider_radius_cap",
            "provider_empty",
            "no_station_data",
            "no_service_candidates",
            "offline",
        }
        for reason in reasons
    ):
        confidence = "low"
    if offline_index_used:
        med_limit = int(config.get("cash_in.offline_index_confidence_med_age_days", 30) or 30)
        if offline_index_age_days is not None and int(offline_index_age_days) >= 0:
            confidence = "mid" if int(offline_index_age_days) <= max(0, med_limit) else "low"
        else:
            confidence = "low"
    elif "no_non_carrier" in reasons and confidence == "high":
        confidence = "mid"

    advisory_only = bool(reasons)
    ui_hint = ""
    if "offline" in reasons:
        ui_hint = "Tryb offline/przerwane logi: rekomendacja orientacyjna."
    elif "offline_index" in reasons:
        date_txt = offline_index_date or "-"
        age_txt = (
            str(int(offline_index_age_days))
            if offline_index_age_days is not None and int(offline_index_age_days) >= 0
            else "?"
        )
        ui_hint = (
            f"Uzywam offline indexu stacji (Spansh dump): index_date={date_txt}, age={age_txt} dni."
        )
    elif "no_offline_index_hit" in reasons:
        ui_hint = "Offline index stacji nie zwrocil hitu dla tego regionu. Pozostaje tryb orientacyjny."
    elif "provider_radius_cap" in reasons:
        req_txt = (
            str(int(round(nearby_requested_radius_ly)))
            if nearby_requested_radius_ly >= 1.0
            else "-"
        )
        eff_txt = (
            str(int(round(nearby_effective_radius_ly)))
            if nearby_effective_radius_ly >= 1.0
            else "-"
        )
        ui_hint = (
            f"EDSM limit 100 LY: requested={req_txt} LY, effective={eff_txt} LY. "
            "Wynik nearby ma obnizona pewnosc."
        )
    elif "provider_empty" in reasons:
        req_txt = (
            str(int(round(nearby_requested_radius_ly)))
            if nearby_requested_radius_ly >= 1.0
            else "-"
        )
        eff_txt = (
            str(int(round(nearby_effective_radius_ly)))
            if nearby_effective_radius_ly >= 1.0
            else "-"
        )
        ui_hint = (
            f"Provider nearby nie zwrocil wynikow (requested={req_txt} LY, effective={eff_txt} LY). "
            "Szukanie kontynuowane fallbackiem."
        )
    elif "provider_circuit_open" in reasons and "local_known_fallback" in reasons:
        ui_hint = "Provider stacyjny chwilowo niedostepny: pokazuje lokalny cache znanych stacji/systemow."
    elif "provider_down_503" in reasons and "local_known_fallback" in reasons:
        ui_hint = "Provider stacyjny chwilowo niedostepny (HTTP 503): pokazuje lokalny cache znanych stacji/systemow."
    elif "providers_empty" in reasons and "local_known_fallback" in reasons:
        ui_hint = "Provider nie zwrocil danych: pokazuje lokalny cache znanych stacji/systemow."
    elif "provider_circuit_open" in reasons and "stale_cache" in reasons:
        ui_hint = "Provider stacyjny chwilowo niedostepny: wynik z cache (stale)."
    elif "provider_down_503" in reasons and "stale_cache" in reasons:
        ui_hint = "Provider stacyjny chwilowo niedostepny: wynik z cache (stale)."
    elif "stale_cache" in reasons:
        ui_hint = "Wynik z cache (stale): traktuj decyzje orientacyjnie."
    elif "provider_circuit_open" in reasons:
        ui_hint = "Provider stacyjny chwilowo niedostepny (circuit open). Uzyj decyzji orientacyjnej."
    elif "provider_down_503" in reasons:
        ui_hint = "Provider stacyjny chwilowo niedostepny (HTTP 503). Uzyj decyzji orientacyjnej."
    elif "providers_empty" in reasons or "no_station_data" in reasons or "no_service_candidates" in reasons:
        ui_hint = "Dane stacyjne ograniczone: traktuj decyzje orientacyjnie."
    elif "no_non_carrier" in reasons:
        if service_norm == "uc":
            ui_hint = "Brak non-carrier dla UC: carrier moze miec fee 25%."
        else:
            ui_hint = "Brak non-carrier dla Vista: sprawdz status payout i freshness."

    return {
        "reasons": reasons,
        "advisory_only": advisory_only,
        "confidence": confidence,
        "ui_hint": ui_hint,
        "service": service_norm,
        "service_candidates_count": len(service_candidates),
        "service_non_carrier_count": len(non_carrier_candidates),
        "service_carrier_count": len(carrier_candidates),
        "source_status": source_status or "none",
        "source_status_bridge": _playerdb_bridge_alias_source_status(source_status),
        "provider_lookup_status": provider_lookup_status or "not_attempted",
        "provider_lookup_attempted": provider_lookup_attempted,
        "swr_cache_used": swr_cache_used,
        "swr_freshness": swr_freshness or "NONE",
        "local_known_fallback_used": local_known_fallback_used,
        "playerdb_bridge_used": local_known_fallback_used,
        "offline_index_used": offline_index_used,
        "offline_index_lookup_attempted": offline_index_lookup_attempted,
        "offline_index_lookup_status": offline_index_lookup_status or "not_attempted",
        "offline_index_date": offline_index_date,
        "offline_index_age_days": int(offline_index_age_days)
        if offline_index_age_days is not None
        else -1,
        "nearby_requested_radius_ly": float(nearby_requested_radius_ly),
        "nearby_effective_radius_ly": float(nearby_effective_radius_ly),
        "nearby_provider_response_count": int(nearby_provider_response_count),
    }


def _append_edge_case_note(base_note: str, edge_case_meta: dict[str, Any]) -> str:
    note = _as_text(base_note)
    meta = dict(edge_case_meta or {})
    reasons = [str(item).strip().lower() for item in (meta.get("reasons") or []) if str(item).strip()]
    if not reasons:
        return note

    extra_parts: list[str] = []
    if "offline" in reasons:
        extra_parts.append("Tryb offline/przerwane logi: rekomendacja orientacyjna.")
    if "provider_circuit_open" in reasons:
        extra_parts.append("Provider stacyjny chwilowo niedostepny (circuit open).")
    if "provider_down_503" in reasons:
        extra_parts.append("Provider stacyjny chwilowo niedostepny (HTTP 503).")
    if "provider_radius_cap" in reasons:
        extra_parts.append("EDSM nearby ograniczony limitem 100 LY (provider cap).")
    if "provider_empty" in reasons:
        extra_parts.append("EDSM nearby zwrocil pusty wynik dla efektywnego promienia.")
    if "stale_cache" in reasons:
        extra_parts.append("Wynik z cache (stale).")
    if "local_known_fallback" in reasons:
        extra_parts.append("Wynik z lokalnego cache znanych stacji/systemow.")
    if "offline_index" in reasons:
        date_txt = _as_text(meta.get("offline_index_date")) or "-"
        age_days = _safe_int(meta.get("offline_index_age_days"))
        age_txt = str(age_days) if age_days is not None and age_days >= 0 else "?"
        extra_parts.append(
            f"Wynik z offline indexu stacji (Spansh dump), index_date={date_txt}, age={age_txt} dni."
        )
    if "no_offline_index_hit" in reasons:
        extra_parts.append("Offline index stacji nie zwrocil hitu dla regionu.")
    if "providers_empty" in reasons or "no_station_data" in reasons or "no_service_candidates" in reasons:
        extra_parts.append("Brak pelnych danych stacyjnych.")
    if "no_non_carrier" in reasons:
        if _as_text(meta.get("service")).lower() == "uc":
            extra_parts.append("Brak non-carrier dla UC (sprawdz fee carriera).")
        else:
            extra_parts.append("Brak non-carrier dla Vista.")
    if not extra_parts:
        extra_parts.append("Scenariusz fallback: decyzja orientacyjna.")

    suffix = " ".join(extra_parts).strip()
    if note:
        return f"{note} {suffix}".strip()
    return suffix


def _provider_status_from_edsm_snapshot(
    snapshot: dict[str, Any],
    *,
    endpoint_key: str,
) -> str:
    snap = dict(snapshot or {})
    endpoints = snap.get("endpoints")
    endpoint = dict(endpoints.get(endpoint_key) or {}) if isinstance(endpoints, dict) else {}
    if bool(endpoint.get("circuit_open")):
        return "provider_circuit_open"
    try:
        code = int(endpoint.get("last_error_code") or 0)
    except Exception:
        code = 0
    if code == 503:
        return "provider_down_503"
    return ""


def _build_station_candidates_runtime(
    *,
    raw_payload: dict[str, Any],
    system: str,
    service: str,
    freshness_ts: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_status = "none"
    provider_lookup_attempted = False
    provider_lookup_status = "not_attempted"
    cross_system_lookup_attempted = False
    cross_system_lookup_status = "not_attempted"
    cross_system_systems_requested = 0
    cross_system_systems_with_candidates = 0
    nearby_requested_radius_ly = 0.0
    nearby_effective_radius_ly = 0.0
    nearby_provider_response_count = 0
    nearby_reason = ""
    service_norm = _normalize_cash_in_service(service)
    limit = max(4, int(config.get("cash_in.station_candidates_limit", 24) or 24))
    include_edsm = bool(config.get("features.providers.edsm_enabled", False))
    include_spansh = bool(config.get("features.trade.station_lookup_online", False))
    cross_enabled = bool(config.get("cash_in.cross_system_discovery_enabled", True))
    cross_radius_ly = float(config.get("cash_in.cross_system_radius_ly", 120.0) or 120.0)
    cross_max_systems = int(config.get("cash_in.cross_system_max_systems", 12) or 12)
    candidates: list[dict[str, Any]] = []
    edsm_snapshot_data: dict[str, Any] = {}
    swr_cache_key = _build_swr_cache_key(
        system=system,
        service=service_norm,
        radius_ly=cross_radius_ly,
        max_systems=cross_max_systems,
        include_edsm=include_edsm,
        include_spansh=include_spansh,
        cross_enabled=cross_enabled,
    )
    swr_lookup_status = "NOT_USED"
    swr_freshness = "NONE"
    swr_cache_used = False
    swr_cache_age_sec = 0.0
    swr_cache_source_status = ""
    swr_saved_at_utc = ""
    local_known_fallback_used = False
    local_known_fallback_age_sec = 0.0
    local_known_fallback_count = 0
    playerdb_lookup_attempted = False
    playerdb_lookup_status = "not_attempted"
    playerdb_used = False
    playerdb_query_mode = "none"
    playerdb_origin_coords_used = False
    playerdb_origin_coords_from_playerdb = False
    playerdb_coords_missing_count = 0
    offline_index_lookup_attempted = False
    offline_index_used = False
    offline_index_lookup_status = "not_attempted"
    offline_index_path = ""
    offline_index_date = ""
    offline_index_age_days = -1
    offline_index_rows_total = 0
    offline_index_rows_service_match = 0
    offline_index_rows_coords_match = 0
    offline_index_ignored_carriers = 0

    raw_candidates = raw_payload.get("station_candidates") or raw_payload.get("stationCandidates")
    if isinstance(raw_candidates, list) and raw_candidates:
        candidates = build_station_candidates(
            raw_candidates,
            default_system=system,
            source_hint="RUNTIME_PAYLOAD",
            freshness_ts=freshness_ts,
            limit=limit,
        )
        source_status = "payload"

    if not candidates:
        station_names = raw_payload.get("station_names") or raw_payload.get("stationNames")
        if isinstance(station_names, list) and station_names:
            candidates = build_station_candidates(
                station_names,
                default_system=system,
                source_hint="RUNTIME_NAMES",
                freshness_ts=freshness_ts,
                limit=limit,
            )
            source_status = "payload_names"

    lookup_enabled = bool(config.get("cash_in.station_candidates_lookup_enabled", False))
    offline_index_enabled = bool(config.get("cash_in.offline_index_fallback_enabled", True))
    offline_index_non_carrier_only = bool(config.get("cash_in.offline_index_non_carrier_only", True))
    offline_index_path = _resolve_offline_index_path()
    origin_coords = None
    app_star_pos = getattr(app_state, "current_star_pos", None)
    if isinstance(app_star_pos, (list, tuple)) and len(app_star_pos) >= 3:
        try:
            origin_coords = [
                float(app_star_pos[0]),
                float(app_star_pos[1]),
                float(app_star_pos[2]),
            ]
        except Exception:
            origin_coords = None
    if origin_coords is None:
        raw_star_pos = raw_payload.get("star_pos") or raw_payload.get("starPos")
        if isinstance(raw_star_pos, (list, tuple)) and len(raw_star_pos) >= 3:
            try:
                origin_coords = [
                    float(raw_star_pos[0]),
                    float(raw_star_pos[1]),
                    float(raw_star_pos[2]),
                ]
            except Exception:
                origin_coords = None

    def _attempt_offline_index_lookup() -> list[dict[str, Any]]:
        nonlocal offline_index_lookup_attempted
        nonlocal offline_index_lookup_status
        nonlocal offline_index_date
        nonlocal offline_index_age_days
        nonlocal offline_index_rows_total
        nonlocal offline_index_rows_service_match
        nonlocal offline_index_rows_coords_match
        nonlocal offline_index_ignored_carriers
        nonlocal offline_index_used

        offline_index_lookup_attempted = True
        offline_candidates, offline_meta = station_candidates_from_offline_index(
            system,
            service=service_norm,
            origin_coords=origin_coords,
            index_path=offline_index_path,
            freshness_ts=freshness_ts,
            limit=limit,
            non_carrier_only=offline_index_non_carrier_only,
        )
        offline_index_lookup_status = _as_text(offline_meta.get("lookup_status")).lower() or "not_attempted"
        offline_index_date = _as_text(offline_meta.get("index_date"))
        offline_index_age_days = int(offline_meta.get("index_age_days") or -1)
        offline_index_rows_total = int(offline_meta.get("rows_total") or 0)
        offline_index_rows_service_match = int(offline_meta.get("rows_service_match") or 0)
        offline_index_rows_coords_match = int(offline_meta.get("rows_coords_match") or 0)
        offline_index_ignored_carriers = int(offline_meta.get("ignored_carriers") or 0)
        if offline_candidates:
            offline_index_used = True
            return offline_candidates
        if offline_index_lookup_status == "not_attempted":
            offline_index_lookup_status = "no_offline_index_hit"
        return []

    def _attempt_playerdb_lookup() -> list[dict[str, Any]]:
        nonlocal playerdb_lookup_attempted
        nonlocal playerdb_lookup_status
        nonlocal playerdb_used
        nonlocal playerdb_query_mode
        nonlocal playerdb_origin_coords_used
        nonlocal playerdb_origin_coords_from_playerdb
        nonlocal playerdb_coords_missing_count

        playerdb_lookup_attempted = True
        playerdb_candidates, playerdb_meta = station_candidates_from_playerdb(
            system,
            service=service_norm,
            origin_coords=origin_coords,
            limit=limit,
        )
        playerdb_lookup_status = _as_text(playerdb_meta.get("lookup_status")).lower() or "not_attempted"
        playerdb_query_mode = _as_text(playerdb_meta.get("query_mode")).lower() or "none"
        playerdb_origin_coords_used = bool(playerdb_meta.get("origin_coords_used"))
        playerdb_origin_coords_from_playerdb = bool(playerdb_meta.get("origin_coords_from_playerdb"))
        playerdb_coords_missing_count = int(playerdb_meta.get("coords_missing_count") or 0)
        if playerdb_candidates:
            playerdb_used = True
            return list(playerdb_candidates)
        return []

    # Local-first path for mode without online lookup:
    # prefer real playerdb before bridge runtime cache and offline index.
    if not candidates and not lookup_enabled:
        playerdb_rows = _attempt_playerdb_lookup()
        if playerdb_rows:
            candidates = playerdb_rows
            source_status = "playerdb"

    if not candidates and not lookup_enabled:
        known = _load_local_known_candidates(service=service_norm, limit=limit)
        if bool(known.get("used")):
            known_rows = list(known.get("candidates") or [])
            known_candidates = build_station_candidates(
                known_rows,
                default_system=system,
                source_hint="LOCAL_KNOWN",
                freshness_ts=freshness_ts,
                limit=limit,
            )
            if known_candidates:
                candidates = known_candidates
                source_status = "local_known_fallback"
                local_known_fallback_used = True
                local_known_fallback_age_sec = float(known.get("age_sec") or 0.0)
                local_known_fallback_count = int(known.get("count") or 0)

    # Offline index fallback (after local/player memory fallback).
    if not candidates and offline_index_enabled and not lookup_enabled:
        offline_rows = _attempt_offline_index_lookup()
        if offline_rows:
            candidates = offline_rows
            source_status = "offline_index"

    if not candidates and lookup_enabled:
        provider_lookup_attempted = True
        candidates = station_candidates_for_system_from_providers(
            system,
            include_edsm=include_edsm,
            include_spansh=include_spansh,
            freshness_ts=freshness_ts,
            limit=limit,
        )
        if include_edsm:
            edsm_snapshot_data = dict(edsm_provider_resilience_snapshot() or {})
        if candidates:
            provider_lookup_status = "providers"
            source_status = provider_lookup_status
        else:
            provider_lookup_status = "providers_empty"
            status_override = _provider_status_from_edsm_snapshot(
                edsm_snapshot_data,
                endpoint_key="station_details",
            )
            if status_override:
                provider_lookup_status = status_override
            source_status = provider_lookup_status
    elif not lookup_enabled:
        provider_lookup_status = "disabled"

    system_lookup_online = bool(config.get("features.providers.system_lookup_online", False))
    needs_cross_system = bool(lookup_enabled and cross_enabled and system_lookup_online)
    if needs_cross_system:
        has_service_locally = bool(
            filter_candidates_by_service(candidates, service=service_norm)
        )
        needs_cross_system = (not candidates) or (not has_service_locally)

    if needs_cross_system:
        provider_lookup_attempted = True
        cross_system_lookup_attempted = True
        cross_candidates, cross_meta = station_candidates_cross_system_from_providers(
            system,
            service=service_norm,
            include_edsm=include_edsm,
            include_spansh=include_spansh,
            radius_ly=cross_radius_ly,
            max_systems=cross_max_systems,
            origin_coords=origin_coords,
            freshness_ts=freshness_ts,
            limit=limit,
        )
        if include_edsm:
            edsm_snapshot_data = dict(edsm_provider_resilience_snapshot() or {})
        cross_system_systems_requested = int(cross_meta.get("systems_requested") or 0)
        cross_system_systems_with_candidates = int(cross_meta.get("systems_with_candidates") or 0)
        nearby_requested_radius_ly = float(
            cross_meta.get("nearby_requested_radius_ly") or 0.0
        )
        nearby_effective_radius_ly = float(
            cross_meta.get("nearby_effective_radius_ly") or 0.0
        )
        nearby_provider_response_count = int(
            cross_meta.get("nearby_provider_response_count") or 0
        )
        nearby_reason = _as_text(cross_meta.get("nearby_reason")).lower()
        if cross_candidates:
            combined: list[dict[str, Any] | str] = []
            combined.extend(candidates)
            combined.extend(cross_candidates)
            candidates = build_station_candidates(
                combined,
                default_system=system,
                source_hint="CROSS_SYSTEM",
                freshness_ts=freshness_ts,
                limit=limit,
            )
            source_status = "providers_cross_system"
            provider_lookup_status = "providers_cross_system"
            cross_system_lookup_status = "cross_system"
        else:
            cross_system_lookup_status = "cross_system_empty"
            status_override = _provider_status_from_edsm_snapshot(
                edsm_snapshot_data,
                endpoint_key="nearby_systems",
            )
            if status_override:
                cross_system_lookup_status = status_override
                if not candidates:
                    provider_lookup_status = status_override
                    source_status = status_override
    elif not cross_enabled:
        cross_system_lookup_status = "disabled"
    elif not system_lookup_online:
        cross_system_lookup_status = "system_lookup_disabled"
    else:
        cross_system_lookup_status = "not_needed"

    if provider_lookup_attempted and candidates:
        if source_status in {"providers", "providers_cross_system"}:
            _store_swr_snapshot(
                cache_key=swr_cache_key,
                candidates=candidates,
                source_status=source_status,
                service=service_norm,
                radius_ly=cross_radius_ly,
                max_systems=cross_max_systems,
            )
        _store_local_known_candidates(
            service=service_norm,
            candidates=candidates,
            max_items_hint=limit * 2,
        )

    if provider_lookup_attempted and not candidates:
        swr_snapshot = _load_swr_snapshot(cache_key=swr_cache_key)
        swr_lookup_status = _as_text(swr_snapshot.get("status")).upper() or "NONE"
        swr_freshness = (
            swr_lookup_status
            if swr_lookup_status in {"FRESH", "STALE", "EXPIRED"}
            else "NONE"
        )
        if swr_lookup_status in {"FRESH", "STALE"}:
            swr_entry = dict(swr_snapshot.get("entry") or {})
            cached_rows = list(swr_entry.get("candidates") or [])
            cached_freshness_ts = _as_text(swr_entry.get("saved_at_utc"))
            cached_candidates = build_station_candidates(
                cached_rows,
                default_system=system,
                source_hint="SWR_CACHE",
                freshness_ts=freshness_ts or cached_freshness_ts,
                limit=limit,
            )
            if cached_candidates:
                candidates = cached_candidates
                swr_cache_used = True
                swr_cache_age_sec = float(swr_snapshot.get("age_sec") or 0.0)
                swr_cache_source_status = _as_text(swr_entry.get("source_status"))
                swr_saved_at_utc = cached_freshness_ts
                if swr_lookup_status == "STALE":
                    source_status = "providers_cache_stale"
                else:
                    restored_status = swr_cache_source_status or "providers"
                    source_status = restored_status
                    provider_lookup_status = restored_status

    if provider_lookup_attempted and not candidates:
        playerdb_rows = _attempt_playerdb_lookup()
        if playerdb_rows:
            candidates = playerdb_rows
            source_status = "playerdb"

    if provider_lookup_attempted and not candidates:
        known = _load_local_known_candidates(service=service_norm, limit=limit)
        if bool(known.get("used")):
            known_rows = list(known.get("candidates") or [])
            known_candidates = build_station_candidates(
                known_rows,
                default_system=system,
                source_hint="LOCAL_KNOWN",
                freshness_ts=freshness_ts,
                limit=limit,
            )
            if known_candidates:
                candidates = known_candidates
                source_status = "local_known_fallback"
                local_known_fallback_used = True
                local_known_fallback_age_sec = float(known.get("age_sec") or 0.0)
                local_known_fallback_count = int(known.get("count") or 0)

    if provider_lookup_attempted and not candidates and offline_index_enabled:
        offline_rows = _attempt_offline_index_lookup()
        if offline_rows:
            candidates = offline_rows
            source_status = "offline_index"

    if not candidates:
        current_station = _as_text(getattr(app_state, "current_station", ""))
        if current_station:
            candidates = build_station_candidates(
                [
                    {
                        "name": current_station,
                        "system_name": system,
                        "type": "station",
                        "source": "RUNTIME_LOCAL",
                    }
                ],
                default_system=system,
                source_hint="RUNTIME_LOCAL",
                freshness_ts=freshness_ts,
                limit=limit,
            )
            source_status = "local_fallback"

    if not offline_index_enabled:
        offline_index_lookup_status = "disabled"
    elif offline_index_lookup_attempted and offline_index_lookup_status == "not_attempted":
        offline_index_lookup_status = "no_offline_index_hit"
    elif bool(candidates) and not offline_index_lookup_attempted:
        offline_index_lookup_status = "not_needed"
    elif offline_index_lookup_status == "not_attempted":
        offline_index_lookup_status = "not_attempted"

    uc_candidates = filter_candidates_by_service(candidates, service="uc")
    vista_candidates = filter_candidates_by_service(candidates, service="vista")
    meta = {
        "source_status": source_status,
        "source_status_bridge": _playerdb_bridge_alias_source_status(source_status),
        "source_order_contract": [
            "providers",
            "providers_cross_system",
            "providers_cache",
            "playerdb",
            "playerdb_bridge",
            "offline_index",
            "local_fallback",
        ],
        "provider_lookup_attempted": provider_lookup_attempted,
        "provider_lookup_status": provider_lookup_status,
        "cross_system_lookup_attempted": cross_system_lookup_attempted,
        "cross_system_lookup_status": cross_system_lookup_status,
        "cross_system_systems_requested": cross_system_systems_requested,
        "cross_system_systems_with_candidates": cross_system_systems_with_candidates,
        "cross_system_origin_coords_used": bool(origin_coords),
        "nearby_requested_radius_ly": float(nearby_requested_radius_ly),
        "nearby_effective_radius_ly": float(nearby_effective_radius_ly),
        "nearby_provider_response_count": int(nearby_provider_response_count),
        "nearby_reason": nearby_reason,
        "swr_cache_used": swr_cache_used,
        "swr_lookup_status": swr_lookup_status,
        "swr_freshness": swr_freshness,
        "swr_cache_age_sec": int(round(swr_cache_age_sec)) if swr_cache_age_sec > 0.0 else 0,
        "swr_cache_source_status": swr_cache_source_status,
        "swr_saved_at_utc": swr_saved_at_utc,
        "swr_profile_service": service_norm,
        "swr_profile_radius_ly": float(cross_radius_ly),
        "swr_profile_max_systems": int(cross_max_systems),
        "local_known_fallback_used": local_known_fallback_used,
        "playerdb_lookup_attempted": playerdb_lookup_attempted,
        "playerdb_lookup_status": playerdb_lookup_status,
        "playerdb_used": playerdb_used,
        "playerdb_query_mode": playerdb_query_mode,
        "playerdb_origin_coords_used": playerdb_origin_coords_used,
        "playerdb_origin_coords_from_playerdb": playerdb_origin_coords_from_playerdb,
        "playerdb_coords_missing_count": playerdb_coords_missing_count,
        "playerdb_bridge_used": local_known_fallback_used,
        "playerdb_bridge_source_status": (
            "playerdb_bridge" if local_known_fallback_used else "not_used"
        ),
        "playerdb_bridge_backend": "runtime_memory_cache",
        "local_known_fallback_age_sec": int(round(local_known_fallback_age_sec))
        if local_known_fallback_age_sec > 0.0
        else 0,
        "local_known_fallback_count": local_known_fallback_count,
        "offline_index_lookup_attempted": offline_index_lookup_attempted,
        "offline_index_lookup_status": offline_index_lookup_status,
        "offline_index_used": offline_index_used,
        "offline_index_path": offline_index_path,
        "offline_index_date": offline_index_date,
        "offline_index_age_days": offline_index_age_days,
        "offline_index_rows_total": offline_index_rows_total,
        "offline_index_rows_service_match": offline_index_rows_service_match,
        "offline_index_rows_coords_match": offline_index_rows_coords_match,
        "offline_index_ignored_carriers": offline_index_ignored_carriers,
        "provider_down_503_count": int(
            max(
                int(
                    (
                        (
                            (edsm_snapshot_data.get("endpoints") or {}).get("station_details")
                            or {}
                        ).get("provider_down_503_count")
                        or 0
                    )
                ),
                int(
                    (
                        (
                            (edsm_snapshot_data.get("endpoints") or {}).get("nearby_systems")
                            or {}
                        ).get("provider_down_503_count")
                        or 0
                    )
                ),
            )
        ),
        "count": len(candidates),
        "uc_count": len(uc_candidates),
        "vista_count": len(vista_candidates),
        "confidence": _station_candidates_confidence(
            candidates_count=len(candidates),
            uc_count=len(uc_candidates),
            vista_count=len(vista_candidates),
            source_status=source_status,
            swr_freshness=swr_freshness,
            offline_index_age_days=offline_index_age_days,
            playerdb_query_mode=playerdb_query_mode,
        ),
    }
    return candidates, meta


def _signature(payload: CashInAssistantPayload) -> str:
    station_meta = dict(payload.station_candidates_meta or {})
    ranking_meta = dict(payload.ranking_meta or {})
    edge_meta = dict(payload.edge_case_meta or {})
    edge_sig = ",".join(
        str(item).strip().lower()
        for item in (edge_meta.get("reasons") or [])
        if str(item).strip()
    ) or "none"
    return (
        f"{payload.system}:{int(round(payload.system_value_estimated))}:"
        f"{int(round(payload.session_value_estimated))}:{payload.signal}:"
        f"{payload.scanned_bodies or 'na'}/{payload.total_bodies or 'na'}:"
        f"{payload.trust_status}:{payload.confidence}:"
        f"{payload.service}:{station_meta.get('count', 0)}:{station_meta.get('source_status', 'na')}:"
        f"{ranking_meta.get('hard_filter_count', 0)}:{edge_sig}"
    )


def _build_tts_line(payload: CashInAssistantPayload) -> str:
    edge_meta = dict(payload.edge_case_meta or {})
    edge_reasons = {
        str(item).strip().lower()
        for item in (edge_meta.get("reasons") or [])
        if str(item).strip()
    }
    if edge_reasons:
        if "offline" in edge_reasons:
            return "Cash-in: tryb offline lub przerwane logi. Rekomendacja orientacyjna, sprawdz panel."
        if "provider_circuit_open" in edge_reasons and "offline_index" in edge_reasons:
            return "Cash-in: provider stacyjny chwilowo niedostepny. Uzywam offline indexu stacji, sprawdz panel."
        if "provider_down_503" in edge_reasons and "offline_index" in edge_reasons:
            return "Cash-in: provider stacyjny zwraca blad 503. Uzywam offline indexu stacji, sprawdz panel."
        if "providers_empty" in edge_reasons and "offline_index" in edge_reasons:
            return "Cash-in: provider nie zwrocil danych. Uzywam offline indexu stacji, sprawdz panel."
        if "offline_index" in edge_reasons:
            return "Cash-in: korzystam z offline indexu stacji. Sprawdz panel i ustaw trase."
        if "provider_circuit_open" in edge_reasons and "local_known_fallback" in edge_reasons:
            return "Cash-in: provider stacyjny chwilowo niedostepny. Pokazuje lokalny cache znanych stacji, sprawdz panel."
        if "provider_down_503" in edge_reasons and "local_known_fallback" in edge_reasons:
            return "Cash-in: provider stacyjny zwraca blad 503. Pokazuje lokalny cache znanych stacji, sprawdz panel."
        if "providers_empty" in edge_reasons and "local_known_fallback" in edge_reasons:
            return "Cash-in: provider nie zwrocil danych. Pokazuje lokalny cache znanych stacji, sprawdz panel."
        if "provider_circuit_open" in edge_reasons and "stale_cache" in edge_reasons:
            return "Cash-in: provider stacyjny chwilowo niedostepny. Pokazuje wynik z cache stale, sprawdz panel."
        if "provider_down_503" in edge_reasons and "stale_cache" in edge_reasons:
            return "Cash-in: provider stacyjny zwraca blad 503. Pokazuje wynik z cache stale, sprawdz panel."
        if "provider_radius_cap" in edge_reasons and "provider_empty" in edge_reasons:
            return "Cash-in: EDSM nearby ograniczony limitem 100 LY i bez wynikow. Uzywam fallbacku, sprawdz panel."
        if "provider_radius_cap" in edge_reasons:
            return "Cash-in: EDSM nearby ograniczony limitem 100 LY. Traktuj decyzje orientacyjnie i sprawdz panel."
        if "provider_empty" in edge_reasons:
            return "Cash-in: provider nearby zwrocil pusty wynik. Sprawdz panel i fallback."
        if "local_known_fallback" in edge_reasons:
            return "Cash-in: pokazuje lokalny cache znanych stacji. Traktuj decyzje orientacyjnie."
        if "no_offline_index_hit" in edge_reasons:
            return "Cash-in: offline index stacji nie zwrocil hitu. Rekomendacja orientacyjna, sprawdz panel."
        if "stale_cache" in edge_reasons:
            return "Cash-in: pokazuje wynik z cache stale. Traktuj decyzje orientacyjnie."
        if "provider_circuit_open" in edge_reasons:
            return "Cash-in: provider stacyjny chwilowo niedostepny. Uzywam trybu orientacyjnego, sprawdz panel."
        if "provider_down_503" in edge_reasons:
            return "Cash-in: provider stacyjny zwraca blad 503. Rekomendacja orientacyjna, sprawdz panel."
        if "no_non_carrier" in edge_reasons and (
            "providers_empty" in edge_reasons
            or "no_station_data" in edge_reasons
            or "no_service_candidates" in edge_reasons
        ):
            if _normalize_cash_in_service(payload.service) == "uc":
                return "Cash-in: dane stacyjne ograniczone i dla UC widze tylko carriery. Sprawdz panel."
            return "Cash-in: dane stacyjne ograniczone i brak non-carrier dla Vista. Sprawdz panel."
        if (
            "providers_empty" in edge_reasons
            or "no_station_data" in edge_reasons
            or "no_service_candidates" in edge_reasons
        ):
            return "Cash-in: brak pelnych danych stacyjnych. Rekomendacja orientacyjna, sprawdz panel."
        if "no_non_carrier" in edge_reasons:
            if _normalize_cash_in_service(payload.service) == "uc":
                return "Cash-in: dla UC widze tylko carriery. Sprawdz fee i zdecyduj."
            return "Cash-in: dla Vista widze tylko carriery. Sprawdz status payout i zdecyduj."

    count = len(payload.options or [])
    if count >= 3:
        return "Cash-in: mam trzy opcje w panelu. Rozwaz teraz, po domknieciu systemu albo pozniej."
    if count == 2:
        return "Cash-in: mam dwie opcje w panelu. Rozwaz teraz albo pozniej."
    return "Cash-in: sprawdz opcje w panelu i zdecyduj."


def _normalize_confidence_level(value: Any) -> str:
    norm = _as_text(value).lower()
    if norm in {"high", "mid", "low"}:
        return norm
    if norm == "medium":
        return "mid"
    return ""


def _resolve_startjump_confidence(
    *,
    system_value: float,
    session_value: float,
    has_system_summary: bool,
) -> str:
    if has_system_summary and system_value > 0 and session_value > 0:
        return "high"
    if max(system_value, session_value) > 0:
        return "mid"
    return "low"


def _round_orientational_value(value: float) -> int:
    amount = max(0.0, float(value or 0.0))
    if amount >= 1_000_000.0:
        step = 1_000_000.0
    elif amount >= 100_000.0:
        step = 100_000.0
    else:
        step = 10_000.0
    return int(round(amount / step) * step)


def _signal_to_var_tier(signal: str) -> str:
    sig = _as_text(signal).lower()
    if sig == "wysoki":
        return "HIGH"
    if sig == "sredni":
        return "MED"
    return "LOW"


def _build_startjump_tts_line(
    *,
    confidence: str,
    system_value: float,
    session_value: float,
    signal: str,
) -> str:
    conf = _normalize_confidence_level(confidence) or "low"
    if conf == "high":
        return (
            "Cash-in: Twoje dane naukowe sa warte "
            f"{_format_cr(session_value)} Cr, a w ostatnim systemie zarobiles "
            f"{_format_cr(system_value)} Cr."
        )
    if conf == "mid":
        session_approx = _round_orientational_value(session_value)
        system_approx = _round_orientational_value(system_value)
        return (
            "Cash-in orientacyjnie: lacznie okolo "
            f"{_format_cr(session_approx)} Cr, a ostatni system okolo "
            f"{_format_cr(system_approx)} Cr."
        )
    return f"Cash-in: niska pewnosc wyceny. VaR(Data): {_signal_to_var_tier(signal)}."


def trigger_startjump_cash_in_callout(
    *,
    event: dict[str, Any] | None = None,
    gui_ref=None,
) -> bool:
    if not bool(config.get("cash_in.startjump_callout_enabled", True)):
        return False

    ev = dict(event or {})
    if _as_text(ev.get("event")).lower() != "startjump":
        return False

    jump_type = _as_text(ev.get("JumpType")).lower()
    if jump_type and jump_type != "hyperspace":
        return False

    if bool(getattr(app_state, "bootstrap_replay", False)):
        return False

    system_name = (
        _as_text(getattr(app_state, "current_system", ""))
        or _as_text(ev.get("StarSystem"))
        or "unknown"
    )

    has_system_summary = False
    system_value = 0.0
    try:
        summary_data = app_state.exit_summary.build_summary_data(system_name=system_name)
        if summary_data is not None:
            has_system_summary = True
            system_value = _safe_float(getattr(summary_data, "total_value", 0.0))
    except Exception:
        has_system_summary = False
        system_value = 0.0

    session_value = 0.0
    try:
        totals = app_state.system_value_engine.calculate_totals()
        if isinstance(totals, dict):
            session_value = _safe_float(totals.get("total"))
    except Exception:
        session_value = 0.0

    explicit_confidence = _normalize_confidence_level(
        ev.get("cash_in_confidence")
        or ev.get("cashInConfidence")
        or ev.get("confidence")
    )
    confidence = explicit_confidence or _resolve_startjump_confidence(
        system_value=system_value,
        session_value=session_value,
        has_system_summary=has_system_summary,
    )
    signal = _cash_signal_from_values(system_value, session_value)

    cooldown_seconds = float(
        config.get("cash_in.startjump_callout_cooldown_sec", 35.0) or 35.0
    )
    system_bucket = int(round(system_value / 1_000_000.0))
    session_bucket = int(round(session_value / 1_000_000.0))
    signature = (
        f"{system_name}:{signal}:{confidence}:{system_bucket}:{session_bucket}"
    )
    if not DEBOUNCER.is_allowed(
        "cash_in_startjump_callout",
        cooldown_seconds,
        context=signature,
    ):
        return False

    raw_text = _build_startjump_tts_line(
        confidence=confidence,
        system_value=system_value,
        session_value=session_value,
        signal=signal,
    )
    risk_status = "RISK_MEDIUM" if signal == "wysoki" else "RISK_LOW"
    var_status = (
        "VAR_HIGH"
        if signal == "wysoki"
        else "VAR_MEDIUM" if signal == "sredni" else "VAR_LOW"
    )
    confidence_policy = (
        "HIGH_EXACT"
        if confidence == "high"
        else "MED_APPROX" if confidence == "mid" else "LOW_TIER_ONLY"
    )
    priority = "P1_HIGH" if confidence == "low" else "P2_NORMAL"

    context = {
        "system": system_name,
        "raw_text": raw_text,
        "risk_status": risk_status,
        "var_status": var_status,
        "trust_status": "TRUST_HIGH",
        "confidence": confidence,
        "confidence_policy": confidence_policy,
        # StartJump callout musi przechodzic przy MID/LOW confidence,
        # ale dalej respektuje anti-spam/cooldown z dispatchera.
        "force_tts": True,
        "cash_in_startjump_payload": {
            "system": system_name,
            "system_value_estimated": int(round(system_value)),
            "session_value_estimated": int(round(session_value)),
            "signal": signal,
            "confidence": confidence,
            "confidence_policy": confidence_policy,
        },
    }

    emit_insight(
        raw_text,
        gui_ref=gui_ref,
        message_id="MSG.CASH_IN_STARTJUMP",
        source="cash_in_assistant",
        event_type="CASH_IN_STARTJUMP",
        context=context,
        priority=priority,
        dedup_key=f"cash_in_startjump:{signature}",
        cooldown_scope="entity",
        cooldown_seconds=cooldown_seconds,
    )
    return True


def trigger_cash_in_assistant(
    *,
    gui_ref=None,
    mode: str = "auto",
    summary_payload: dict[str, Any] | None = None,
    suppress_tts: bool = False,
) -> bool:
    if not bool(config.get("cash_in_assistant_enabled", True)):
        return False

    mode_norm = _as_text(mode).lower() or "auto"
    is_manual_mode = mode_norm in {"manual", "manual_hotkey"}
    raw = dict(summary_payload or {})

    system = _as_text(raw.get("system")) or _as_text(getattr(app_state, "current_system", "")) or "unknown"
    scanned = _safe_int(raw.get("scanned_bodies"))
    total = _safe_int(raw.get("total_bodies"))
    system_value = _safe_float(raw.get("cash_in_system_estimated"))
    session_value = _safe_float(raw.get("cash_in_session_estimated"))
    signal = _as_text(raw.get("cash_in_signal")).lower() or _cash_signal_from_values(system_value, session_value)
    trust_status = _as_text(raw.get("trust_status")).upper() or "TRUST_HIGH"
    confidence = _as_text(raw.get("confidence")).lower() or "mid"
    service = _normalize_cash_in_service(
        raw.get("cash_in_service")
        or raw.get("cashInService")
        or raw.get("service")
    )
    tariff_percent = _safe_optional_float(
        raw.get("tariff_percent")
        or raw.get("tariffPercent")
        or raw.get("fleet_carrier_tariff_percent")
        or raw.get("fleetCarrierTariffPercent")
    )
    freshness_ts = (
        _as_text(raw.get("freshness_ts"))
        or _as_text(raw.get("freshnessTs"))
        or _as_text(raw.get("station_freshness_ts"))
        or _as_text(raw.get("stationFreshnessTs"))
    )
    vista_fc_policy_mode = _normalize_vista_fc_policy_mode(
        raw.get("vista_fc_policy_mode")
        or raw.get("vistaFcPolicyMode")
        or raw.get("vista_fc_policy")
        or raw.get("vistaFcPolicy")
        or config.get("cash_in.vista_fc_policy_mode", "ASSUMED_100")
    )

    payout_contract = _build_payout_contract(
        gross_value=session_value,
        tariff_percent=tariff_percent,
        vista_fc_policy_mode=vista_fc_policy_mode,
        freshness_ts=freshness_ts,
    )
    station_candidates, station_candidates_meta = _build_station_candidates_runtime(
        raw_payload=raw,
        system=system,
        service=service,
        freshness_ts=freshness_ts,
    )
    options, ranking_meta = _build_profiled_options(
        service=service,
        candidates=station_candidates,
        payout_contract=payout_contract,
        trust_status=trust_status,
        confidence=confidence,
    )
    profiled_reason = _as_text(ranking_meta.get("reason")).lower()
    if not options:
        options = _build_options(
            signal=signal,
            system_value=system_value,
            session_value=session_value,
            trust_status=trust_status,
            confidence=confidence,
            scanned_bodies=scanned,
            total_bodies=total,
        )
        ranking_meta = {
            "enabled": False,
            "reason": "fallback_legacy_options",
            "profiled_reason": profiled_reason,
            "service": service,
            "hard_filter_count": 0,
        }
    # F12.2: nie podpinamy placeholder targetu dla scenariusza no_service_candidates.
    if profiled_reason != "no_service_candidates":
        options = _attach_fallback_target_to_options(
            options,
            station_candidates=station_candidates,
            service=service,
        )
    if any(bool((opt or {}).get("fallback_target_attached")) for opt in options):
        ranking_meta["fallback_target_attached"] = True
    options = _apply_ui_transparency_contract(options)

    edge_case_meta = _build_edge_case_meta(
        raw_payload=raw,
        service=service,
        station_candidates=station_candidates,
        station_candidates_meta=station_candidates_meta,
        ranking_meta=ranking_meta,
    )
    confidence = _as_text(edge_case_meta.get("confidence")).lower() or confidence

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
        service=service,
        payout_contract=payout_contract,
        station_candidates=station_candidates,
        station_candidates_meta=station_candidates_meta,
        ranking_meta=ranking_meta,
        edge_case_meta=edge_case_meta,
    )
    payload.note = _append_edge_case_note(payload.note, edge_case_meta)
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
    if suppress_tts:
        # Summary-driven auto call should populate panel/state without cutting into
        # exploration summary voice line.
        context["suppress_tts"] = True
        context["voice_sequence_reason"] = "after_exploration_summary"

    dedup_key = (
        f"cash_in_manual:{payload.system}:{payload.signature}"
        if is_manual_mode
        else f"cash_in_auto:{payload.system}:{payload.signature}"
    )
    cooldown_seconds = 0.0 if is_manual_mode else 90.0

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
