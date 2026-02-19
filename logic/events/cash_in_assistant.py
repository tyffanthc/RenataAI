from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import config
from app.state import app_state
from logic.cash_in_station_candidates import (
    build_station_candidates,
    filter_candidates_by_service,
    station_candidates_for_system_from_providers,
)
from logic.insight_dispatcher import emit_insight
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
        return [], {"enabled": False, "reason": "no_service_candidates", "service": service_norm}

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
        "hutton_guard_threshold_ls": hutton_threshold_ls,
        "avoid_carriers_for_uc": avoid_carriers_for_uc,
        "carrier_ok_for_fast_mode": carrier_ok_for_fast_mode,
    }
    return options, ranking_meta


def resolve_cash_in_option_target(option: dict[str, Any] | None) -> dict[str, str]:
    payload = option if isinstance(option, dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}

    target_system = str(
        target.get("system_name")
        or payload.get("target_system")
        or payload.get("system")
        or ""
    ).strip()
    target_station = str(
        target.get("name")
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

    return {
        "target_system": target_system,
        "target_station": target_station,
        "target_display": target_display,
        "profile": profile,
        "route_profile": route_profile,
    }


def handoff_cash_in_to_route_intent(
    option: dict[str, Any] | None,
    *,
    set_route_intent: Any,
    source: str = "cash_in.intent",
    allow_auto_route: bool = False,
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
    if not target_system:
        return {
            "ok": False,
            "reason": "target_missing",
            "target_system": "",
            "target_station": str(target.get("target_station") or "").strip(),
            "target_display": str(target.get("target_display") or "").strip(),
            "profile": str(target.get("profile") or "").strip(),
            "route_profile": str(target.get("route_profile") or "").strip(),
            "snapshot": {},
        }

    snapshot = set_route_intent(target_system, source=source) or {}
    return {
        "ok": True,
        "reason": "intent_set",
        "target_system": target_system,
        "target_station": str(target.get("target_station") or "").strip(),
        "target_display": str(target.get("target_display") or "").strip(),
        "profile": str(target.get("profile") or "").strip(),
        "route_profile": str(target.get("route_profile") or "").strip(),
        "snapshot": snapshot,
    }


def _station_candidates_confidence(
    *,
    candidates_count: int,
    uc_count: int,
    vista_count: int,
    source_status: str,
) -> str:
    source = _as_text(source_status).lower()
    if candidates_count <= 0:
        return "low"
    if source.startswith("providers") and (uc_count > 0 or vista_count > 0):
        return "high"
    if uc_count > 0 or vista_count > 0:
        return "mid"
    return "low"


def _build_station_candidates_runtime(
    *,
    raw_payload: dict[str, Any],
    system: str,
    freshness_ts: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_status = "none"
    limit = max(4, int(config.get("cash_in.station_candidates_limit", 24) or 24))
    candidates: list[dict[str, Any]] = []

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
    if not candidates and lookup_enabled:
        include_edsm = bool(config.get("features.providers.edsm_enabled", False))
        include_spansh = bool(config.get("features.trade.station_lookup_online", False))
        candidates = station_candidates_for_system_from_providers(
            system,
            include_edsm=include_edsm,
            include_spansh=include_spansh,
            freshness_ts=freshness_ts,
            limit=limit,
        )
        source_status = "providers" if candidates else "providers_empty"

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

    uc_candidates = filter_candidates_by_service(candidates, service="uc")
    vista_candidates = filter_candidates_by_service(candidates, service="vista")
    meta = {
        "source_status": source_status,
        "count": len(candidates),
        "uc_count": len(uc_candidates),
        "vista_count": len(vista_candidates),
        "confidence": _station_candidates_confidence(
            candidates_count=len(candidates),
            uc_count=len(uc_candidates),
            vista_count=len(vista_candidates),
            source_status=source_status,
        ),
    }
    return candidates, meta


def _signature(payload: CashInAssistantPayload) -> str:
    station_meta = dict(payload.station_candidates_meta or {})
    ranking_meta = dict(payload.ranking_meta or {})
    return (
        f"{payload.system}:{int(round(payload.system_value_estimated))}:"
        f"{int(round(payload.session_value_estimated))}:{payload.signal}:"
        f"{payload.scanned_bodies or 'na'}/{payload.total_bodies or 'na'}:"
        f"{payload.trust_status}:{payload.confidence}:"
        f"{payload.service}:{station_meta.get('count', 0)}:{station_meta.get('source_status', 'na')}:"
        f"{ranking_meta.get('hard_filter_count', 0)}"
    )


def _build_tts_line(payload: CashInAssistantPayload) -> str:
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
        freshness_ts=freshness_ts,
    )
    options, ranking_meta = _build_profiled_options(
        service=service,
        candidates=station_candidates,
        payout_contract=payout_contract,
        trust_status=trust_status,
        confidence=confidence,
    )
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
            "service": service,
            "hard_filter_count": 0,
        }
    options = _apply_ui_transparency_contract(options)

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
