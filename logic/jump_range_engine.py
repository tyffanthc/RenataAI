from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import config
from logic.utils import MSG_QUEUE


@dataclass
class JumpRangeResult:
    ok: bool
    jump_range_ly: Optional[float]
    jump_range_limited_by: Optional[str]
    jump_range_fuel_needed_t: Optional[float]
    source: str = "computed"
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


def _log_debug(message: str) -> None:
    if not config.get("jump_range_engine_debug", False):
        return
    MSG_QUEUE.put(("log", f"[JR] {message}"))


def _match_fsd_entry(
    modules_data: Dict[str, Any],
    fsd_class: int,
    fsd_rating: str,
    fsd_item: str,
) -> Optional[Dict[str, Any]]:
    entries = modules_data.get("fsd")
    if not isinstance(entries, list):
        return None

    item_norm = (fsd_item or "").strip().lower()
    wants_overcharge = "overcharge" in item_norm or "sco" in item_norm

    candidates = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("class") == fsd_class
        and str(entry.get("rating") or "").upper() == fsd_rating
    ]
    if not candidates:
        return None

    def _is_overcharge(entry: Dict[str, Any]) -> bool:
        name = str(entry.get("name") or "").lower()
        symbol = str(entry.get("symbol") or "").lower()
        return "overcharge" in name or "sco" in name or "overcharge" in symbol

    if wants_overcharge:
        for entry in candidates:
            if _is_overcharge(entry):
                return entry
    else:
        for entry in candidates:
            if not _is_overcharge(entry):
                return entry

    return candidates[0]


