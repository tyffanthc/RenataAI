# logic/events/exploration_bio_events.py

from __future__ import annotations

import math
import time
from typing import Any, Dict

import config
from app.state import app_state
from logic.utils import powiedz
from logic.utils.renata_log import log_event_throttled


# --- DSS BIO ASSISTANT ---
DSS_BIO_WARNED_BODIES = set()  # BodyName/BodyID with spoken bio warning
EXOBIO_SCAN_WARNED = set()  # (system, body, species)
EXOBIO_CODEX_WARNED = set()  # (system, species)
EXOBIO_SAMPLE_COUNT = {}  # (system, body, species) -> number of saved samples
EXOBIO_RANGE_READY_WARNED = set()  # (system, body, species) -> range-ready already spoken
EXOBIO_RANGE_TRACKERS = {}  # (system, body, species) -> distance tracker state
EXOBIO_LAST_STATUS_POS = {}  # last known position from Status.json


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


def reset_bio_flags() -> None:
    """Reset local anti-spam flags for biology helpers."""
    global DSS_BIO_WARNED_BODIES, EXOBIO_SCAN_WARNED, EXOBIO_CODEX_WARNED
    global EXOBIO_SAMPLE_COUNT, EXOBIO_RANGE_READY_WARNED, EXOBIO_RANGE_TRACKERS, EXOBIO_LAST_STATUS_POS
    DSS_BIO_WARNED_BODIES = set()
    EXOBIO_SCAN_WARNED = set()
    EXOBIO_CODEX_WARNED = set()
    EXOBIO_SAMPLE_COUNT = {}
    EXOBIO_RANGE_READY_WARNED = set()
    EXOBIO_RANGE_TRACKERS = {}
    EXOBIO_LAST_STATUS_POS = {}


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

    for key, tracker in list(EXOBIO_RANGE_TRACKERS.items()):
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
        msg = "Odleglosc miedzy probkami potwierdzona. Mozesz skanowac kolejna."
        powiedz(
            msg,
            gui_ref,
            message_id="MSG.EXOBIO_RANGE_READY",
            context={
                "raw_text": msg,
                "system": _current_status_system(),
                "body": _status_body_name(status),
            },
        )


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
        powiedz(
            msg,
            gui_ref,
            message_id="MSG.BIO_SIGNALS_HIGH",
            context={"raw_text": msg},
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
        sample_count = int(EXOBIO_SAMPLE_COUNT.get(key, 0)) + 1
        EXOBIO_SAMPLE_COUNT[key] = sample_count

        # "Sample logged" only once per species/body.
        if key not in EXOBIO_SCAN_WARNED:
            EXOBIO_SCAN_WARNED.add(key)
            if body:
                msg = f"Probka zapisana. {species}. Kontynuuj badania na {body}."
            else:
                msg = f"Probka zapisana. {species}. Kontynuuj badania."
            powiedz(
                msg,
                gui_ref,
                message_id="MSG.EXOBIO_SAMPLE_LOGGED",
                context={"raw_text": msg, "system": system_name, "body": body},
            )

        # Real distance tracker based on science data + status position.
        tracker_state = _arm_range_tracker(key, species)

        # Legacy fallback only when science data does not provide distance threshold.
        if tracker_state == "unavailable" and sample_count == 2 and key not in EXOBIO_RANGE_READY_WARNED:
            EXOBIO_RANGE_READY_WARNED.add(key)
            msg = "Odleglosc miedzy probkami potwierdzona. Mozesz skanowac kolejna."
            powiedz(
                msg,
                gui_ref,
                message_id="MSG.EXOBIO_RANGE_READY",
                context={"raw_text": msg, "system": system_name, "body": body},
            )
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
    powiedz(
        msg,
        gui_ref,
        message_id="MSG.EXOBIO_NEW_ENTRY",
        context={"raw_text": msg, "system": system_name, "body": body},
    )
