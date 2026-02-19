# logic/events/exploration_bio_events.py

from __future__ import annotations

import json
import math
import time
from typing import Any, Dict

import config
from app.state import app_state
from logic.events.exploration_awareness import emit_callout_or_summary
from logic.insight_dispatcher import emit_insight
from logic.utils.renata_log import log_event_throttled


# --- DSS BIO ASSISTANT ---
DSS_BIO_WARNED_BODIES = set()  # BodyName/BodyID with spoken bio warning
EXOBIO_SCAN_WARNED = set()  # (system, body, species)
EXOBIO_CODEX_WARNED = set()  # (system, species)
EXOBIO_SAMPLE_COUNT = {}  # (system, body, species) -> number of saved samples
EXOBIO_SAMPLE_COMPLETE = set()  # (system, body, species) -> sample sequence completed (3/3)
EXOBIO_RANGE_READY_WARNED = set()  # (system, body, species) -> range-ready already spoken
EXOBIO_RANGE_TRACKERS = {}  # (system, body, species) -> distance tracker state
EXOBIO_LAST_STATUS_POS = {}  # last known position from Status.json
EXOBIO_RECOVERY_UNCERTAIN_KEYS = set()  # (system, body, species) -> numbering uncertainty

_EXOBIO_KEY_DELIM = "||"
_EXOBIO_PERSIST_MIN_INTERVAL_SEC = 2.0
_EXOBIO_LAST_PERSIST_TS = 0.0


def _exc_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _log_exobio_fallback(key: str, message: str, exc: Exception, *, interval_ms: int = 10000, **fields) -> None:
    log_event_throttled(
        f"EXOBIO:{key}",
        interval_ms,
        "EXOBIO",
        message,
        error=_exc_text(exc),
        **fields,
    )


def reset_bio_flags(*, persist: bool = False) -> None:
    """Reset local anti-spam flags for biology helpers."""
    global DSS_BIO_WARNED_BODIES, EXOBIO_SCAN_WARNED, EXOBIO_CODEX_WARNED
    global EXOBIO_SAMPLE_COUNT, EXOBIO_SAMPLE_COMPLETE
    global EXOBIO_RANGE_READY_WARNED, EXOBIO_RANGE_TRACKERS, EXOBIO_LAST_STATUS_POS
    global EXOBIO_RECOVERY_UNCERTAIN_KEYS
    DSS_BIO_WARNED_BODIES = set()
    EXOBIO_SCAN_WARNED = set()
    EXOBIO_CODEX_WARNED = set()
    EXOBIO_SAMPLE_COUNT = {}
    EXOBIO_SAMPLE_COMPLETE = set()
    EXOBIO_RANGE_READY_WARNED = set()
    EXOBIO_RANGE_TRACKERS = {}
    EXOBIO_LAST_STATUS_POS = {}
    EXOBIO_RECOVERY_UNCERTAIN_KEYS = set()
    if persist:
        _persist_exobio_state(force=True)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_exobio_key_parts(system_name: Any, body_name: Any, species_name: Any) -> tuple[str, str, str] | None:
    system = _as_text(system_name).lower()
    body = _as_text(body_name).lower()
    species = _as_text(species_name).lower()
    if not system or not body or not species:
        return None
    return system, body, species


def _encode_exobio_key(key: Any) -> str:
    if not isinstance(key, (list, tuple)) or len(key) != 3:
        return ""
    normalized = _normalize_exobio_key_parts(key[0], key[1], key[2])
    if not normalized:
        return ""
    return _EXOBIO_KEY_DELIM.join(normalized)


def _decode_exobio_key(raw: Any) -> tuple[str, str, str] | None:
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        return _normalize_exobio_key_parts(raw[0], raw[1], raw[2])
    token = _as_text(raw)
    if not token:
        return None
    parts = token.split(_EXOBIO_KEY_DELIM, 2)
    if len(parts) != 3:
        return None
    return _normalize_exobio_key_parts(parts[0], parts[1], parts[2])


def _serialize_exobio_key_set(keys: set) -> list[str]:
    out: list[str] = []
    for key in keys or set():
        token = _encode_exobio_key(key)
        if token:
            out.append(token)
    return sorted(set(out))


def _serialize_exobio_sample_count() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key, raw_count in (EXOBIO_SAMPLE_COUNT or {}).items():
        token = _encode_exobio_key(key)
        if not token:
            continue
        try:
            count = int(raw_count or 0)
        except Exception:
            count = 0
        count = max(0, min(3, count))
        out[token] = count
    return out


