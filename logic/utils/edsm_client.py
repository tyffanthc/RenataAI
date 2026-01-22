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


def _throttle() -> None:
    global _LAST_REQUEST_AT
    now = time.monotonic()
    delta_ms = (now - _LAST_REQUEST_AT) * 1000.0
    if delta_ms < _THROTTLE_MS:
        time.sleep(max(0.0, (_THROTTLE_MS - delta_ms) / 1000.0))
    _LAST_REQUEST_AT = time.monotonic()


def fetch_systems(query: str, *, timeout: float | None = None) -> List[str]:
    _throttle()
    q = (query or "").strip()
    if not q:
        return []
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

    return names
