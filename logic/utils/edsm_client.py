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
_CACHE: dict[str, tuple[float, list[str]]] = {}


def _normalize_query(query: str) -> str:
    return " ".join((query or "").strip().split()).lower()


def _cache_get(key: str) -> list[str] | None:
    item = _CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return list(data)


def _cache_set(key: str, data: list[str]) -> None:
    _CACHE[key] = (time.monotonic(), list(data))
    if len(_CACHE) <= _CACHE_MAX_ITEMS:
        return
    oldest_key = min(_CACHE.items(), key=lambda kv: kv[1][0])[0]
    _CACHE.pop(oldest_key, None)


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
    cache_key = _normalize_query(q)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
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