def _normalize_engineering_value(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _apply_engineering_modifiers(
    fsd_params: Dict[str, Any],
    engineering: Optional[Dict[str, Any]],
    experimental: Optional[str],
    modules_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool, str | None]:
    if not config.get("jump_range_engineering_enabled", True):
        return fsd_params, False, None

    params = dict(fsd_params)
    applied = False
    source = None

    modifiers = None
    if isinstance(engineering, dict):
        modifiers = engineering.get("Modifiers") or engineering.get("modifiers")
    if isinstance(modifiers, list):
        for modifier in modifiers:
            if not isinstance(modifier, dict):
                continue
            label = (
                modifier.get("Label")
                or modifier.get("label")
                or modifier.get("Name")
                or modifier.get("name")
            )
            if not label:
                continue
            label_norm = str(label).strip().lower()
            value = _normalize_engineering_value(modifier.get("Value"))
            if value is None:
                value = _normalize_engineering_value(modifier.get("value"))
            if value is None:
                continue
            if "optimal" in label_norm and "mass" in label_norm:
                params["opt_mass"] = value
                applied = True
                source = "modifiers"
            elif "max" in label_norm and "fuel" in label_norm:
                params["max_fuel"] = value
                applied = True
                source = "modifiers"
            elif "fuel" in label_norm and "power" in label_norm:
                params["fuel_power"] = value
                applied = True
                source = "modifiers"
            elif "fuel" in label_norm and "multiplier" in label_norm:
                params["fuel_multiplier"] = value
                applied = True
                source = "modifiers"

    if applied:
        return params, True, source

    mods = modules_data.get("fsd_engineering")
    if isinstance(mods, dict):
        opt_mass_mult = mods.get("opt_mass_multiplier")
        if isinstance(opt_mass_mult, (int, float)):
            params["opt_mass"] = float(params.get("opt_mass", 0.0)) * float(opt_mass_mult)
            applied = True
            source = "modules_data"

        max_fuel_mult = mods.get("max_fuel_multiplier")
        if isinstance(max_fuel_mult, (int, float)):
            params["max_fuel"] = float(params.get("max_fuel", 0.0)) * float(max_fuel_mult)
            applied = True
            source = "modules_data"

        fuel_mult = mods.get("fuel_multiplier")
        if isinstance(fuel_mult, (int, float)):
            params["fuel_multiplier"] = float(params.get("fuel_multiplier", 0.0)) * float(
                fuel_mult
            )
            applied = True
            source = "modules_data"

        fuel_power = mods.get("fuel_power")
        if isinstance(fuel_power, (int, float)):
            params["fuel_power"] = float(fuel_power)
            applied = True
            source = "modules_data"

        if experimental and mods.get("experimental"):
            experimental_mods = mods.get("experimental", {})
            if isinstance(experimental_mods, dict):
                exp_key = str(experimental).strip().lower()
                exp_entry = experimental_mods.get(exp_key)
                if isinstance(exp_entry, dict):
                    exp_opt_mass_mult = exp_entry.get("opt_mass_multiplier")
                    if isinstance(exp_opt_mass_mult, (int, float)):
                        params["opt_mass"] = float(params.get("opt_mass", 0.0)) * float(
                            exp_opt_mass_mult
                        )
                        applied = True
                        source = "modules_data"

    experimental_norm = str(experimental or "").strip().lower()
    if experimental_norm and experimental_norm not in ("none", "null"):
        if "mass manager" in experimental_norm or "mass_manager" in experimental_norm:
            params["opt_mass"] = float(params.get("opt_mass", 0.0)) * 1.04
            applied = True
            source = source or "experimental"
        elif "deep charge" in experimental_norm or "deep_charge" in experimental_norm:
            params["max_fuel"] = float(params.get("max_fuel", 0.0)) * 1.1
            applied = True
            source = source or "experimental"

    return params, applied, source


def _compute_jump_range(
    mass_current_t: float,
    fuel_limit_t: float,
    opt_mass_t: float,
    fuel_power: float,
    fuel_multiplier: float,
) -> Optional[float]:
    if mass_current_t <= 0 or fuel_limit_t <= 0:
        return 0.0
    if opt_mass_t <= 0 or fuel_power <= 0 or fuel_multiplier <= 0:
        return None
    return (fuel_limit_t / fuel_multiplier) ** (1.0 / fuel_power) * (
        opt_mass_t / mass_current_t
    )


def _resolve_fsd_params(
    ship_state: Any, modules_data: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    fsd = getattr(ship_state, "fsd", {}) or {}
    fsd_class = fsd.get("class")
    fsd_rating = fsd.get("rating")
    fsd_item = fsd.get("item") or ""

    if not fsd_class or not fsd_rating:
        return None, None, "missing_fsd"

    try:
        fsd_class = int(fsd_class)
    except Exception:
        return None, None, "invalid_fsd_class"

    fsd_rating = str(fsd_rating).strip().upper()
    if not fsd_rating:
        return None, None, "invalid_fsd_rating"

    entry = _match_fsd_entry(modules_data, fsd_class, fsd_rating, fsd_item)
    if not entry:
        return None, None, "missing_fsd_params"

    try:
        opt_mass_t = float(entry.get("opt_mass", 0.0))
        max_fuel_t = float(entry.get("max_fuel", 0.0))
        fuel_power = float(entry.get("fuel_power", 0.0))
        fuel_multiplier = float(entry.get("fuel_multiplier", 0.0))
    except Exception:
        return None, None, "invalid_fsd_params"

    engineering = fsd.get("engineering")
    experimental = fsd.get("experimental")
    fsd_params = {
        "opt_mass": opt_mass_t,
        "max_fuel": max_fuel_t,
        "fuel_power": fuel_power,
        "fuel_multiplier": fuel_multiplier,
    }
    fsd_params, engineering_applied, engineering_source = _apply_engineering_modifiers(
        fsd_params, engineering, experimental, modules_data
    )

    return (
        fsd_params,
        {
            "engineering_applied": engineering_applied,
            "engineering_source": engineering_source,
            "fsd_symbol": entry.get("symbol"),
        },
        None,
    )


def _compute_jump_range_from_params(
    mass_current_t: float,
    fuel_limit_t: float,
    fsd_params: Dict[str, Any],
) -> Optional[float]:
    try:
        opt_mass_t = float(fsd_params.get("opt_mass", 0.0))
        fuel_power = float(fsd_params.get("fuel_power", 0.0))
        fuel_multiplier = float(fsd_params.get("fuel_multiplier", 0.0))
    except Exception:
        return None
    return _compute_jump_range(
        mass_current_t, fuel_limit_t, opt_mass_t, fuel_power, fuel_multiplier
    )


def compute_jump_range_current(ship_state: Any, modules_data: Dict[str, Any]) -> JumpRangeResult:
    if ship_state is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_ship_state",
        )

    fsd_params, fsd_meta, error = _resolve_fsd_params(ship_state, modules_data)
    if error or not fsd_params or not fsd_meta:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error=error or "missing_fsd_params",
        )

    unladen = getattr(ship_state, "unladen_mass_t", None)
    cargo = getattr(ship_state, "cargo_mass_t", None)
    fuel_main = getattr(ship_state, "fuel_main_t", None)
    fuel_res = getattr(ship_state, "fuel_reservoir_t", None)

    if unladen is None or cargo is None or fuel_main is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_mass_data",
        )

    include_res = bool(config.get("jump_range_include_reservoir_mass", True))
    if include_res and fuel_res is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_reservoir_mass",
        )

    try:
        mass_current_t = float(unladen) + float(cargo) + float(fuel_main)
        if include_res:
            mass_current_t += float(fuel_res or 0.0)
    except Exception:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_mass_data",
        )

    try:
        max_fuel_t = float(fsd_params.get("max_fuel", 0.0))
    except Exception:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_fsd_params",
        )

    fuel_limit_t = min(float(fuel_main), max_fuel_t) if fuel_main is not None else 0.0
    if max_fuel_t <= 0 or fuel_main is None or fuel_main <= 0:
        limited_by = "fuel"
    elif fuel_main < max_fuel_t:
        limited_by = "fuel"
    else:
        limited_by = "mass"

    base_range = _compute_jump_range_from_params(mass_current_t, fuel_limit_t, fsd_params)
    if base_range is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="compute_failed",
        )

    booster = getattr(ship_state, "fsd_booster", {}) or {}
    booster_bonus = 0.0
    try:
        booster_bonus = float(booster.get("bonus_ly", 0.0) or 0.0)
    except Exception:
        booster_bonus = 0.0

    final_range = base_range + booster_bonus if base_range > 0 else 0.0

    rounding = config.get("jump_range_rounding", 2)
    try:
        rounding = int(rounding)
    except Exception:
        rounding = 2

    if rounding is not None and rounding >= 0:
        final_range = round(final_range, rounding)

    _log_debug(
        "JR computed: mass=%.3f fuel=%.3f opt_mass=%.3f max_fuel=%.3f base=%.3f "
        "booster=%.3f final=%.3f limited_by=%s engineering=%s"
        % (
            mass_current_t,
            fuel_limit_t,
            float(fsd_params.get("opt_mass", 0.0)),
            max_fuel_t,
            base_range,
            booster_bonus,
            final_range,
            limited_by,
            "yes" if fsd_meta.get("engineering_applied") else "no",
        )
    )

    return JumpRangeResult(
        ok=True,
        jump_range_ly=final_range,
        jump_range_limited_by=limited_by,
        jump_range_fuel_needed_t=fuel_limit_t,
        source="computed",
        details={
            "base_range_ly": base_range,
            "booster_bonus_ly": booster_bonus,
            "engineering_applied": fsd_meta.get("engineering_applied"),
            "engineering_source": fsd_meta.get("engineering_source"),
            "fsd_symbol": fsd_meta.get("fsd_symbol"),
        },
    )


