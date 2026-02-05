import time
from typing import List

import requests


class Edsmtimeout(Exception):
    pass


class Edsmunavailable(Exception):
    pass


class Edsmbadresponse(Exception):
    pass


_LAST_REQUEST_AT = 0.0
_THROTTLE_MS = 500
_DEFAULT_TIMEOUT = 3.0
_CACHE_TTL_SECONDS = 10 * 60
_CACHE_MAX_ITEMS = 200
_CACHE: dict[str, tuple[float, object]] = {}
_STATIONS_CACHE: dict[str, tuple[float, list[str]]] = {}
_STATIONS_TTL_SECONDS = 24 * 60 * 60


def _normalize_query(query: str) -> str:
    return " ".join((query or "").strip().split()).lower()


def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: str, data) -> None:
    _CACHE[key] = (time.monotonic(), data)
    if len(_CACHE) <= _CACHE_MAX_ITEMS:
        return
    oldest_key = min(_CACHE.items(), key=lambda kv: kv[1][0])[0]
    _CACHE.pop(oldest_key, None)


def _stations_cache_get(key: str) -> list[str] | None:
    item = _STATIONS_CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.monotonic() - ts > _STATIONS_TTL_SECONDS:
        _STATIONS_CACHE.pop(key, None)
        return None
    return list(data)


def _stations_cache_set(key: str, data: list[str]) -> None:
    _STATIONS_CACHE[key] = (time.monotonic(), list(data))


def _throttle() -> None:
    global _LAST_REQUEST_AT
    now = time.monotonic()
    delta_ms = (now - _LAST_REQUEST_AT) * 1000.0
    if delta_ms < _THROTTLE_MS:
        time.sleep(max(0.0, (_THROTTLE_MS - delta_ms) / 1000.0))
    _LAST_REQUEST_AT = time.monotonic()


def fetch_systems(query: str, *, timeout: float | None = None) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []
    cache_key = f"systems:{_normalize_query(q)}"
    cached = _cache_get(cache_key)
    if isinstance(cached, list):
        return [str(item) for item in cached if item]
    _throttle()
    url = "https://www.edsm.net/api-v1/systems"
    headers = {"User-Agent": "RENATA/1.0", "Accept": "application/json"}
    timeout_val = _DEFAULT_TIMEOUT if timeout is None else float(timeout)

    try:
        res = requests.get(
            url,
            params={"systemName": q, "showId": 1},
            headers=headers,
            timeout=timeout_val,
        )
    except requests.Timeout as e:
        raise Edsmtimeout(str(e)) from e
    except requests.RequestException as e:
        raise Edsmunavailable(str(e)) from e

    if res.status_code != 200:
        raise Edsmunavailable(f"HTTP {res.status_code}")

    try:
        data = res.json()
    except Exception as e:
        raise Edsmbadresponse(str(e)) from e

    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]

    names: List[str] = []
    for item in items:
        name = None
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("name") or item.get("system") or item.get("system_name")
        if not name:
            continue
        if name not in names:
            names.append(str(name))

    if len(names) > 50:
        names = names[:50]

    if names:
        _cache_set(cache_key, names)

    return names


def fetch_system_info(query: str, *, timeout: float | None = None) -> dict | None:
    q = (query or "").strip()
    if not q:
        return None
    cache_key = f"system_info:{_normalize_query(q)}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)

    _throttle()
    url = "https://www.edsm.net/api-v1/system"
    headers = {"User-Agent": "RENATA/1.0", "Accept": "application/json"}
    timeout_val = _DEFAULT_TIMEOUT if timeout is None else float(timeout)

    try:
        res = requests.get(
            url,
            params={"systemName": q, "showId": 1, "showCoordinates": 1},
            headers=headers,
            timeout=timeout_val,
        )
    except requests.Timeout as e:
        raise Edsmtimeout(str(e)) from e
    except requests.RequestException as e:
        raise Edsmunavailable(str(e)) from e

    if res.status_code != 200:
        raise Edsmunavailable(f"HTTP {res.status_code}")

    try:
        data = res.json()
    except Exception as e:
        raise Edsmbadresponse(str(e)) from e

    if not isinstance(data, dict):
        raise Edsmbadresponse("Unexpected response")

    name = data.get("name") or data.get("system") or data.get("system_name")
    coords = data.get("coords") if isinstance(data.get("coords"), dict) else {}
    info = {
        "name": name,
        "x": coords.get("x"),
        "y": coords.get("y"),
        "z": coords.get("z"),
        "edsm_id": data.get("id") or data.get("id64"),
    }
    _cache_set(cache_key, dict(info))
    return info


def fetch_system_stations(system_name: str, *, timeout: float | None = None) -> List[str]:
    sys_name = (system_name or "").strip()
    if not sys_name:
        return []

    cache_key = f"stations:{_normalize_query(sys_name)}"
    cached = _stations_cache_get(cache_key)
    if isinstance(cached, list):
        return [str(item) for item in cached if item]

    _throttle()
    url = "https://www.edsm.net/api-system-v1/stations"
    headers = {"User-Agent": "RENATA/1.0", "Accept": "application/json"}
    timeout_val = _DEFAULT_TIMEOUT if timeout is None else float(timeout)

    try:
        res = requests.get(
            url,
            params={"systemName": sys_name},
            headers=headers,
            timeout=timeout_val,
        )
    except requests.Timeout as e:
        raise Edsmtimeout(str(e)) from e
    except requests.RequestException as e:
        raise Edsmunavailable(str(e)) from e

    if res.status_code != 200:
        raise Edsmunavailable(f"HTTP {res.status_code}")

    try:
        data = res.json()
    except Exception as e:
        raise Edsmbadresponse(str(e)) from e

    if not isinstance(data, dict):
        raise Edsmbadresponse("Unexpected response")

    items = data.get("stations") or []
    names: List[str] = []
    for item in items:
        name = None
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("name") or item.get("station") or item.get("stationName")
        if not name:
            continue
        if name not in names:
            names.append(str(name))

    names = sorted(names, key=lambda item: item.lower())
    if len(names) > 200:
        names = names[:200]

    if names:
        _stations_cache_set(cache_key, names)

    return names
