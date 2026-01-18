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


def _apply_engineering_modifiers(
    fsd_params: Dict[str, Any],
    engineering: Optional[Dict[str, Any]],
    experimental: Optional[str],
    modules_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    mods = modules_data.get("fsd_engineering")
    if not mods or not engineering:
        return fsd_params, False

    if not isinstance(mods, dict):
        return fsd_params, False

    params = dict(fsd_params)
    applied = False

    opt_mass_mult = mods.get("opt_mass_multiplier")
    if isinstance(opt_mass_mult, (int, float)):
        params["opt_mass"] = float(params.get("opt_mass", 0.0)) * float(opt_mass_mult)
        applied = True

    max_fuel_mult = mods.get("max_fuel_multiplier")
    if isinstance(max_fuel_mult, (int, float)):
        params["max_fuel"] = float(params.get("max_fuel", 0.0)) * float(max_fuel_mult)
        applied = True

    fuel_mult = mods.get("fuel_multiplier")
    if isinstance(fuel_mult, (int, float)):
        params["fuel_multiplier"] = float(params.get("fuel_multiplier", 0.0)) * float(
            fuel_mult
        )
        applied = True

    fuel_power = mods.get("fuel_power")
    if isinstance(fuel_power, (int, float)):
        params["fuel_power"] = float(fuel_power)
        applied = True

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

    return params, applied


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


def compute_jump_range_current(ship_state: Any, modules_data: Dict[str, Any]) -> JumpRangeResult:
    if ship_state is None:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_ship_state",
        )

    fsd = getattr(ship_state, "fsd", {}) or {}
    fsd_class = fsd.get("class")
    fsd_rating = fsd.get("rating")
    fsd_item = fsd.get("item") or ""

    if not fsd_class or not fsd_rating:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_fsd",
        )

    try:
        fsd_class = int(fsd_class)
    except Exception:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_fsd_class",
        )

    fsd_rating = str(fsd_rating).strip().upper()
    if not fsd_rating:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_fsd_rating",
        )

    entry = _match_fsd_entry(modules_data, fsd_class, fsd_rating, fsd_item)
    if not entry:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="missing_fsd_params",
        )

    try:
        opt_mass_t = float(entry.get("opt_mass", 0.0))
        max_fuel_t = float(entry.get("max_fuel", 0.0))
        fuel_power = float(entry.get("fuel_power", 0.0))
        fuel_multiplier = float(entry.get("fuel_multiplier", 0.0))
    except Exception:
        return JumpRangeResult(
            ok=False,
            jump_range_ly=None,
            jump_range_limited_by="unknown",
            jump_range_fuel_needed_t=None,
            error="invalid_fsd_params",
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

    engineering = fsd.get("engineering")
    experimental = fsd.get("experimental")
    fsd_params = {
        "opt_mass": opt_mass_t,
        "max_fuel": max_fuel_t,
        "fuel_power": fuel_power,
        "fuel_multiplier": fuel_multiplier,
    }
    fsd_params, engineering_applied = _apply_engineering_modifiers(
        fsd_params, engineering, experimental, modules_data
    )

    opt_mass_t = float(fsd_params.get("opt_mass", 0.0))
    max_fuel_t = float(fsd_params.get("max_fuel", 0.0))
    fuel_power = float(fsd_params.get("fuel_power", 0.0))
    fuel_multiplier = float(fsd_params.get("fuel_multiplier", 0.0))

    fuel_limit_t = min(float(fuel_main), max_fuel_t) if fuel_main is not None else 0.0
    if max_fuel_t <= 0 or fuel_main is None or fuel_main <= 0:
        limited_by = "fuel"
    elif fuel_main < max_fuel_t:
        limited_by = "fuel"
    else:
        limited_by = "mass"

    base_range = _compute_jump_range(
        mass_current_t, fuel_limit_t, opt_mass_t, fuel_power, fuel_multiplier
    )
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
            opt_mass_t,
            max_fuel_t,
            base_range,
            booster_bonus,
            final_range,
            limited_by,
            "yes" if engineering_applied else "no",
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
            "engineering_applied": engineering_applied,
            "fsd_symbol": entry.get("symbol"),
        },
    )
