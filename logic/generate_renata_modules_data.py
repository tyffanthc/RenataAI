from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List

import requests

OUTPUT_FILE = "renata_modules_data.json"
SOURCE_URL = "https://raw.githubusercontent.com/EDCD/coriolis-data/master/dist/modules.json"


def _fetch_json(url: str) -> Any:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _iter_modules(data: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(data, dict):
        for item in data.values():
            if isinstance(item, dict):
                yield item


def _pick_value(module: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in module and module[key] is not None:
            return module[key]
    stats = module.get("stats")
    if isinstance(stats, dict):
        for key in keys:
            if key in stats and stats[key] is not None:
                return stats[key]
    return None


def _build_dataset(data: Any) -> Dict[str, Any]:
    fsd_list: List[Dict[str, Any]] = []
    booster_list: List[Dict[str, Any]] = []

    for module in _iter_modules(data):
        name = str(module.get("name") or module.get("symbol") or "").strip()
        name_lower = name.lower()
        module_class = _pick_value(module, ("class", "size"))
        rating = _pick_value(module, ("rating",))

        if "frame shift drive" in name_lower:
            fsd_list.append(
                {
                    "name": name,
                    "class": module_class,
                    "rating": rating,
                    "opt_mass": _pick_value(module, ("optmass", "optimal_mass")),
                    "max_fuel": _pick_value(module, ("maxfuel", "max_fuel")),
                    "fuel_power": _pick_value(module, ("fuelpower", "fuel_power")),
                    "fuel_multiplier": _pick_value(module, ("fuelmul", "fuel_multiplier")),
                }
            )
            continue

        if "guardian" in name_lower and "fsd booster" in name_lower:
            booster_list.append(
                {
                    "name": name,
                    "class": module_class,
                    "rating": rating,
                    "range_bonus_ly": _pick_value(module, ("range", "boost", "range_bonus")),
                }
            )

    data_out = {
        "version": "v1",
        "generated_at": time.time(),
        "source": SOURCE_URL,
        "fsd": fsd_list,
        "guardian_fsd_booster": booster_list,
        "complete": bool(fsd_list and booster_list),
    }
    return data_out


def generate_modules_data(path: str = OUTPUT_FILE) -> str | None:
    """
    Generuje plik JSON z danymi FSD + booster.
    Zwraca:
        None - OK
        str  - blad (komunikat)
    """
    try:
        raw = _fetch_json(SOURCE_URL)
        data = _build_dataset(raw)
        if not data.get("complete"):
            return "[MODULES_DATA] Brak kompletnych danych (FSD/booster)."

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return None
    except Exception as e:
        return f"[MODULES_DATA] Błąd generowania: {e}"
