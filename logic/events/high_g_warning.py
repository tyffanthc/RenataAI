from __future__ import annotations

from typing import Any

import config
from app.state import app_state
from logic.insight_dispatcher import emit_insight


# Cache last known gravity from body scans so approach/orbit events can announce High-G
# even if the approach payload does not carry `SurfaceGravity`.
_BODY_GRAVITY_CACHE_G: dict[str, float] = {}
_STATUS_ORBIT_CONTEXT_ACTIVE = False


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _resolve_threshold_g() -> float:
    try:
        value = float(config.get("high_g_warning_threshold_g", 2.0) or 2.0)
    except Exception:
        value = 2.0
    return max(0.5, value)


def _normalize_gravity_to_g(raw_value: float) -> float:
    # Journal bywa niespójny (czasem m/s^2, czasem "G"). Powyżej ~5
    # traktujemy wartość jako m/s^2 i przeliczamy na Earth-G.
    if raw_value > 5.0:
        return raw_value / 9.80665
    return raw_value


def _extract_gravity_g(payload: dict[str, Any]) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in (
        "gravity_g",
        "GravityG",
        "SurfaceGravityG",
        "PlanetaryGravityG",
        "Gravity",
        "SurfaceGravity",
        "BodyGravity",
        "PlanetaryGravity",
    ):
        raw = _safe_float(payload.get(key))
        if raw is None:
            continue
        if raw <= 0.0:
            continue
        return _normalize_gravity_to_g(raw)
    return None


def _extract_body_name(payload: dict[str, Any]) -> str:
    body = (
        _as_text(payload.get("BodyName"))
        or _as_text(payload.get("Body"))
        or _as_text(payload.get("BodyID"))
    )
    if body:
        return body
    return _as_text(getattr(app_state, "current_body", "")) or "unknown_body"


def _cache_key(*, system_name: str, body_name: str) -> str:
    return f"{_as_text(system_name).casefold()}::{_as_text(body_name).casefold()}"


def _remember_gravity_g(
    *,
    system_name: str,
    body_name: str,
    gravity_g: float | None,
) -> None:
    if gravity_g is None or gravity_g <= 0.0:
        return
    key = _cache_key(system_name=system_name, body_name=body_name)
    if not key or key == "::":
        return
    _BODY_GRAVITY_CACHE_G[key] = float(gravity_g)


def _lookup_cached_gravity_g(
    *,
    system_name: str,
    body_name: str,
) -> float | None:
    key = _cache_key(system_name=system_name, body_name=body_name)
    if not key or key == "::":
        return None
    raw = _BODY_GRAVITY_CACHE_G.get(key)
    if raw is None:
        return None
    return _safe_float(raw)


def _status_bool(payload: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        text = _as_text(value).lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return None


def _is_orbit_or_glide_entry_status(status_data: dict[str, Any]) -> bool:
    """
    Best-effort detector for orbit approach context from Status.json payload.

    We intentionally avoid relying on a specific Flags/Flags2 bit mapping here because
    payload formats vary across runtimes/parsers. If explicit boolean fields are present,
    emit only on rising edge.
    """
    global _STATUS_ORBIT_CONTEXT_ACTIVE

    if not isinstance(status_data, dict):
        return False

    orbital = _status_bool(status_data, "OrbitalCruise", "InOrbitalCruise", "orbital_cruise")
    glide = _status_bool(status_data, "GlideMode", "InGlide", "glide_mode", "glide")

    current = bool(orbital) or bool(glide)
    rising = current and (not _STATUS_ORBIT_CONTEXT_ACTIVE)
    _STATUS_ORBIT_CONTEXT_ACTIVE = current
    return bool(rising)


def _reset_state_for_tests() -> None:
    global _STATUS_ORBIT_CONTEXT_ACTIVE
    _BODY_GRAVITY_CACHE_G.clear()
    _STATUS_ORBIT_CONTEXT_ACTIVE = False


def _emit_high_g_callout(
    *,
    gravity_g: float,
    body_name: str,
    system_name: str,
    gui_ref=None,
) -> bool:
    raw_text = (
        "Wykryto wysokie przeciazenie grawitacyjne. "
        "Ogranicz opadanie."
    )
    return bool(
        emit_insight(
            raw_text,
            gui_ref=gui_ref,
            message_id="MSG.HIGH_G_WARNING",
            source="high_g_warning",
            event_type="SHIP_HEALTH_CHANGED",
            context={
                "raw_text": raw_text,
                "gravity_g": round(float(gravity_g), 2),
                "body": body_name,
                "system": system_name,
            },
            priority="P1_HIGH",
            dedup_key=f"high_g:{system_name}:{body_name}",
            cooldown_scope="entity",
            cooldown_seconds=120.0,
        )
    )


def handle_journal_event(ev: dict[str, Any], gui_ref=None) -> bool:
    if not bool(config.get("high_g_warning", True)):
        return False
    event_name = _as_text((ev or {}).get("event"))
    if event_name not in {"Scan", "Touchdown", "ApproachBody"}:
        return False

    body_name = _extract_body_name(ev or {})
    system_name = (
        _as_text((ev or {}).get("StarSystem"))
        or _as_text(getattr(app_state, "current_system", ""))
        or "unknown"
    )

    gravity_g = _extract_gravity_g(ev or {})
    if event_name == "Scan":
        _remember_gravity_g(system_name=system_name, body_name=body_name, gravity_g=gravity_g)
        return False

    if gravity_g is None:
        gravity_g = _lookup_cached_gravity_g(system_name=system_name, body_name=body_name)
    if gravity_g is None:
        return False
    if gravity_g < _resolve_threshold_g():
        return False

    # Keep cache fresh if approach/touchdown carried gravity explicitly.
    _remember_gravity_g(system_name=system_name, body_name=body_name, gravity_g=gravity_g)
    return _emit_high_g_callout(
        gravity_g=gravity_g,
        body_name=body_name,
        system_name=system_name,
        gui_ref=gui_ref,
    )


def handle_status_update(status_data: dict[str, Any], gui_ref=None) -> bool:
    if not bool(config.get("high_g_warning", True)):
        return False

    gravity_g = _extract_gravity_g(status_data or {})
    if gravity_g is None:
        return False

    body_name = (
        _as_text((status_data or {}).get("BodyName"))
        or _as_text((status_data or {}).get("Body"))
        or _as_text(getattr(app_state, "current_body", ""))
        or "unknown_body"
    )
    system_name = (
        _as_text((status_data or {}).get("StarSystem"))
        or _as_text(getattr(app_state, "current_system", ""))
        or "unknown"
    )
    _remember_gravity_g(system_name=system_name, body_name=body_name, gravity_g=gravity_g)

    if gravity_g < _resolve_threshold_g():
        return False
    if not _is_orbit_or_glide_entry_status(status_data or {}):
        return False

    return _emit_high_g_callout(
        gravity_g=gravity_g,
        body_name=body_name,
        system_name=system_name,
        gui_ref=gui_ref,
    )
