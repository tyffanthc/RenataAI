from __future__ import annotations

import json
import time
import gzip
from typing import Any, Dict, Iterable, List, Sequence

import requests

OUTPUT_FILE = "renata_modules_data.json"
SOURCE_URLS: Sequence[str] = (
    "https://raw.githubusercontent.com/EDCD/coriolis-data/master/dist/modules.json",
    "https://raw.githubusercontent.com/EDCD/coriolis-data/master/dist/modules.json.gz",
)

FSD_URL = "https://raw.githubusercontent.com/EDCD/coriolis-data/master/modules/standard/frame_shift_drive.json"
BOOSTER_URL = "https://raw.githubusercontent.com/EDCD/coriolis-data/master/modules/internal/guardian_fsd_booster.json"


def _fetch_json(url: str) -> Any:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    if url.endswith(".gz"):
        raw = gzip.decompress(resp.content)
        return json.loads(raw.decode("utf-8"))
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


def _build_dataset_from_files(fsd_data: Any, booster_data: Any) -> Dict[str, Any]:
    fsd_list_raw = []
    booster_list_raw = []

    if isinstance(fsd_data, dict):
        fsd_list_raw = fsd_data.get("fsd") or []
    elif isinstance(fsd_data, list):
        fsd_list_raw = fsd_data

    if isinstance(booster_data, dict):
        booster_list_raw = booster_data.get("gfsb") or []
    elif isinstance(booster_data, list):
        booster_list_raw = booster_data

    fsd_list: List[Dict[str, Any]] = []
    for module in fsd_list_raw:
        if not isinstance(module, dict):
            continue
        fsd_list.append(
            {
                "name": module.get("name") or module.get("ukName") or "FSD",
                "class": module.get("class"),
                "rating": module.get("rating"),
                "opt_mass": module.get("optmass"),
                "max_fuel": module.get("maxfuel"),
                "fuel_power": module.get("fuelpower"),
                "fuel_multiplier": module.get("fuelmul"),
                "symbol": module.get("symbol"),
            }
        )

    booster_list: List[Dict[str, Any]] = []
    for module in booster_list_raw:
        if not isinstance(module, dict):
            continue
        booster_list.append(
            {
                "name": module.get("name") or module.get("ukName") or "Guardian FSD Booster",
                "class": module.get("class"),
                "rating": module.get("rating"),
                "range_bonus_ly": module.get("jumpboost"),
                "symbol": module.get("symbol"),
            }
        )

    data_out = {
        "version": "v1",
        "generated_at": time.time(),
        "source": {"fsd": FSD_URL, "booster": BOOSTER_URL},
        "fsd": fsd_list,
        "guardian_fsd_booster": booster_list,
        "complete": bool(fsd_list and booster_list),
    }
    return data_out


def generate_modules_data(
    path: str = OUTPUT_FILE,
    source_urls: Any | None = None,
) -> str | None:
    """
    Generuje plik JSON z danymi FSD + booster.
    Zwraca:
        None - OK
        str  - blad (komunikat)
    """
    errors: List[str] = []

    if isinstance(source_urls, dict):
        fsd_url = source_urls.get("fsd_url") or FSD_URL
        booster_url = source_urls.get("booster_url") or BOOSTER_URL
        try:
            fsd_data = _fetch_json(fsd_url)
            booster_data = _fetch_json(booster_url)
            data = _build_dataset_from_files(fsd_data, booster_data)
            if not data.get("complete"):
                return "[MODULES_DATA] Brak kompletnych danych (FSD/booster)."

            data["source"] = {"fsd": fsd_url, "booster": booster_url}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return None
        except Exception as e:
            errors.append(f"{fsd_url}/{booster_url}: {e}")

        fallback = source_urls.get("fallback_urls") or []
        source_urls = fallback

    urls = list(source_urls or SOURCE_URLS)
    for url in urls:
        try:
            raw = _fetch_json(url)
            data = _build_dataset(raw)
            if not data.get("complete"):
                return "[MODULES_DATA] Brak kompletnych danych (FSD/booster)."

            data["source"] = url
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return None
        except Exception as e:
            errors.append(f"{url}: {e}")

    return "[MODULES_DATA] Błąd generowania: " + " | ".join(errors)
