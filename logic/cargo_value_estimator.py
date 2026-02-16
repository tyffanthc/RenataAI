from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

import config
from logic.utils.renata_log import log_event_throttled


@dataclass(frozen=True)
class CargoValueEstimate:
    cargo_tons: float
    cargo_floor_cr: float
    cargo_expected_cr: float
    confidence: str
    source: str
    priced_tons: float


_RUNTIME_LOCK = RLock()
_RUNTIME: dict[str, Any] = {
    "market_current": {},
    "market_cache": {},
    "cargo_inventory": {},
    "cargo_tons_hint": 0.0,
    "last_signature": "",
}


def reset_runtime() -> None:
    with _RUNTIME_LOCK:
        _RUNTIME["market_current"] = {}
        _RUNTIME["market_cache"] = {}
        _RUNTIME["cargo_inventory"] = {}
        _RUNTIME["cargo_tons_hint"] = 0.0
        _RUNTIME["last_signature"] = ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _positive_float(value: Any) -> float | None:
    number = _safe_float(value, default=-1.0)
    if number > 0.0:
        return number
    return None


def _normalize_commodity_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return "".join(ch for ch in raw if ch.isalnum())


def _market_price_entry(item: dict[str, Any]) -> tuple[float, float] | None:
    sell = _positive_float(item.get("SellPrice"))
    buy = _positive_float(item.get("BuyPrice"))
    mean = _positive_float(item.get("MeanPrice") or item.get("AveragePrice") or item.get("price"))
    expected = sell or buy or mean
    if expected is None:
        return None
    floor_candidates = [v for v in (sell, buy, mean) if v is not None and v > 0.0]
    floor = min(floor_candidates) if floor_candidates else float(expected)
    return float(expected), float(floor)


def _iter_market_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("Items") or data.get("items") or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _iter_cargo_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = data.get("Inventory") or data.get("Cargo") or data.get("cargo") or []
    if not isinstance(inventory, list):
        return []
    return [item for item in inventory if isinstance(item, dict)]


def _floor_factor(source: str, fallback: float) -> float:
    key = {
        "market": "risk.cargo.floor_factor.market",
        "cache": "risk.cargo.floor_factor.cache",
        "fallback": "risk.cargo.floor_factor.fallback",
    }.get(source, "")
    if not key:
        return float(fallback)
    value = _safe_float(config.get(key, fallback), default=fallback)
    if value <= 0.0:
        return float(fallback)
    if value > 1.0:
        return 1.0
    return float(value)


def _default_unit_price() -> float:
    value = _safe_float(config.get("risk.cargo.default_unit_price_cr", 20_000.0), default=20_000.0)
    if value <= 0.0:
        return 20_000.0
    return float(value)


def _fallback_prices() -> dict[str, float]:
    raw = config.get("risk.cargo.fallback_prices", {})
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, float] = {}
    for key, value in raw.items():
        norm = _normalize_commodity_name(key)
        if not norm:
            continue
        price = _positive_float(value)
        if price is None:
            continue
        parsed[norm] = float(price)
    return parsed


def _median(values: list[float]) -> float | None:
    clean = sorted(v for v in values if v > 0.0)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2 == 1:
        return float(clean[mid])
    return float((clean[mid - 1] + clean[mid]) / 2.0)


def _resolve_overall_confidence(source_hits: dict[str, float]) -> str:
    if source_hits.get("fallback", 0.0) > 0.0:
        return "LOW"
    if source_hits.get("cache", 0.0) > 0.0:
        return "MED"
    return "HIGH"


def _resolve_overall_source(source_hits: dict[str, float]) -> str:
    used = {key for key, value in source_hits.items() if float(value) > 0.0}
    if not used:
        return "none"
    if len(used) == 1:
        return next(iter(used))
    return "mixed"


