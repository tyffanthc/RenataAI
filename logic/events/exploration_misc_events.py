# logic/events/exploration_misc_events.py

from __future__ import annotations

from typing import Any, Dict

from logic.utils import powiedz


# --- FIRST FOOTFALL (S2-LOGIC-05) ---
FIRST_FOOTFALL_WARNED_BODIES = set()    # ciała, dla których padł komunikat footfall


def reset_footfall_flags() -> None:
    """Resetuje lokalne flagi anty-spam dla first footfall."""
    global FIRST_FOOTFALL_WARNED_BODIES
    FIRST_FOOTFALL_WARNED_BODIES = set()


# --------------------------------------------------
#  FIRST FOOTFALL (S2-LOGIC-05)
# --------------------------------------------------
def handle_first_footfall(ev: Dict[str, Any], gui_ref=None):
    """
    S2-LOGIC-05 — First Footfall detection (Odyssey gdzie dostępne).

    Szukamy sygnałów typu 'FirstFootfall' / podobnych, jeśli są w ev.
    Jeden komunikat na ciało.

    Przeniesione z EventHandler._check_first_footfall.
    """
    global FIRST_FOOTFALL_WARNED_BODIES

    event_name = ev.get("event")
    if event_name not in ("Footfall", "Touchdown", "Disembark"):
        return

    # Nazwy pól mogą się różnić w różnych wersjach – próbujemy kilka
    is_first = bool(
        ev.get("FirstFootfall")
        or ev.get("FirstFootfallOnBody")
        or ev.get("IsFirstFootfall")
    )
    if not is_first:
        return

    body = (
        ev.get("Body")
        or ev.get("BodyName")
        or ev.get("NearestDestination")
    )
    if not body:
        return

    if body in FIRST_FOOTFALL_WARNED_BODIES:
        return

    FIRST_FOOTFALL_WARNED_BODIES.add(body)
    powiedz(
        "Zanotowano pierwszy ludzki krok na tej planecie.",
        gui_ref,
        message_id="MSG.FOOTFALL",
    )
