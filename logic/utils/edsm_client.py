import time
from typing import Any, Dict, List

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
_STATIONS_DETAILS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_NEARBY_SYSTEMS_TTL_SECONDS = 10 * 60
_NEARBY_SYSTEMS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


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


def _stations_details_cache_get(key: str) -> list[dict[str, Any]] | None:
    item = _STATIONS_DETAILS_CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.monotonic() - ts > _STATIONS_TTL_SECONDS:
        _STATIONS_DETAILS_CACHE.pop(key, None)
        return None
    return [dict(row) for row in data]


def _stations_details_cache_set(key: str, data: list[dict[str, Any]]) -> None:
    _STATIONS_DETAILS_CACHE[key] = (time.monotonic(), [dict(row) for row in data])


def _nearby_systems_cache_get(key: str) -> list[dict[str, Any]] | None:
    item = _NEARBY_SYSTEMS_CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.monotonic() - ts > _NEARBY_SYSTEMS_TTL_SECONDS:
        _NEARBY_SYSTEMS_CACHE.pop(key, None)
        return None
    return [dict(row) for row in data if isinstance(row, dict)]


def _nearby_systems_cache_set(key: str, data: list[dict[str, Any]]) -> None:
    _NEARBY_SYSTEMS_CACHE[key] = (time.monotonic(), [dict(row) for row in data if isinstance(row, dict)])


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


def fetch_system_stations_details(
    system_name: str,
    *,
    timeout: float | None = None,
) -> List[Dict[str, Any]]:
    """
    Szczegoly stacji EDSM dla systemu (best-effort schema):
    - name
    - type
    - distance_ls (distanceToArrival)
    - services (otherServices + inferred flags)
    """
    sys_name = (system_name or "").strip()
    if not sys_name:
        return []

    cache_key = f"stations_details:{_normalize_query(sys_name)}"
    cached = _stations_details_cache_get(cache_key)
    if isinstance(cached, list):
        return [dict(item) for item in cached if isinstance(item, dict)]

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
    details: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (
            item.get("name")
            or item.get("station")
            or item.get("stationName")
            or ""
        )
        name = str(name).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)

        services: list[str] = []
        other_services = item.get("otherServices")
        if isinstance(other_services, list):
            for service in other_services:
                if service is None:
                    continue
                text = str(service).strip()
                if text:
                    services.append(text)

        # EDSM bywa niespojne dla fleet carriers; wspieramy oba tropy.
        station_type = str(item.get("type") or "").strip()
        is_fleet_carrier = "carrier" in station_type.lower() or bool(item.get("isFleetCarrier"))
        if is_fleet_carrier:
            station_type = "fleet_carrier"

        row: Dict[str, Any] = {
            "name": name,
            "system": sys_name,
            "type": station_type or "station",
            "distance_ls": item.get("distanceToArrival"),
            "services": services,
            "source": "EDSM",
        }
        details.append(row)

    if details:
        _stations_details_cache_set(cache_key, details)
    return details


def fetch_nearby_systems(
    system_name: str,
    *,
    radius_ly: float = 120.0,
    limit: int = 16,
    timeout: float | None = None,
) -> List[Dict[str, Any]]:
    """
    Pobiera systemy w poblizu podanego systemu (EDSM sphere-systems).
    Zwraca rekordy: {name, distance_ly, x, y, z, source}.
    """
    sys_name = (system_name or "").strip()
    if not sys_name:
        return []

    safe_radius = max(1.0, float(radius_ly or 120.0))
    safe_limit = max(1, int(limit or 16))
    cache_key = (
        f"nearby_systems:{_normalize_query(sys_name)}:"
        f"radius={round(safe_radius, 2)}:limit={safe_limit}"
    )
    cached = _nearby_systems_cache_get(cache_key)
    if isinstance(cached, list):
        return [dict(item) for item in cached if isinstance(item, dict)]

    _throttle()
    url = "https://www.edsm.net/api-v1/sphere-systems"
    headers = {"User-Agent": "RENATA/1.0", "Accept": "application/json"}
    timeout_val = _DEFAULT_TIMEOUT if timeout is None else float(timeout)

    params = {
        "systemName": sys_name,
        "radius": safe_radius,
        "showCoordinates": 1,
    }

    try:
        res = requests.get(
            url,
            params=params,
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

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        candidate = data.get("systems")
        items = candidate if isinstance(candidate, list) else []
    else:
        raise Edsmbadresponse("Unexpected response")

    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    origin_key = sys_name.casefold()
    for item in items:
        if isinstance(item, str):
            name = item.strip()
            if not name:
                continue
            name_key = name.casefold()
            if name_key == origin_key or name_key in seen:
                continue
            seen.add(name_key)
            rows.append(
                {
                    "name": name,
                    "distance_ly": None,
                    "x": None,
                    "y": None,
                    "z": None,
                    "source": "EDSM",
                }
            )
            continue

        if not isinstance(item, dict):
            continue

        name = str(
            item.get("name")
            or item.get("system")
            or item.get("systemName")
            or ""
        ).strip()
        if not name:
            continue
        name_key = name.casefold()
        if name_key == origin_key or name_key in seen:
            continue
        seen.add(name_key)

        coords = item.get("coords") if isinstance(item.get("coords"), dict) else {}
        distance_raw = (
            item.get("distance")
            or item.get("distance_ly")
            or item.get("distanceLy")
            or item.get("dist")
        )
        try:
            distance_ly = float(distance_raw) if distance_raw is not None else None
        except Exception:
            distance_ly = None

        rows.append(
            {
                "name": name,
                "distance_ly": distance_ly,
                "x": coords.get("x"),
                "y": coords.get("y"),
                "z": coords.get("z"),
                "source": "EDSM",
            }
        )

    rows.sort(
        key=lambda row: (
            float(row.get("distance_ly"))
            if row.get("distance_ly") is not None
            else 1e18,
            str(row.get("name") or "").casefold(),
        )
    )
    if len(rows) > safe_limit:
        rows = rows[:safe_limit]

    if rows:
        _nearby_systems_cache_set(cache_key, rows)
    return rows