def _serialize_exobio_trackers() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key, tracker in (EXOBIO_RANGE_TRACKERS or {}).items():
        token = _encode_exobio_key(key)
        if not token or not isinstance(tracker, dict):
            continue
        row: Dict[str, Any] = {}
        for numeric_key in ("threshold_m", "lat", "lon", "radius_m"):
            numeric_value = _as_float(tracker.get(numeric_key))
            if numeric_value is not None:
                row[numeric_key] = numeric_value
        row["pending"] = bool(tracker.get("pending", False))
        body = _as_text(tracker.get("body")).lower()
        system = _as_text(tracker.get("system")).lower()
        if body:
            row["body"] = body
        if system:
            row["system"] = system
        if row:
            out[token] = row
    return out


def _snapshot_exobio_state_payload() -> Dict[str, Any]:
    status_payload: Dict[str, Any] = {}
    last_pos = EXOBIO_LAST_STATUS_POS if isinstance(EXOBIO_LAST_STATUS_POS, dict) else {}
    for numeric_key in ("lat", "lon", "radius_m", "ts"):
        numeric_value = _as_float(last_pos.get(numeric_key))
        if numeric_value is not None:
            status_payload[numeric_key] = numeric_value
    body = _as_text(last_pos.get("body")).lower()
    system = _as_text(last_pos.get("system")).lower()
    if body:
        status_payload["body"] = body
    if system:
        status_payload["system"] = system

    return {
        "schema_version": 1,
        "sample_count_by_key": _serialize_exobio_sample_count(),
        "sample_complete_keys": _serialize_exobio_key_set(EXOBIO_SAMPLE_COMPLETE),
        "range_ready_warned_keys": _serialize_exobio_key_set(EXOBIO_RANGE_READY_WARNED),
        "range_trackers": _serialize_exobio_trackers(),
        "uncertain_sequence_keys": _serialize_exobio_key_set(EXOBIO_RECOVERY_UNCERTAIN_KEYS),
        "last_status_pos": status_payload,
        "updated_at": int(time.time()),
    }


def _persist_exobio_state(*, force: bool = False) -> bool:
    global _EXOBIO_LAST_PERSIST_TS

    now = time.time()
    if (not force) and (_EXOBIO_LAST_PERSIST_TS > 0.0):
        if (now - _EXOBIO_LAST_PERSIST_TS) < _EXOBIO_PERSIST_MIN_INTERVAL_SEC:
            return False

    payload = _snapshot_exobio_state_payload()
    try:
        config.update_anti_spam_state({"exobio": payload})
        _EXOBIO_LAST_PERSIST_TS = now
        return True
    except Exception:
        try:
            config.STATE["exobio_state"] = payload
            _EXOBIO_LAST_PERSIST_TS = now
            return True
        except Exception:
            return False


