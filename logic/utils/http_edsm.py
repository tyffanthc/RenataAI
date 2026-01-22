import config
from logic.cache_store import CacheStore
from logic.utils.notify import DEBOUNCER, MSG_QUEUE
from logic.utils.edsm_client import (
    Edsmbadresponse,
    Edsmunavailable,
    Edsmtimeout,
    fetch_systems,
)


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

    try:
        names = fetch_systems(q)
    except Edsmtimeout as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM timeout: {e}"))
        return []
    except Edsmunavailable as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM unavailable: {e}"))
        return []
    except Edsmbadresponse as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM bad response: {e}"))
        return []
    except Exception as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM lookup failed: {e}"))
        return []

    if names:
        _CACHE.set(cache_key, names, _CACHE_TTL_SECONDS, meta={"query": q})

    return names