def compute_jump_range_loadout_max(
    ship_state: Any, modules_data: Dict[str, Any]
) -> JumpRangeResult:
    fsd_params, fsd_meta, error = _resolve_fsd_params(ship_state, modules_data)
    if error or not fsd_params or not fsd_meta:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error=error or "missing_fsd_params",
        )

    unladen = getattr(ship_state, "unladen_mass_t", None)
    if unladen is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_mass_data",
        )

    try:
        max_fuel_t = float(fsd_params.get("max_fuel", 0.0))
    except Exception:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_fsd_params",
        )

    fuel_limit_t = max_fuel_t
    try:
        mass_current_t = float(unladen) + float(fuel_limit_t)
    except Exception:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_mass_data",
        )

    base_range = _compute_jump_range_from_params(mass_current_t, fuel_limit_t, fsd_params)
    if base_range is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="compute_failed",
        )

    booster = getattr(ship_state, "fsd_booster", {}) or {}
    booster_bonus = 0.0
    try:
        booster_bonus = float(booster.get("bonus_ly", 0.0) or 0.0)
    except Exception:
        booster_bonus = 0.0

    final_range = base_range + booster_bonus if base_range > 0 else 0.0

    rounding = config.get("jump_range_rounding", 2)
    try:
        rounding = int(rounding)
    except Exception:
        rounding = 2

    if rounding is not None and rounding >= 0:
        final_range = round(final_range, rounding)

    return JumpRangeResult(
        ok=True,
        jump_range_ly=final_range,
        jump_range_limited_by="mass",
        jump_range_fuel_needed_t=fuel_limit_t,
        source="computed",
        details={
            "base_range_ly": base_range,
            "booster_bonus_ly": booster_bonus,
            "engineering_applied": fsd_meta.get("engineering_applied"),
            "engineering_source": fsd_meta.get("engineering_source"),
            "fsd_symbol": fsd_meta.get("fsd_symbol"),
        },
    )