def _apply_exobio_state_payload(payload: Dict[str, Any]) -> Dict[str, int]:
    global EXOBIO_SAMPLE_COUNT, EXOBIO_SAMPLE_COMPLETE
    global EXOBIO_RANGE_READY_WARNED, EXOBIO_RANGE_TRACKERS, EXOBIO_LAST_STATUS_POS
    global EXOBIO_RECOVERY_UNCERTAIN_KEYS

    sample_count: Dict[tuple[str, str, str], int] = {}
    sample_complete: set[tuple[str, str, str]] = set()
    range_ready_warned: set[tuple[str, str, str]] = set()
    range_trackers: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    uncertain_keys: set[tuple[str, str, str]] = set()

    raw_counts = payload.get("sample_count_by_key", {})
    if isinstance(raw_counts, dict):
        for raw_key, raw_value in raw_counts.items():
            key = _decode_exobio_key(raw_key)
            if not key:
                continue
            try:
                count = int(raw_value or 0)
            except Exception:
                count = 0
            count = max(0, min(3, count))
            if count > 0:
                sample_count[key] = count
            if count >= 3:
                sample_complete.add(key)

    for raw_key in payload.get("sample_complete_keys", []) or []:
        key = _decode_exobio_key(raw_key)
        if not key:
            continue
        sample_complete.add(key)
        sample_count[key] = max(3, int(sample_count.get(key, 0) or 0))

    for raw_key in payload.get("range_ready_warned_keys", []) or []:
        key = _decode_exobio_key(raw_key)
        if key:
            range_ready_warned.add(key)

    for raw_key in payload.get("uncertain_sequence_keys", []) or []:
        key = _decode_exobio_key(raw_key)
        if key:
            uncertain_keys.add(key)

    raw_trackers = payload.get("range_trackers", {})
    if isinstance(raw_trackers, dict):
        for raw_key, raw_tracker in raw_trackers.items():
            key = _decode_exobio_key(raw_key)
            if not key or not isinstance(raw_tracker, dict):
                continue
            row: Dict[str, Any] = {"pending": bool(raw_tracker.get("pending", False))}
            for numeric_key in ("threshold_m", "lat", "lon", "radius_m"):
                numeric_value = _as_float(raw_tracker.get(numeric_key))
                if numeric_value is not None:
                    row[numeric_key] = numeric_value
            body = _as_text(raw_tracker.get("body")).lower()
            system = _as_text(raw_tracker.get("system")).lower()
            if body:
                row["body"] = body
            if system:
                row["system"] = system
            if row:
                range_trackers[key] = row

    status_payload: Dict[str, Any] = {}
    raw_last_status = payload.get("last_status_pos", {})
    if isinstance(raw_last_status, dict):
        for numeric_key in ("lat", "lon", "radius_m", "ts"):
            numeric_value = _as_float(raw_last_status.get(numeric_key))
            if numeric_value is not None:
                status_payload[numeric_key] = numeric_value
        body = _as_text(raw_last_status.get("body")).lower()
        system = _as_text(raw_last_status.get("system")).lower()
        if body:
            status_payload["body"] = body
        if system:
            status_payload["system"] = system

    # Completed sample cycles should not keep active trackers or pending ready-warn flags.
    for key in list(sample_complete):
        range_trackers.pop(key, None)
        range_ready_warned.discard(key)

    EXOBIO_SAMPLE_COUNT = sample_count
    EXOBIO_SAMPLE_COMPLETE = sample_complete
    EXOBIO_RANGE_READY_WARNED = range_ready_warned
    EXOBIO_RANGE_TRACKERS = range_trackers
    EXOBIO_LAST_STATUS_POS = status_payload
    EXOBIO_RECOVERY_UNCERTAIN_KEYS = uncertain_keys

    return {
        "sample_keys": len(EXOBIO_SAMPLE_COUNT),
        "complete_keys": len(EXOBIO_SAMPLE_COMPLETE),
        "tracker_keys": len(EXOBIO_RANGE_TRACKERS),
        "ready_warned_keys": len(EXOBIO_RANGE_READY_WARNED),
    }


def load_exobio_state_from_contract(*, force: bool = False) -> Dict[str, Any]:
    has_runtime_state = bool(
        EXOBIO_SAMPLE_COUNT
        or EXOBIO_SAMPLE_COMPLETE
        or EXOBIO_RANGE_READY_WARNED
        or EXOBIO_RANGE_TRACKERS
    )
    if has_runtime_state and not force:
        return {"loaded": False, "reason": "runtime_state_present"}

    payload: Dict[str, Any] = {}
    try:
        anti_spam_state = config.get_anti_spam_state(default={})
        raw = anti_spam_state.get("exobio") if isinstance(anti_spam_state, dict) else {}
        if isinstance(raw, dict):
            payload = raw
    except Exception:
        payload = {}

    if not payload:
        try:
            raw = config.STATE.get("exobio_state", {})
            if isinstance(raw, dict):
                payload = raw
        except Exception:
            payload = {}

    if not payload:
        return {"loaded": False, "reason": "no_persisted_payload"}

    stats = _apply_exobio_state_payload(payload)
    loaded = bool(stats.get("sample_keys", 0) or stats.get("tracker_keys", 0))
    return {"loaded": loaded, "reason": "ok", **stats}