def _unknown_tons_unit_price(
    *,
    current_prices: dict[str, dict[str, float]],
    cache_prices: dict[str, dict[str, float]],
    default_price: float,
) -> tuple[float, str]:
    current_values = [
        _safe_float(entry.get("expected"), default=0.0)
        for entry in current_prices.values()
        if isinstance(entry, dict)
    ]
    current_median = _median(current_values)
    if current_median is not None:
        return float(current_median), "market"

    cache_values = [
        _safe_float(entry.get("expected"), default=0.0)
        for entry in cache_prices.values()
        if isinstance(entry, dict)
    ]
    cache_median = _median(cache_values)
    if cache_median is not None:
        return float(cache_median), "cache"

    return float(default_price), "fallback"


def update_market_snapshot(data: dict | None, *, source: str = "market_json") -> None:
    if not isinstance(data, dict):
        return

    current_prices: dict[str, dict[str, float]] = {}
    for item in _iter_market_items(data):
        raw_name = item.get("Name_Localised") or item.get("Name") or item.get("name")
        key = _normalize_commodity_name(raw_name)
        if not key:
            continue
        entry = _market_price_entry(item)
        if entry is None:
            continue
        expected, floor = entry
        current_prices[key] = {
            "expected": float(expected),
            "floor": float(max(0.0, floor)),
            "source": str(source),
        }

    with _RUNTIME_LOCK:
        _RUNTIME["market_current"] = current_prices
        cached = dict(_RUNTIME.get("market_cache") or {})
        for key, value in current_prices.items():
            cached[key] = dict(value)
        _RUNTIME["market_cache"] = cached


def update_cargo_snapshot(data: dict | None, *, source: str = "cargo_json") -> None:
    if not isinstance(data, dict):
        return

    cargo_inventory: dict[str, dict[str, Any]] = {}
    for item in _iter_cargo_items(data):
        raw_name = item.get("Name_Localised") or item.get("Name") or item.get("name")
        key = _normalize_commodity_name(raw_name)
        if not key:
            continue
        count = _positive_float(
            item.get("Count")
            or item.get("count")
            or item.get("Amount")
            or item.get("amount")
            or item.get("Qty")
            or item.get("Quantity")
        )
        if count is None or count <= 0.0:
            continue
        entry = cargo_inventory.setdefault(
            key,
            {"name": str(raw_name or key), "tons": 0.0},
        )
        entry["tons"] = float(entry.get("tons", 0.0)) + float(count)

    cargo_tons_hint = 0.0
    for key in ("Cargo", "CargoMass", "Count", "cargo", "cargoMass"):
        value = _positive_float(data.get(key))
        if value is not None:
            cargo_tons_hint = float(value)
            break
    if cargo_tons_hint <= 0.0:
        cargo_tons_hint = sum(float(v.get("tons", 0.0) or 0.0) for v in cargo_inventory.values())

    with _RUNTIME_LOCK:
        _RUNTIME["cargo_inventory"] = cargo_inventory
        _RUNTIME["cargo_tons_hint"] = float(max(0.0, cargo_tons_hint))


