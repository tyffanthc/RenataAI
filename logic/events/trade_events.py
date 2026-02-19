from __future__ import annotations

import time
from typing import Any

import config
from logic.utils import powiedz
from logic import utils
from app.state import app_state
from logic.utils.renata_log import log_event_throttled

# --- MAKLER PRO (S2-LOGIC-06) ---
JACKPOT_WARNED_STATIONS = set()
JACKPOT_DEFAULT = {}
JACKPOT_CACHE = set()
_JACKPOT_WARNED_TS: dict[tuple[str, str], float] = {}
_JACKPOT_CACHE_TS: dict[tuple[str, str, str, int], float] = {}
_JACKPOT_STATE_LOADED = False
_JACKPOT_LAST_PERSIST_TS = 0.0

_JACKPOT_STATE_SCHEMA_VERSION = 1
_JACKPOT_STATE_SECTION = "trade_jackpot_cache"


def _jackpot_ttl_sec() -> float:
    try:
        return max(60.0, float(config.get("anti_spam.trade_jackpot.ttl_sec", 1200.0)))
    except Exception:
        return 1200.0


def _jackpot_max_stations() -> int:
    try:
        return max(16, int(config.get("anti_spam.trade_jackpot.max_stations", 256)))
    except Exception:
        return 256


def _jackpot_max_items() -> int:
    try:
        return max(32, int(config.get("anti_spam.trade_jackpot.max_items", 1024)))
    except Exception:
        return 1024


def _jackpot_persist_min_interval_sec() -> float:
    try:
        return max(0.5, float(config.get("anti_spam.persist_min_interval_sec", 2.0)))
    except Exception:
        return 2.0


def _coerce_ts(value: Any) -> float | None:
    try:
        ts = float(value)
    except Exception:
        return None
    if ts <= 0.0:
        return None
    return ts


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _prune_jackpot_cache(*, now: float | None = None) -> bool:
    global JACKPOT_WARNED_STATIONS, JACKPOT_CACHE
    global _JACKPOT_WARNED_TS, _JACKPOT_CACHE_TS

    changed = False
    ts_now = float(now if now is not None else time.time())
    stale_before = ts_now - _jackpot_ttl_sec()

    stale_stations = [
        key
        for key, ts in list(_JACKPOT_WARNED_TS.items())
        if _coerce_ts(ts) is None or float(ts) < stale_before
    ]
    for key in stale_stations:
        _JACKPOT_WARNED_TS.pop(key, None)
        JACKPOT_WARNED_STATIONS.discard(key)
        changed = True

    stale_items = [
        key
        for key, ts in list(_JACKPOT_CACHE_TS.items())
        if _coerce_ts(ts) is None or float(ts) < stale_before
    ]
    for key in stale_items:
        _JACKPOT_CACHE_TS.pop(key, None)
        JACKPOT_CACHE.discard(key)
        changed = True

    max_stations = _jackpot_max_stations()
    if len(_JACKPOT_WARNED_TS) > max_stations:
        ordered = sorted(_JACKPOT_WARNED_TS.items(), key=lambda item: float(item[1]))
        for key, _ in ordered[: max(0, len(_JACKPOT_WARNED_TS) - max_stations)]:
            _JACKPOT_WARNED_TS.pop(key, None)
            JACKPOT_WARNED_STATIONS.discard(key)
            changed = True

    max_items = _jackpot_max_items()
    if len(_JACKPOT_CACHE_TS) > max_items:
        ordered = sorted(_JACKPOT_CACHE_TS.items(), key=lambda item: float(item[1]))
        for key, _ in ordered[: max(0, len(_JACKPOT_CACHE_TS) - max_items)]:
            _JACKPOT_CACHE_TS.pop(key, None)
            JACKPOT_CACHE.discard(key)
            changed = True

    return changed