def recover_exobio_from_journal_lines(
    lines: list[str] | tuple[str, ...] | None,
    *,
    max_lines: int = 4000,
    persist: bool = True,
) -> Dict[str, Any]:
    if not isinstance(lines, (list, tuple)) or not lines:
        return {"recovered": False, "events": 0, "keys": len(EXOBIO_SAMPLE_COUNT)}

    events_recovered = 0
    used_system_fallback = 0
    current_system = _as_text(getattr(app_state, "current_system", ""))

    for raw_line in list(lines)[-max_lines:]:
        try:
            ev = json.loads(raw_line)
        except Exception:
            continue
        if not isinstance(ev, dict):
            continue

        event_name = _as_text(ev.get("event"))
        if event_name in ("Location", "FSDJump", "CarrierJump"):
            next_system = _as_text(ev.get("StarSystem"))
            if next_system:
                current_system = next_system
            continue

        if event_name != "ScanOrganic":
            continue

        species = _species_name(ev)
        body = _as_text(ev.get("BodyName")) or _as_text(ev.get("Body")) or _as_text(ev.get("BodyID"))
        system_name = _as_text(ev.get("StarSystem"))
        used_fallback_for_event = False
        if not system_name:
            system_name = current_system
            if system_name:
                used_system_fallback += 1
                used_fallback_for_event = True

        if not (species and body and system_name):
            continue

        key = (system_name.lower(), body.lower(), species.lower())
        previous = int(EXOBIO_SAMPLE_COUNT.get(key, 0) or 0)
        next_count = max(0, min(3, previous + 1))
        if next_count == previous:
            continue
        EXOBIO_SAMPLE_COUNT[key] = next_count
        events_recovered += 1

        if next_count >= 3:
            EXOBIO_SAMPLE_COMPLETE.add(key)
            EXOBIO_RANGE_TRACKERS.pop(key, None)
            EXOBIO_RANGE_READY_WARNED.discard(key)

        if _is_numeric_token(_as_text(body)) or used_fallback_for_event:
            EXOBIO_RECOVERY_UNCERTAIN_KEYS.add(key)

    if events_recovered and persist:
        _persist_exobio_state(force=True)

    return {
        "recovered": bool(events_recovered),
        "events": events_recovered,
        "keys": len(EXOBIO_SAMPLE_COUNT),
        "used_system_fallback": used_system_fallback,
    }


def bootstrap_exobio_state_from_journal_lines(
    lines: list[str] | tuple[str, ...] | None,
    *,
    max_lines: int = 4000,
) -> Dict[str, Any]:
    loaded = load_exobio_state_from_contract(force=True)
    if bool(loaded.get("loaded")):
        return {"source": "state", **loaded}

    recovered = recover_exobio_from_journal_lines(lines, max_lines=max_lines, persist=True)
    if bool(recovered.get("recovered")):
        return {"source": "journal_recovery", **recovered}
    return {"source": "none", **recovered}


def _current_system(ev: Dict[str, Any]) -> str:
    return _as_text(ev.get("StarSystem")) or _as_text(getattr(app_state, "current_system", ""))


def _current_body(ev: Dict[str, Any]) -> str:
    return (
        _as_text(ev.get("BodyName"))
        or _as_text(ev.get("Body"))
        or _as_text(ev.get("BodyID"))
        or _as_text(ev.get("NearestDestination"))
    )


def _is_numeric_token(value: str) -> bool:
    value = _as_text(value)
    return bool(value and value.isdigit())


def _canonical_body_for_key(ev: Dict[str, Any], system_name: str) -> str:
    """
    Build a stable body key for exobio tracking.
    Prefer body name; when ScanOrganic provides only numeric Body/BodyID,
    reuse last Status body from the same system.
    """
    body_raw = _current_body(ev).lower()
    if body_raw and (not _is_numeric_token(body_raw)):
        return body_raw

    pos = EXOBIO_LAST_STATUS_POS or {}
    pos_body = _as_text(pos.get("body")).lower()
    pos_system = _as_text(pos.get("system")).lower()
    pos_ts = float(pos.get("ts", 0.0) or 0.0)
    # Accept recent status body from the same system.
    if (
        pos_body
        and pos_system
        and system_name.lower() == pos_system
        and (time.time() - pos_ts) <= 120.0
    ):
        return pos_body

    return body_raw


def _species_name(ev: Dict[str, Any]) -> str:
    return (
        _as_text(ev.get("Species_Localised"))
        or _as_text(ev.get("Species"))
        or _as_text(ev.get("Name_Localised"))
        or _as_text(ev.get("Genus_Localised"))
        or _as_text(ev.get("Genus"))
        or _as_text(ev.get("Name"))
    )


def _exobio_context(
    *,
    system_name: str,
    body_name: str,
    species: str = "",
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "raw_text": "",
        "system": system_name,
        "body": body_name,
        "species": species,
        "risk_status": "RISK_LOW",
        "var_status": "VAR_MEDIUM",
        "trust_status": "TRUST_HIGH",
        "confidence": "high",
    }
    source = payload or {}
    for key in ("in_combat", "combat_silence", "combat_state"):
        if key in source:
            ctx[key] = source.get(key)
    return ctx