def estimate_cargo_value(*, cargo_tons: float | None = None) -> CargoValueEstimate:
    with _RUNTIME_LOCK:
        current_prices = dict(_RUNTIME.get("market_current") or {})
        cache_prices = dict(_RUNTIME.get("market_cache") or {})
        cargo_inventory = dict(_RUNTIME.get("cargo_inventory") or {})
        cargo_tons_hint = _safe_float(_RUNTIME.get("cargo_tons_hint"), default=0.0)

    fallback_prices = _fallback_prices()
    default_unit_price = _default_unit_price()

    reported_tons = max(0.0, _safe_float(cargo_tons, default=0.0))
    if reported_tons <= 0.0:
        reported_tons = max(0.0, cargo_tons_hint)

    source_hits = {"market": 0.0, "cache": 0.0, "fallback": 0.0}
    cargo_expected_cr = 0.0
    cargo_floor_cr = 0.0
    priced_tons = 0.0

    for key, item in cargo_inventory.items():
        if not isinstance(item, dict):
            continue
        tons = max(0.0, _safe_float(item.get("tons"), default=0.0))
        if tons <= 0.0:
            continue

        source_kind = "fallback"
        expected_unit = 0.0
        floor_unit = 0.0

        current_entry = current_prices.get(key)
        cache_entry = cache_prices.get(key)
        fallback_unit = fallback_prices.get(key, default_unit_price)

        if isinstance(current_entry, dict) and _positive_float(current_entry.get("expected")) is not None:
            expected_unit = float(_safe_float(current_entry.get("expected"), default=0.0))
            market_floor = max(0.0, _safe_float(current_entry.get("floor"), default=0.0))
            factor = _floor_factor("market", fallback=0.85)
            candidate_floor = expected_unit * factor
            if market_floor > 0.0:
                floor_unit = min(market_floor, candidate_floor)
            else:
                floor_unit = candidate_floor
            source_kind = "market"
        elif isinstance(cache_entry, dict) and _positive_float(cache_entry.get("expected")) is not None:
            expected_unit = float(_safe_float(cache_entry.get("expected"), default=0.0))
            factor = _floor_factor("cache", fallback=0.70)
            floor_unit = expected_unit * factor
            source_kind = "cache"
        else:
            expected_unit = float(fallback_unit)
            factor = _floor_factor("fallback", fallback=0.55)
            floor_unit = expected_unit * factor
            source_kind = "fallback"

        cargo_expected_cr += expected_unit * tons
        cargo_floor_cr += max(0.0, floor_unit) * tons
        priced_tons += tons
        source_hits[source_kind] = float(source_hits.get(source_kind, 0.0) + tons)

    unknown_tons = max(0.0, reported_tons - priced_tons)
    if unknown_tons > 0.0:
        unit_expected, source_kind = _unknown_tons_unit_price(
            current_prices=current_prices,
            cache_prices=cache_prices,
            default_price=default_unit_price,
        )
        factor = _floor_factor(source_kind if source_kind in {"market", "cache"} else "fallback", fallback=0.55)
        unit_floor = unit_expected * factor
        cargo_expected_cr += unit_expected * unknown_tons
        cargo_floor_cr += unit_floor * unknown_tons
        priced_tons += unknown_tons
        source_hits[source_kind] = float(source_hits.get(source_kind, 0.0) + unknown_tons)

    confidence = _resolve_overall_confidence(source_hits) if reported_tons > 0.0 else "HIGH"
    source = _resolve_overall_source(source_hits) if reported_tons > 0.0 else "none"

    estimate = CargoValueEstimate(
        cargo_tons=max(0.0, reported_tons),
        cargo_floor_cr=max(0.0, cargo_floor_cr),
        cargo_expected_cr=max(0.0, cargo_expected_cr),
        confidence=confidence,
        source=source,
        priced_tons=max(0.0, priced_tons),
    )

    signature = (
        f"{int(estimate.cargo_tons)}:{int(estimate.cargo_floor_cr // 10_000)}:"
        f"{int(estimate.cargo_expected_cr // 10_000)}:{estimate.confidence}:{estimate.source}"
    )
    with _RUNTIME_LOCK:
        if signature != str(_RUNTIME.get("last_signature") or ""):
            _RUNTIME["last_signature"] = signature
            if estimate.cargo_tons > 0.0:
                log_event_throttled(
                    "CARGO_VAR:estimate",
                    1500,
                    "CARGO_VAR",
                    "cargo value-at-risk updated",
                    cargo_tons=int(round(estimate.cargo_tons)),
                    floor_cr=int(round(estimate.cargo_floor_cr)),
                    expected_cr=int(round(estimate.cargo_expected_cr)),
                    confidence=estimate.confidence,
                    source=estimate.source,
                )

    return estimate

