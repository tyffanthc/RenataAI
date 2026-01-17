from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import config
from logic import utils


_RATING_BY_CLASS_INDEX = {
    "1": "E",
    "2": "D",
    "3": "C",
    "4": "B",
    "5": "A",
}


def _emit_status(level: str, code: str, text: str, *, debug_only: bool = False) -> None:
    if debug_only and not config.get("fit_resolver_debug", False):
        return
    try:
        from gui import common as gui_common  # type: ignore

        gui_common.emit_status(
            level,
            code,
            text=text,
            source="fit_resolver",
            notify_overlay=not debug_only,
        )
    except Exception:
        utils.MSG_QUEUE.put(("log", f"[{level}] {code}: {text}"))


def _log_debug(message: str) -> None:
    if not config.get("fit_resolver_debug", False):
        return
    utils.MSG_QUEUE.put(("log", f"[FIT] {message}"))


def _norm(text: Any) -> str:
    if text is None:
        return ""
    return str(text).strip().lower()


def _parse_class_rating_from_item(item: str) -> Tuple[Optional[int], Optional[str]]:
    if not item:
        return None, None
    item = item.lower()
    size_match = re.search(r"size\s*([1-8])", item)
    class_letter = re.search(r"class\s*([a-e])", item)
    class_digit = re.search(r"class\s*([1-5])", item)
    size = int(size_match.group(1)) if size_match else None
    rating = None
    if class_letter:
        rating = class_letter.group(1).upper()
    elif class_digit:
        rating = _RATING_BY_CLASS_INDEX.get(class_digit.group(1))
    return size, rating


def _extract_class_rating(module: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    item = _norm(module.get("Item"))
    size, rating = _parse_class_rating_from_item(item)
    if size is not None and rating:
        return size, rating

    cls = module.get("Class") if isinstance(module, dict) else None
    if cls is None:
        cls = module.get("class") if isinstance(module, dict) else None
    if cls is not None:
        try:
            size = int(cls)
        except Exception:
            size = None

    rating_val = module.get("Rating") if isinstance(module, dict) else None
    if rating_val is None:
        rating_val = module.get("rating") if isinstance(module, dict) else None
    if rating_val is not None:
        rating_val = str(rating_val).strip().upper()
        if rating_val:
            rating = rating_val

    return size, rating


def _is_fsd_module(module: Dict[str, Any]) -> bool:
    slot = _norm(module.get("Slot"))
    item = _norm(module.get("Item"))
    if "frameshiftdrivebooster" in slot:
        return False
    if "fsdbooster" in item or "guardianfsdbooster" in item:
        return False
    if "frameshiftdrive" in slot:
        return True
    if "frameshiftdrive" in item:
        return True
    if "hyperdrive" in item:
        return True
    if "fsd" in item:
        return True
    return False


def _is_booster_module(module: Dict[str, Any]) -> bool:
    slot = _norm(module.get("Slot"))
    item = _norm(module.get("Item"))
    if "frameshiftdrivebooster" in slot:
        return True
    if "guardianfsdbooster" in item:
        return True
    if "fsdbooster" in item:
        return True
    return False


def _extract_engineering(module: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    engineering = module.get("Engineering")
    if not isinstance(engineering, dict):
        engineering = None

    experimental = None
    if engineering:
        experimental = engineering.get("ExperimentalEffect") or engineering.get(
            "ExperimentalEffect_Localised"
        )
    if experimental is None:
        experimental = module.get("ExperimentalEffect") or module.get(
            "ExperimentalEffect_Localised"
        )
    if experimental is not None:
        experimental = str(experimental).strip() or None
    return engineering, experimental


def _lookup_booster_bonus(
    modules_data: Optional[Dict[str, Any]], booster_class: Optional[int]
) -> float:
    if not modules_data or not booster_class:
        return 0.0
    entries = modules_data.get("guardian_fsd_booster")
    if not isinstance(entries, list):
        return 0.0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("class") == booster_class:
            try:
                return float(entry.get("range_bonus_ly", 0.0))
            except Exception:
                return 0.0
    return 0.0


def resolve_fit_from_loadout(
    modules: List[Dict[str, Any]] | None,
    modules_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if modules is None or not isinstance(modules, list):
        modules = []

    fsd: Dict[str, Any] = {
        "present": False,
        "class": None,
        "rating": None,
        "item": "",
        "engineering": None,
        "experimental": None,
    }
    fsd_booster: Dict[str, Any] = {
        "present": False,
        "class": None,
        "bonus_ly": 0.0,
        "item": "",
    }

    fsd_module = None
    booster_module = None
    for module in modules:
        if not isinstance(module, dict):
            continue
        if fsd_module is None and _is_fsd_module(module):
            fsd_module = module
        if booster_module is None and _is_booster_module(module):
            booster_module = module
        if fsd_module is not None and booster_module is not None:
            break

    if fsd_module:
        fsd["present"] = True
        fsd["item"] = str(fsd_module.get("Item") or "").strip()
        fsd_class, fsd_rating = _extract_class_rating(fsd_module)
        fsd["class"] = fsd_class
        fsd["rating"] = fsd_rating
        engineering, experimental = _extract_engineering(fsd_module)
        fsd["engineering"] = engineering
        fsd["experimental"] = experimental
        _emit_status(
            "INFO",
            "FIT_FSD_FOUND",
            f"FSD: {fsd_class or '-'}{fsd_rating or ''}",
            debug_only=True,
        )
        if fsd_class is None or not fsd_rating:
            _log_debug(f"FSD raw module: {fsd_module}")
    else:
        _emit_status("WARN", "FIT_MISSING_FSD", "Missing FSD in Loadout")

    if booster_module:
        fsd_booster["present"] = True
        fsd_booster["item"] = str(booster_module.get("Item") or "").strip()
        booster_class, _ = _extract_class_rating(booster_module)
        fsd_booster["class"] = booster_class
        fsd_booster["bonus_ly"] = _lookup_booster_bonus(modules_data, booster_class)
        _emit_status(
            "INFO",
            "FIT_BOOSTER_FOUND",
            f"FSD Booster: class={booster_class or '-'} bonus={fsd_booster['bonus_ly']}",
            debug_only=True,
        )
        if booster_class is None:
            _log_debug(f"Booster raw module: {booster_module}")
    else:
        fsd_booster["bonus_ly"] = 0.0

    if not modules_data:
        _emit_status(
            "WARN",
            "FIT_MODULES_DATA_MISSING",
            "Modules data missing - fit readiness limited",
        )

    fit_ready = bool(
        fsd.get("present")
        and fsd.get("class")
        and fsd.get("rating")
        and modules_data
    )
    if fit_ready:
        _emit_status("OK", "FIT_READY", "Fit data ready for JR-4")

    if not fsd.get("present") and config.get("fit_resolver_fail_on_missing", False):
        raise ValueError("FitResolver: missing FSD in Loadout")
    if not modules_data and config.get("fit_resolver_fail_on_missing", False):
        raise ValueError("FitResolver: modules_data missing")

    return {
        "fsd": fsd,
        "fsd_booster": fsd_booster,
        "fit_ready_for_jr": fit_ready,
    }