def _normalize_species_for_science(raw_name: str) -> str:
    if not raw_name:
        return ""
    try:
        engine = getattr(app_state, "system_value_engine", None)
        if engine and hasattr(engine, "_normalize_species_name"):
            normalized = engine._normalize_species_name(raw_name)  # noqa: SLF001 - internal helper
            if normalized:
                return str(normalized).strip()
    except Exception as exc:
        _log_exobio_fallback(
            "species.normalize",
            "failed to normalize species name via SystemValueEngine",
            exc,
        )
    return str(raw_name).strip()


def _species_minimum_distance(species: str) -> float | None:
    """
    Read species minimum distance from Exobiology sheet (Minimum_Distance).
    """
    if not species:
        return None
    try:
        engine = getattr(app_state, "system_value_engine", None)
        if not engine:
            return None

        species_norm = _normalize_species_for_science(species)
        row = None
        if hasattr(engine, "_lookup_exobio_row"):
            row = engine._lookup_exobio_row(species_norm)  # noqa: SLF001 - internal helper
        if row is None:
            return None

        distance = _as_float(row.get("Minimum_Distance"))
        if distance is None or distance <= 0:
            return None
        return distance
    except Exception:
        return None


def _estimate_collected_species_value(ev: Dict[str, Any], species: str) -> tuple[float | None, bool]:
    """
    Estimate collected sample value for a species from science data.
    Returns (value_cr, includes_first_footfall_bonus).
    """
    if not species:
        return None, False
    try:
        engine = getattr(app_state, "system_value_engine", None)
        if not engine or not hasattr(engine, "_lookup_exobio_row"):
            return None, False

        species_norm = _normalize_species_for_science(species)
        if not species_norm:
            return None, False

        row = engine._lookup_exobio_row(species_norm)  # noqa: SLF001 - internal helper
        if row is None:
            return None, False

        base_value = float(_as_float(row.get("Base_Value")) or 0.0)
        fd_bonus = float(_as_float(row.get("First_Discovery_Bonus")) or 0.0)
        total_ff = float(_as_float(row.get("Total_First_Footfall")) or 0.0)

        is_first_discovery = bool(
            ev.get("FirstDiscovery")
            or ev.get("IsNewSpecies")
            or ev.get("NewSpecies")
        )
        is_first_footfall = bool(
            ev.get("FirstFootfall")
            or ev.get("FirstScan")
        )

        value = base_value
        if is_first_discovery and fd_bonus > 0:
            value += fd_bonus

        includes_ff = False
        if is_first_footfall and total_ff > 0:
            extra_ff = max(0.0, total_ff - (base_value + fd_bonus))
            if extra_ff > 0:
                value += extra_ff
                includes_ff = True

        if value <= 0:
            return None, includes_ff
        return value, includes_ff
    except Exception as exc:
        _log_exobio_fallback(
            "value.estimate",
            "failed to estimate exobiology sample value",
            exc,
        )
        return None, False


def _format_cr(value: float | None) -> str:
    if value is None:
        return ""
    try:
        rounded = int(round(float(value)))
    except Exception:
        return ""
    return f"{rounded:,}".replace(",", " ")


def _status_body_name(status: Dict[str, Any]) -> str:
    return _as_text(status.get("BodyName")) or _as_text(status.get("Body"))


def _current_status_system() -> str:
    return _as_text(getattr(app_state, "current_system", ""))


def _is_biology_codex(ev: Dict[str, Any]) -> bool:
    fields = (
        _as_text(ev.get("Name")),
        _as_text(ev.get("Name_Localised")),
        _as_text(ev.get("Category")),
        _as_text(ev.get("SubCategory")),
    )
    joined = " ".join(fields).lower()
    return "codex_ent_biology" in joined or "biology" in joined or "biologia" in joined


def _is_new_codex_entry(ev: Dict[str, Any]) -> bool:
    return bool(
        ev.get("IsNewEntry")
        or ev.get("IsNewDiscovery")
        or ev.get("NewEntry")
        or ev.get("NewDiscoveries")
        or ev.get("FirstDiscovery")
    )


def _spherical_distance_m(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
    radius_m: float,
) -> float:
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))
    return radius_m * c