def _snapshot_jackpot_cache(*, now: float | None = None) -> dict[str, Any]:
    ts_now = float(now if now is not None else time.time())
    _prune_jackpot_cache(now=ts_now)

    station_entries: list[dict[str, Any]] = []
    for (system_name, station_name), ts in _JACKPOT_WARNED_TS.items():
        station_entries.append(
            {
                "system": system_name,
                "station": station_name,
                "ts": float(ts),
            }
        )
    station_entries.sort(key=lambda row: float(row.get("ts") or 0.0), reverse=True)
    station_entries = station_entries[: _jackpot_max_stations()]

    jackpot_entries: list[dict[str, Any]] = []
    for (system_name, station_name, commodity_key, price), ts in _JACKPOT_CACHE_TS.items():
        jackpot_entries.append(
            {
                "system": system_name,
                "station": station_name,
                "commodity": commodity_key,
                "price": int(price),
                "ts": float(ts),
            }
        )
    jackpot_entries.sort(key=lambda row: float(row.get("ts") or 0.0), reverse=True)
    jackpot_entries = jackpot_entries[: _jackpot_max_items()]

    return {
        "schema_version": _JACKPOT_STATE_SCHEMA_VERSION,
        "updated_at": int(ts_now),
        "station_entries": station_entries,
        "jackpot_entries": jackpot_entries,
    }


def _persist_jackpot_cache(*, force: bool = False) -> bool:
    global _JACKPOT_LAST_PERSIST_TS

    now = time.time()
    if (not force) and (_JACKPOT_LAST_PERSIST_TS > 0.0):
        if (now - _JACKPOT_LAST_PERSIST_TS) < _jackpot_persist_min_interval_sec():
            return False

    payload = _snapshot_jackpot_cache(now=now)
    try:
        config.update_anti_spam_state({_JACKPOT_STATE_SECTION: payload})
        _JACKPOT_LAST_PERSIST_TS = now
        return True
    except Exception:
        return False


def _load_jackpot_cache(*, force: bool = False) -> dict[str, Any]:
    global JACKPOT_WARNED_STATIONS, JACKPOT_CACHE
    global _JACKPOT_WARNED_TS, _JACKPOT_CACHE_TS
    global _JACKPOT_STATE_LOADED

    if _JACKPOT_STATE_LOADED and not force:
        return {"loaded": False, "reason": "already_loaded"}

    payload: dict[str, Any] = {}
    try:
        anti_spam_state = config.get_anti_spam_state(default={})
        raw = anti_spam_state.get(_JACKPOT_STATE_SECTION) if isinstance(anti_spam_state, dict) else {}
        if isinstance(raw, dict):
            payload = raw
    except Exception:
        payload = {}

    loaded_stations: dict[tuple[str, str], float] = {}
    loaded_items: dict[tuple[str, str, str, int], float] = {}

    if isinstance(payload.get("station_entries"), list):
        for row in payload.get("station_entries", []):
            if not isinstance(row, dict):
                continue
            system_name = _norm_text(row.get("system"))
            station_name = _norm_text(row.get("station"))
            ts = _coerce_ts(row.get("ts"))
            if not (system_name and station_name and ts is not None):
                continue
            loaded_stations[(system_name, station_name)] = ts

    if isinstance(payload.get("jackpot_entries"), list):
        for row in payload.get("jackpot_entries", []):
            if not isinstance(row, dict):
                continue
            system_name = _norm_text(row.get("system"))
            station_name = _norm_text(row.get("station"))
            commodity_key = _norm_text(row.get("commodity")).lower()
            ts = _coerce_ts(row.get("ts"))
            try:
                price = int(row.get("price") or 0)
            except Exception:
                price = 0
            if not (system_name and station_name and commodity_key and price > 0 and ts is not None):
                continue
            loaded_items[(system_name, station_name, commodity_key, price)] = ts

    JACKPOT_WARNED_STATIONS = set(loaded_stations.keys())
    JACKPOT_CACHE = set(loaded_items.keys())
    _JACKPOT_WARNED_TS = loaded_stations
    _JACKPOT_CACHE_TS = loaded_items
    _JACKPOT_STATE_LOADED = True
    _prune_jackpot_cache()
    return {
        "loaded": bool(JACKPOT_WARNED_STATIONS or JACKPOT_CACHE),
        "reason": "ok",
        "stations": len(JACKPOT_WARNED_STATIONS),
        "items": len(JACKPOT_CACHE),
    }


