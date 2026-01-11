# logic/events/exploration_material_events.py

from __future__ import annotations

from typing import Any, Dict

from logic.utils import powiedz
from app.state import app_state


# --------------------------------------------------
#  MATERIAŁY (MaterialCollected / MaterialDiscarded)
# --------------------------------------------------
def handle_material_collected(ev: Dict[str, Any], gui_ref=None):
    """
    Obsługa eventu MaterialCollected.
    Przeniesione 1:1 z końcówki EventHandler.handle_event.
    """
    m = ev.get("Name")
    if not m:
        return

    inv = app_state.inventory
    key = str(m).lower()
    inv[key] = inv.get(key, 0) + 1
    app_state.set_inventory(inv)
    powiedz(f"Zebrano materiał: {m}", gui_ref)


def handle_material_discarded(ev: Dict[str, Any], gui_ref=None):
    """
    Obsługa eventu MaterialDiscarded.
    Przeniesione 1:1 z końcówki EventHandler.handle_event.
    """
    m = ev.get("Name")
    if not m:
        return

    inv = app_state.inventory
    key = str(m).lower()
    inv[key] = max(inv.get(key, 0) - 1, 0)
    app_state.set_inventory(inv)
