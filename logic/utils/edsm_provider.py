from __future__ import annotations

from dataclasses import dataclass

from logic.utils.edsm_client import (
    Edsmbadresponse,
    Edsmunavailable,
    Edsmtimeout,
    fetch_system_info,
)
from logic.utils.http_edsm import is_edsm_enabled


@dataclass(frozen=True)
class SystemInfo:
    name: str
    x: float
    y: float
    z: float
    edsm_id: str | None = None
    source: str = "local"


_LOCAL_SYSTEMS: dict[str, SystemInfo] = {}
_LAST_REASON = ""


def _normalize_name(name: str) -> str:
    return " ".join((name or "").strip().split()).lower()


def register_local_system(info: SystemInfo) -> None:
    name = (info.name or "").strip()
    if not name:
        return
    _LOCAL_SYSTEMS[_normalize_name(name)] = info


def clear_local_systems() -> None:
    _LOCAL_SYSTEMS.clear()


def get_last_reason() -> str:
    return _LAST_REASON


def lookup_system(name: str | None) -> SystemInfo | None:
    global _LAST_REASON
    raw = (name or "").strip()
    if not raw:
        _LAST_REASON = "empty_name"
        return None

    norm = _normalize_name(raw)
    local = _LOCAL_SYSTEMS.get(norm)
    if local:
        _LAST_REASON = "local_hit"
        return local

    if not is_edsm_enabled():
        _LAST_REASON = "edsm_disabled"
        return None

    try:
        data = fetch_system_info(raw)
    except Edsmtimeout:
        _LAST_REASON = "edsm_timeout"
        return None
    except Edsmunavailable:
        _LAST_REASON = "edsm_unavailable"
        return None
    except Edsmbadresponse:
        _LAST_REASON = "edsm_bad_response"
        return None
    except Exception:
        _LAST_REASON = "edsm_error"
        return None

    if not isinstance(data, dict):
        _LAST_REASON = "edsm_not_found"
        return None

    name_val = data.get("name")
    x_val = data.get("x")
    y_val = data.get("y")
    z_val = data.get("z")
    if name_val is None or x_val is None or y_val is None or z_val is None:
        _LAST_REASON = "edsm_bad_response"
        return None

    try:
        edsm_id = data.get("edsm_id")
        edsm_id_val = None if edsm_id in (None, "") else str(edsm_id)
        info = SystemInfo(
            name=str(name_val),
            x=float(x_val),
            y=float(y_val),
            z=float(z_val),
            edsm_id=edsm_id_val,
            source="edsm",
        )
    except Exception:
        _LAST_REASON = "edsm_bad_response"
        return None

    _LAST_REASON = "edsm_hit"
    return info