def _arm_range_tracker(
    key: tuple[str, str, str],
    species: str,
) -> str:
    """
    Arm or queue real distance tracking from last known Status position.
    Returns one of:
    - "armed": tracker has baseline position and can measure distance now
    - "pending": waiting for next valid Status baseline
    - "unavailable": no species threshold in science data
    """
    threshold_m = _species_minimum_distance(species)
    if threshold_m is None:
        return "unavailable"

    pos = EXOBIO_LAST_STATUS_POS or {}
    lat = _as_float(pos.get("lat"))
    lon = _as_float(pos.get("lon"))
    radius_m = _as_float(pos.get("radius_m"))
    pos_body = _as_text(pos.get("body")).lower()
    pos_system = _as_text(pos.get("system")).lower()
    key_system, key_body, _ = key

    tracker = EXOBIO_RANGE_TRACKERS.get(key, {})
    tracker.update(
        {
            "threshold_m": threshold_m,
            "body": key_body,
            "system": key_system,
        }
    )

    pos_is_recent = time.time() - float(pos.get("ts", 0.0) or 0.0) <= 30.0
    body_matches = not (key_body and pos_body and (key_body != pos_body))
    system_matches = not (key_system and pos_system and (key_system != pos_system))

    if (
        lat is not None
        and lon is not None
        and radius_m is not None
        and pos_is_recent
        and body_matches
        and system_matches
    ):
        tracker.update(
            {
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "pending": False,
            }
        )
        EXOBIO_RANGE_TRACKERS[key] = tracker
        EXOBIO_RANGE_READY_WARNED.discard(key)
        return "armed"

    # No immediate baseline: queue and wait for next valid status sample.
    tracker["pending"] = True
    EXOBIO_RANGE_TRACKERS[key] = tracker
    EXOBIO_RANGE_READY_WARNED.discard(key)
    return "pending"


def handle_exobio_status_position(status: Dict[str, Any], gui_ref=None) -> None:
    """
    EXOBIO-DISTANCE-REAL-01:
    Consume live position from Status.json and speak readiness when
    Minimum_Distance threshold is crossed.
    """
    if not config.get("bio_assistant", True):
        return
    if not isinstance(status, dict):
        return

    lat = _as_float(status.get("Latitude"))
    lon = _as_float(status.get("Longitude"))
    radius_m = _as_float(status.get("PlanetRadius"))
    body = _status_body_name(status).lower()
    system = _current_status_system().lower()

    if lat is None or lon is None or radius_m is None:
        return

    state_changed = False
    EXOBIO_LAST_STATUS_POS.update(
        {
            "lat": lat,
            "lon": lon,
            "radius_m": radius_m,
            "body": body,
            "system": system,
            "ts": time.time(),
        }
    )
    state_changed = True

    for key, tracker in list(EXOBIO_RANGE_TRACKERS.items()):
        sample_count = int(EXOBIO_SAMPLE_COUNT.get(key, 0) or 0)
        if sample_count >= 3 or key in EXOBIO_SAMPLE_COMPLETE:
            continue
        if key in EXOBIO_RANGE_READY_WARNED:
            continue

        key_system, key_body, _ = key
        body_mismatch = key_body and body and key_body != body and (not _is_numeric_token(key_body))
        if body_mismatch:
            continue
        if key_system and system and key_system != system:
            continue

        if tracker.get("pending"):
            # First valid status sample after ScanOrganic becomes the baseline.
            tracker["lat"] = lat
            tracker["lon"] = lon
            tracker["radius_m"] = radius_m
            tracker["pending"] = False
            if (not tracker.get("body")) and body:
                tracker["body"] = body
            state_changed = True
            continue

        t_lat = _as_float(tracker.get("lat"))
        t_lon = _as_float(tracker.get("lon"))
        t_radius = _as_float(tracker.get("radius_m"))
        t_threshold = _as_float(tracker.get("threshold_m"))
        if t_lat is None or t_lon is None or t_radius is None or t_threshold is None:
            continue

        distance_m = _spherical_distance_m(
            t_lat,
            t_lon,
            lat,
            lon,
            t_radius,
        )
        if distance_m < t_threshold:
            continue

        EXOBIO_RANGE_READY_WARNED.add(key)
        state_changed = True
        msg = "Osiągnięto odpowiednią odległość. Pobierz kolejną próbkę."
        key_system, key_body, key_species = key
        ctx = _exobio_context(
            system_name=_current_status_system() or key_system,
            body_name=_status_body_name(status) or key_body,
            species=key_species,
            payload=status,
        )
        ctx["raw_text"] = msg
        allow_tts = emit_insight(
            msg,
            gui_ref=gui_ref,
            message_id="MSG.EXOBIO_RANGE_READY",
            source="exploration_bio_events",
            event_type="BIO_PROGRESS",
            context=ctx,
            priority="P2_NORMAL",
            dedup_key=f"exobio_ready:{key_system}:{key_body}:{key_species}",
            cooldown_scope="entity",
            cooldown_seconds=10.0,
        )
        if not allow_tts:
            # Retry on next position update if TTS was suppressed (e.g. combat silence).
            EXOBIO_RANGE_READY_WARNED.discard(key)
            state_changed = True

    if state_changed:
        _persist_exobio_state(force=False)


