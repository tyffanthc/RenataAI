# logic/events/exploration_bio_events.py

from __future__ import annotations

from typing import Any, Dict

import config
from logic.utils import powiedz
from app.state import app_state


# --- DSS BIO ASSISTANT (S2-LOGIC-04) ---
DSS_BIO_WARNED_BODIES = set()  # BodyName/BodyID, dla ktorych juz padl komunikat bio
EXOBIO_SCAN_WARNED = set()  # (system, body, species)
EXOBIO_CODEX_WARNED = set()  # (system, species)
EXOBIO_SAMPLE_COUNT = {}  # (system, body, species) -> liczba zapisanych probek
EXOBIO_RANGE_READY_WARNED = set()  # (system, body, species) -> komunikat "kolejna probka" juz byl


def reset_bio_flags() -> None:
    """Resetuje lokalne flagi anty-spam dla sygnałów biologicznych."""
    global DSS_BIO_WARNED_BODIES, EXOBIO_SCAN_WARNED, EXOBIO_CODEX_WARNED
    global EXOBIO_SAMPLE_COUNT, EXOBIO_RANGE_READY_WARNED
    DSS_BIO_WARNED_BODIES = set()
    EXOBIO_SCAN_WARNED = set()
    EXOBIO_CODEX_WARNED = set()
    EXOBIO_SAMPLE_COUNT = {}
    EXOBIO_RANGE_READY_WARNED = set()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _current_system(ev: Dict[str, Any]) -> str:
    return _as_text(ev.get("StarSystem")) or _as_text(getattr(app_state, "current_system", ""))


def _current_body(ev: Dict[str, Any]) -> str:
    return (
        _as_text(ev.get("BodyName"))
        or _as_text(ev.get("Body"))
        or _as_text(ev.get("BodyID"))
        or _as_text(ev.get("NearestDestination"))
    )


def _species_name(ev: Dict[str, Any]) -> str:
    return (
        _as_text(ev.get("Species_Localised"))
        or _as_text(ev.get("Species"))
        or _as_text(ev.get("Name_Localised"))
        or _as_text(ev.get("Genus_Localised"))
        or _as_text(ev.get("Genus"))
        or _as_text(ev.get("Name"))
    )


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


def handle_dss_bio_signals(ev: Dict[str, Any], gui_ref=None) -> None:
    """
    S2-LOGIC-04 — Asystent biologiczny DSS.

    Event: SAASignalsFound
    Jeśli sygnałów 'Biological' >= 3:
        'Potwierdzono liczne sygnały biologiczne. Warto wylądować.'
    Jeden komunikat na planetę.

    Logika 1:1 z dawnego monolitu exploration (przed podziałem na exploration_*_events).
    """
    if ev.get("event") != "SAASignalsFound":
        return

    body = ev.get("BodyName") or ev.get("Body") or ev.get("BodyID")
    if not body:
        return

    global DSS_BIO_WARNED_BODIES
    # antyspam: tylko raz na planetę
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
            except Exception:
                pass

    if bio_count >= 3:
        DSS_BIO_WARNED_BODIES.add(body)
        powiedz(
            "Potwierdzono liczne sygnały biologiczne. Warto wylądować.",
            gui_ref,
            message_id="MSG.BIO_SIGNALS_HIGH",
            context={"raw_text": "Potwierdzono liczne sygnały biologiczne. Warto wylądować."},
        )


def handle_exobio_progress(ev: Dict[str, Any], gui_ref=None) -> None:
    """
    EXOBIO-GAP-01:
    - reaguje na ScanOrganic / CodexEntry,
    - daje lekki kontekst exobio bez spamu,
    - aktualizuje SystemValueEngine dla biologii.
    """
    typ = ev.get("event")
    if typ not in ("ScanOrganic", "CodexEntry"):
        return

    # Zawsze aktualizuj engine (nawet jesli TTS jest wylaczony).
    try:
        app_state.system_value_engine.analyze_biology_event(ev)
    except Exception:
        pass
    if typ == "CodexEntry":
        try:
            app_state.system_value_engine.analyze_discovery_meta_event(ev)
        except Exception:
            pass

    if not config.get("bio_assistant", True):
        return

    system_name = _current_system(ev)
    species = _species_name(ev)
    body = _current_body(ev)

    if typ == "ScanOrganic":
        if not species:
            return
        key = (system_name.lower(), body.lower(), species.lower())
        sample_count = int(EXOBIO_SAMPLE_COUNT.get(key, 0)) + 1
        EXOBIO_SAMPLE_COUNT[key] = sample_count

        # "Probka zapisana..." wypowiadamy tylko raz na gatunek/cialo.
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

        # EXOBIO-RANGE-01:
        # Przy drugiej zarejestrowanej probce wiemy, ze wymagany dystans
        # zostal osiagniety i mozna szukac kolejnej.
        if sample_count == 2 and key not in EXOBIO_RANGE_READY_WARNED:
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
