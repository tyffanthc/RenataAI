from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_RISK_RANK = {
    "LOW": 1,
    "MED": 2,
    "HIGH": 3,
    "CRIT": 4,
}


@dataclass(frozen=True)
class RiskRebuyContract:
    risk_label: str
    rebuy_label: str
    source_risk_label: str
    value_risk_label: str
    exploration_value_estimated: float
    exobio_value_estimated: float


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _normalize_risk_label(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "CRIT" in text:
        return "CRIT"
    if "HIGH" in text:
        return "HIGH"
    if "MED" in text:
        return "MED"
    return "LOW"


def _value_risk_label(*, exploration_value: float, exobio_value: float) -> str:
    # VERY_HIGH from product feedback is intentionally collapsed to HIGH for widget contract.
    if exploration_value >= 250_000_000.0 or exobio_value >= 1_000_000_000.0:
        return "CRIT"
    if exploration_value >= 200_000_000.0 or exobio_value >= 750_000_000.0:
        return "HIGH"
    if exploration_value >= 150_000_000.0 or exobio_value >= 500_000_000.0:
        return "HIGH"
    if exploration_value >= 100_000_000.0 or exobio_value >= 250_000_000.0:
        return "MED"
    if exploration_value >= 50_000_000.0 or exobio_value >= 100_000_000.0:
        return "LOW"
    return "LOW"


def _rebuy_label(*, credits: float, rebuy_cost: float) -> str:
    if rebuy_cost <= 0.0 or credits < 0.0:
        return "Rebuy ?"
    if credits < rebuy_cost:
        return "NO REBUY"
    if credits < (rebuy_cost * 1.2):
        return "REBUY LOW"
    return "Rebuy OK"


def _max_risk(left: str, right: str) -> str:
    left_norm = _normalize_risk_label(left)
    right_norm = _normalize_risk_label(right)
    if _RISK_RANK[right_norm] > _RISK_RANK[left_norm]:
        return right_norm
    return left_norm


def build_risk_rebuy_contract(payload: dict | None) -> RiskRebuyContract:
    data = dict(payload or {})

    source_risk = _normalize_risk_label(data.get("risk_status"))

    exploration_value = _safe_float(data.get("exploration_value_estimated"))
    exobio_value = _safe_float(data.get("exobio_value_estimated"))
    value_risk = _value_risk_label(
        exploration_value=exploration_value,
        exobio_value=exobio_value,
    )

    risk_label = _max_risk(source_risk, value_risk)

    credits = _safe_float(data.get("credits"))
    rebuy_cost = _safe_float(data.get("rebuy_cost"))
    rebuy_label = _rebuy_label(credits=credits, rebuy_cost=rebuy_cost)

    # Product contract: NO REBUY always critical.
    if rebuy_label == "NO REBUY":
        risk_label = "CRIT"
    # Product contract: REBUY LOW cannot be shown with LOW/MED risk.
    elif rebuy_label == "REBUY LOW" and _RISK_RANK.get(risk_label, 0) < _RISK_RANK["HIGH"]:
        risk_label = "HIGH"

    return RiskRebuyContract(
        risk_label=risk_label,
        rebuy_label=rebuy_label,
        source_risk_label=source_risk,
        value_risk_label=value_risk,
        exploration_value_estimated=max(0.0, exploration_value),
        exobio_value_estimated=max(0.0, exobio_value),
    )