def reset_jackpot_runtime_state(*, persist: bool = False) -> None:
    global JACKPOT_WARNED_STATIONS, JACKPOT_CACHE
    global _JACKPOT_WARNED_TS, _JACKPOT_CACHE_TS
    global _JACKPOT_STATE_LOADED, _JACKPOT_LAST_PERSIST_TS

    JACKPOT_WARNED_STATIONS = set()
    JACKPOT_CACHE = set()
    _JACKPOT_WARNED_TS = {}
    _JACKPOT_CACHE_TS = {}
    _JACKPOT_STATE_LOADED = False
    _JACKPOT_LAST_PERSIST_TS = 0.0
    if persist:
        _persist_jackpot_cache(force=True)


def handle_market_data(data: dict, gui_ref=None):
    """
    CZYSTA FUNKCJA GAMEPLAY (Etap B1)
    ---------------------------------
    Przyjmuje dict `data` (odpowiednik Market.json).
    Zero I/O. Zero wczytywania plików.

    Logika 1:1 z handle_market (bez I/O).
    """

    if not config.get("trade_jackpot_speech", True):
        return

    if not isinstance(data, dict):
        return

    items = data.get("Items") or data.get("items") or []
    if not isinstance(items, list):
        return

    _load_jackpot_cache()
    _prune_jackpot_cache()

    station_name = (
        data.get("StationName")
        or data.get("stationName")
        or data.get("Name")
        or "UNKNOWN_STATION"
    )

    system_name = app_state.current_system or data.get("StarSystem") or "UNKNOWN_SYSTEM"

    global JACKPOT_WARNED_STATIONS, JACKPOT_DEFAULT, JACKPOT_CACHE

    jackpot_cfg = config.get("jackpot_thresholds", JACKPOT_DEFAULT)

    thresholds = {
        str(name).lower(): int(val)
        for name, val in jackpot_cfg.items()
        if isinstance(val, (int, float))
    }

    if not thresholds:
        return

    station_key = (system_name, station_name)
    if station_key in JACKPOT_WARNED_STATIONS:
        return

    # SZUKAMY JACKPOTU
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_name = item.get("Name_Localised") or item.get("Name") or ""
        if not raw_name:
            continue

        name_clean = str(raw_name).strip()
        key = name_clean.lower()

        if key not in thresholds:
            continue

        # Realna obecność towaru
        try:
            stock_val = int(item.get("Stock") or 0)
        except (TypeError, ValueError):
            stock_val = 0

        if stock_val <= 0:
            continue

        try:
            buy_price_val = int(item.get("BuyPrice") or 0)
        except (TypeError, ValueError):
            buy_price_val = 0

        if buy_price_val <= 0:
            continue

        jackpot_threshold = thresholds[key]

        # Czy mamy jackpot?
        if buy_price_val < jackpot_threshold:
            jackpot_key = (system_name, station_name, key, buy_price_val)

            # Antyspam (cache)
            if jackpot_key in JACKPOT_CACHE:
                continue

            now_ts = time.time()
            JACKPOT_CACHE.add(jackpot_key)
            JACKPOT_WARNED_STATIONS.add(station_key)
            _JACKPOT_CACHE_TS[jackpot_key] = now_ts
            _JACKPOT_WARNED_TS[station_key] = now_ts

            msg = (
                f"Komandorze, {name_clean} jest tu wyjątkowo tanie. "
                f"To świetna okazja. Cena: {buy_price_val} kredytów."
            )
            powiedz(
                msg,
                gui_ref,
                message_id="MSG.TRADE_JACKPOT",
                context={"raw_text": msg},
            )

            try:
                utils.MSG_QUEUE.put(
                    (
                        "log",
                        f"[MAKLER PRO] JACKPOT na stacji {station_name}: "
                        f"{name_clean} @ {buy_price_val} Cr",
                    )
                )
            except Exception as exc:
                log_event_throttled(
                    "TRADE:jackpot.log",
                    10000,
                    "TRADE",
                    "failed to write jackpot log to queue",
                    error=f"{type(exc).__name__}: {exc}",
                    station=station_name,
                    commodity=name_clean,
                )

            _persist_jackpot_cache()
            break
