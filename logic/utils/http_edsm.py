import config
from logic.utils.notify import DEBOUNCER, MSG_QUEUE
from logic.utils.edsm_client import (
    Edsmbadresponse,
    Edsmunavailable,
    Edsmtimeout,
    fetch_nearby_systems,
    fetch_system_stations_details,
    fetch_system_stations,
    fetch_systems,
)


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
    return names


def edsm_stations_for_system(system_name: str) -> list[str]:
    if not is_edsm_enabled():
        return []
    sys_name = (system_name or "").strip()
    if not sys_name:
        return []
    if not DEBOUNCER.is_allowed("edsm_stations", cooldown_sec=0.8, context=sys_name.lower()):
        MSG_QUEUE.put(("log", f"[EDSM] stations debounce system={sys_name!r}"))
        return []
    try:
        stations = fetch_system_stations(sys_name)
        MSG_QUEUE.put(("log", f"[EDSM] stations system={sys_name!r} count={len(stations)}"))
        return stations
    except Edsmtimeout as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM timeout: {e}"))
        return []
    except Edsmunavailable as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM unavailable: {e}"))
        return []
    except Edsmbadresponse as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM bad response: {e}"))
        return []
    except Exception as e:  # noqa: BLE001
        MSG_QUEUE.put(("log", f"[WARN] EDSM lookup failed: {e}"))
        return []


def edsm_station_details_for_system(system_name: str) -> list[dict]:
    if not is_edsm_enabled():
        return []
    sys_name = (system_name or "").strip()
    if not sys_name:
        return []
    if not DEBOUNCER.is_allowed("edsm_stations_details", cooldown_sec=0.8, context=sys_name.lower()):
        MSG_QUEUE.put(("log", f"[EDSM] station details debounce system={sys_name!r}"))
        return []
    try:
        rows = fetch_system_stations_details(sys_name)
        MSG_QUEUE.put(("log", f"[EDSM] station details system={sys_name!r} count={len(rows)}"))
        return rows
    except Edsmtimeout as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM timeout: {e}"))
        return []
    except Edsmunavailable as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM unavailable: {e}"))
        return []
    except Edsmbadresponse as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM bad response: {e}"))
        return []
    except Exception as e:  # noqa: BLE001
        MSG_QUEUE.put(("log", f"[WARN] EDSM lookup failed: {e}"))
        return []


def edsm_nearby_systems(
    system_name: str,
    *,
    radius_ly: float = 120.0,
    limit: int = 16,
) -> list[dict]:
    if not is_edsm_enabled():
        return []
    sys_name = (system_name or "").strip()
    if not sys_name:
        return []
    ctx = f"{sys_name.lower()}|{round(float(radius_ly or 120.0), 1)}|{int(limit or 16)}"
    if not DEBOUNCER.is_allowed("edsm_nearby_systems", cooldown_sec=0.8, context=ctx):
        MSG_QUEUE.put(("log", f"[EDSM] nearby debounce system={sys_name!r}"))
        return []
    try:
        rows = fetch_nearby_systems(
            sys_name,
            radius_ly=float(radius_ly or 120.0),
            limit=int(limit or 16),
        )
        MSG_QUEUE.put(
            (
                "log",
                f"[EDSM] nearby systems system={sys_name!r} radius={round(float(radius_ly or 120.0), 1)} count={len(rows)}",
            )
        )
        return rows
    except Edsmtimeout as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM timeout: {e}"))
        return []
    except Edsmunavailable as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM unavailable: {e}"))
        return []
    except Edsmbadresponse as e:
        MSG_QUEUE.put(("log", f"[WARN] EDSM bad response: {e}"))
        return []
    except Exception as e:  # noqa: BLE001
        MSG_QUEUE.put(("log", f"[WARN] EDSM lookup failed: {e}"))
        return []
