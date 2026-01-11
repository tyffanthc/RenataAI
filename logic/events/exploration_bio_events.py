# logic/events/exploration_bio_events.py

from __future__ import annotations

from typing import Any, Dict

from logic.utils import powiedz


# --- DSS BIO ASSISTANT (S2-LOGIC-04) ---
DSS_BIO_WARNED_BODIES = set()  # BodyName/BodyID, dla których już padł komunikat bio


def reset_bio_flags() -> None:
    """Resetuje lokalne flagi anty-spam dla sygnałów biologicznych."""
    global DSS_BIO_WARNED_BODIES
    DSS_BIO_WARNED_BODIES = set()


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
        )