def handle_dss_bio_signals(ev: Dict[str, Any], gui_ref=None) -> None:
    """
    Event: SAASignalsFound
    If 'Biological' signals >= 3:
      "Potwierdzono liczne sygnały biologiczne. Warto wylądować."
    One message per body.
    """
    if ev.get("event") != "SAASignalsFound":
        return

    body = ev.get("BodyName") or ev.get("Body") or ev.get("BodyID")
    if not body:
        return

    global DSS_BIO_WARNED_BODIES
    if body in DSS_BIO_WARNED_BODIES:
        return

    signals = ev.get("Signals") or []
    if not isinstance(signals, list):
        return

    bio_count = 0
    for s in signals:
        if not isinstance(s, dict):
            continue
        sig_type = str(s.get("Type") or "").lower()
        if "biological" in sig_type:
            try:
                bio_count += int(s.get("Count") or 0)
            except (TypeError, ValueError):
                continue

    if bio_count >= 3:
        DSS_BIO_WARNED_BODIES.add(body)
        msg = "Potwierdzono liczne sygnały biologiczne. Warto wylądować."
        emit_callout_or_summary(
            text=msg,
            gui_ref=gui_ref,
            message_id="MSG.BIO_SIGNALS_HIGH",
            source="exploration_bio_events",
            system_name=_current_system(ev),
            body_name=_as_text(body),
            callout_key=f"bio_signals:{_as_text(body).lower() or 'unknown'}",
            event_type="BODY_DISCOVERED",
            priority="P2_NORMAL",
            context={"raw_text": msg, "body": _as_text(body), "system": _current_system(ev)},
        )


