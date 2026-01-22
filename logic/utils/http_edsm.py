import requests
import config
from logic.cache_store import CacheStore
from logic.utils.notify import DEBOUNCER, MSG_QUEUE


_CACHE = CacheStore(namespace="edsm", provider="edsm")
_CACHE_TTL_SECONDS = 60 * 60


def is_edsm_enabled() -> bool:
    return bool(config.get("features.providers.edsm_enabled", False))


def edsm_systems_suggest(query: str) -> list[str]:
    if not is_edsm_enabled():
        return []

    q = (query or "").strip()
    if q.startswith("-"):
        q = q[1:].strip()
    if len(q) < 2:
        return []

    if not DEBOUNCER.is_allowed("edsm_systems", cooldown_sec=0.8, context=q.lower()):
        return []

    cache_key = f"systems:{q.lower()}"
    hit, cached, _meta = _CACHE.get(cache_key)
    if hit and isinstance(cached, list):
        return [str(item) for item in cached if item]

    url = "https://www.edsm.net/api-v1/systems"
    headers = {"User-Agent": "RENATA/1.0", "Accept": "application/json"}

    try:
        res = requests.get(
            url,
            params={"systemName": q, "showId": 1},
            headers=headers,
            timeout=4,
        )
    except Exception as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM lookup failed: {e}"))
        return []

    if res.status_code != 200:
        MSG_QUEUE.put(("log", f"[WARN] EDSM HTTP {res.status_code} for {q!r}"))
        return []

    try:
        data = res.json()
    except Exception as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM JSON error: {e}"))
        return []

    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]

    names: list[str] = []
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
        _CACHE.set(cache_key, names, _CACHE_TTL_SECONDS, meta={"query": q})

    return names
