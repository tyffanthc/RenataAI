import time

import config
from logic.utils import DEBOUNCER, powiedz


# --- GLOBAL FLAGS / STATE (paliwo) ---

LOW_FUEL_WARNED = False
LOW_FUEL_FLAG_PENDING = False
LOW_FUEL_FLAG_PENDING_TS = 0.0
LOW_FUEL_FLAG_CONFIRM_WINDOW_SEC = 8.0


def handle_status_update(status: dict, gui_ref=None):
    """
    Czysta logika niskiego paliwa oparta o przekazany dict status.
    Brak I/O, brak odczytu plikow.
    """
    if not config.get("fuel_warning", True):
        return

    global LOW_FUEL_WARNED, LOW_FUEL_FLAG_PENDING, LOW_FUEL_FLAG_PENDING_TS

    if not isinstance(status, dict):
        return

    # Zadokowany statek -> ignorujemy alert i resetujemy stan.
    if bool(status.get("Docked")):
        LOW_FUEL_WARNED = False
        LOW_FUEL_FLAG_PENDING = False
        LOW_FUEL_FLAG_PENDING_TS = 0.0
        return

    # Flaga low fuel z gry.
    low_fuel_flag = bool(status.get("LowFuel", False))
    if not low_fuel_flag and "Flags" in status:
        try:
            flags = int(status.get("Flags", 0))
            low_fuel_flag = bool(flags & (1 << 4))
        except Exception:
            pass

    # Proba wyliczenia procentu paliwa.
    fuel_percent = None
    fuel = status.get("Fuel") or {}
    fuel_main = fuel.get("FuelMain")
    cap = status.get("FuelCapacity") or {}
    cap_main = cap.get("Main")
    try:
        if fuel_main is not None:
            val = float(fuel_main)

            # Startup transient: czasami dostajemy chwilowe zero bez pojemnosci.
            if (
                val == 0.0
                and not low_fuel_flag
                and not (cap_main and float(cap_main) > 0.0)
            ):
                return

            # 0..1 traktujemy jako procent 0..100.
            if 0.0 <= val <= 1.0:
                fuel_percent = val * 100.0
            elif cap_main:
                fuel_percent = (val / float(cap_main)) * 100.0
    except Exception:
        fuel_percent = None

    try:
        threshold = float(config.get("fuel_warning_threshold_pct", 15))
    except Exception:
        threshold = 15.0
    if threshold not in (15.0, 25.0, 50.0):
        threshold = 15.0

    min_fuel_percent = threshold
    reset_fuel_percent = max(30.0, threshold + 10.0)

    low_fuel = (fuel_percent < min_fuel_percent) if fuel_percent is not None else low_fuel_flag

    if low_fuel and not LOW_FUEL_WARNED:
        # Dla "flag-only" (bez wyliczonego procentu) wymagamy potwierdzenia
        # druga probka low_fuel w oknie czasu.
        if fuel_percent is None:
            now = time.time()
            if not LOW_FUEL_FLAG_PENDING:
                LOW_FUEL_FLAG_PENDING = True
                LOW_FUEL_FLAG_PENDING_TS = now
                return
            if (now - LOW_FUEL_FLAG_PENDING_TS) > LOW_FUEL_FLAG_CONFIRM_WINDOW_SEC:
                LOW_FUEL_FLAG_PENDING_TS = now
                return
            LOW_FUEL_FLAG_PENDING = False
            LOW_FUEL_FLAG_PENDING_TS = 0.0

        LOW_FUEL_WARNED = True

        system_name = status.get("StarSystem") or status.get("SystemName") or None
        if DEBOUNCER.can_send("LOW_FUEL", 300, context=system_name):
            powiedz(
                "Warning. Fuel reserves critical.",
                gui_ref,
                message_id="MSG.FUEL_CRITICAL",
            )
        return

    # Reset warning po zatankowaniu.
    if not low_fuel and fuel_percent is not None and fuel_percent > reset_fuel_percent:
        LOW_FUEL_WARNED = False

    # Reset pending, jesli nie ma stanu low fuel.
    if not low_fuel:
        LOW_FUEL_FLAG_PENDING = False
        LOW_FUEL_FLAG_PENDING_TS = 0.0