def handle_exobio_progress(ev: Dict[str, Any], gui_ref=None) -> None:
    """
    EXOBIO progress:
    - reacts to ScanOrganic / CodexEntry,
    - provides lightweight exobio context without spam,
    - updates SystemValueEngine for biology events.
    """
    typ = ev.get("event")
    if typ not in ("ScanOrganic", "CodexEntry"):
        return

    # Always update engine, even when TTS is disabled.
    try:
        app_state.system_value_engine.analyze_biology_event(ev)
    except Exception as exc:
        _log_exobio_fallback(
            "engine.analyze_biology",
            "failed to process biology event in SystemValueEngine",
            exc,
        )
    if typ == "CodexEntry":
        try:
            app_state.system_value_engine.analyze_discovery_meta_event(ev)
        except Exception as exc:
            _log_exobio_fallback(
                "engine.analyze_discovery_meta",
                "failed to process discovery meta event in SystemValueEngine",
                exc,
            )

    if not config.get("bio_assistant", True):
        return

    system_name = _current_system(ev)
    species = _species_name(ev)
    body = _canonical_body_for_key(ev, system_name)

    if typ == "ScanOrganic":
        if not species:
            return

        key = (system_name.lower(), body.lower(), species.lower())
        if key in EXOBIO_SAMPLE_COMPLETE:
            return

        previous_count = int(EXOBIO_SAMPLE_COUNT.get(key, 0) or 0)
        if previous_count >= 3:
            EXOBIO_SAMPLE_COMPLETE.add(key)
            _persist_exobio_state(force=True)
            return

        sample_count = previous_count + 1
        EXOBIO_SAMPLE_COUNT[key] = sample_count

        raw_body_token = _as_text(ev.get("BodyName")) or _as_text(ev.get("Body")) or _as_text(ev.get("BodyID"))
        event_uncertain = (not _as_text(ev.get("StarSystem"))) or _is_numeric_token(raw_body_token)
        if event_uncertain:
            EXOBIO_RECOVERY_UNCERTAIN_KEYS.add(key)
        else:
            EXOBIO_RECOVERY_UNCERTAIN_KEYS.discard(key)

        subject = species or body or "obiektu biologicznego"
        sequence_uncertain = key in EXOBIO_RECOVERY_UNCERTAIN_KEYS

        if sample_count == 1:
            if sequence_uncertain:
                msg = f"Kolejna próbka {subject} pobrana."
            else:
                msg = f"Pierwsza próbka {subject} pobrana."
            ctx = _exobio_context(system_name=system_name, body_name=body, species=species, payload=ev)
            ctx["raw_text"] = msg
            emit_insight(
                msg,
                gui_ref=gui_ref,
                message_id="MSG.EXOBIO_SAMPLE_LOGGED",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=ctx,
                priority="P2_NORMAL",
                dedup_key=f"exobio_sample:{system_name}:{body}:{species}:1",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
        elif sample_count == 2:
            if sequence_uncertain:
                msg = f"Kolejna próbka {subject} pobrana."
            else:
                msg = f"Druga próbka {subject} pobrana."
            ctx = _exobio_context(system_name=system_name, body_name=body, species=species, payload=ev)
            ctx["raw_text"] = msg
            emit_insight(
                msg,
                gui_ref=gui_ref,
                message_id="MSG.EXOBIO_SAMPLE_LOGGED",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=ctx,
                priority="P2_NORMAL",
                dedup_key=f"exobio_sample:{system_name}:{body}:{species}:2",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
        elif sample_count >= 3:
            value_cr, includes_ff = _estimate_collected_species_value(ev, species)
            value_text = _format_cr(value_cr)
            if value_text:
                ff_suffix = " (uwzględniono bonus pierwszego kroku)." if includes_ff else "."
                msg = f"Mamy wszystko dla {subject}. Szacowana wartość pobranych próbek: {value_text} kredytów{ff_suffix}"
            else:
                msg = f"Mamy wszystko dla {subject}. Skanowanie gatunku zakończone."
            ctx = _exobio_context(system_name=system_name, body_name=body, species=species, payload=ev)
            ctx["raw_text"] = msg
            emit_insight(
                msg,
                gui_ref=gui_ref,
                message_id="MSG.EXOBIO_SAMPLE_LOGGED",
                source="exploration_bio_events",
                event_type="BIO_PROGRESS",
                context=ctx,
                priority="P2_NORMAL",
                dedup_key=f"exobio_sample:{system_name}:{body}:{species}:3",
                cooldown_scope="entity",
                cooldown_seconds=0.0,
            )
            EXOBIO_SAMPLE_COMPLETE.add(key)
            EXOBIO_SCAN_WARNED.add(key)
            EXOBIO_RANGE_TRACKERS.pop(key, None)
            EXOBIO_RANGE_READY_WARNED.discard(key)
            EXOBIO_RECOVERY_UNCERTAIN_KEYS.discard(key)
            _persist_exobio_state(force=True)
            return

        # Real distance tracker based on science data + status position.
        tracker_state = _arm_range_tracker(key, species) if sample_count < 3 else "complete"

        # Gate message only when real threshold tracking is available from science data.
        if tracker_state == "unavailable":
            EXOBIO_RANGE_TRACKERS.pop(key, None)
            EXOBIO_RANGE_READY_WARNED.discard(key)
        _persist_exobio_state(force=True)
        return

    if not _is_biology_codex(ev):
        return
    if not _is_new_codex_entry(ev):
        return
    if not species:
        return

    codex_key = (system_name.lower(), species.lower())
    if codex_key in EXOBIO_CODEX_WARNED:
        return
    EXOBIO_CODEX_WARNED.add(codex_key)

    msg = f"Nowy wpis biologiczny. {species}."
    ctx = _exobio_context(system_name=system_name, body_name=body, species=species, payload=ev)
    ctx["raw_text"] = msg
    emit_insight(
        msg,
        gui_ref=gui_ref,
        message_id="MSG.EXOBIO_NEW_ENTRY",
        source="exploration_bio_events",
        event_type="BIO_DISCOVERED",
        context=ctx,
        priority="P2_NORMAL",
        dedup_key=f"exobio_codex:{system_name}:{species}",
        cooldown_scope="entity",
        cooldown_seconds=120.0,
    )


try:
    load_exobio_state_from_contract(force=True)
except Exception:
    pass
