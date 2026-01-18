import config
from logic.utils import powiedz, DEBOUNCER


# --- GLOBAL FLAGS / STATE (paliwo) ---

LOW_FUEL_WARNED = False


def handle_status_update(status: dict, gui_ref=None):
    """
    Czysta funkcja gameplay dla logiki niskiego paliwa.

    Działa WYŁĄCZNIE na przekazanym słowniku `status` (odpowiednik Status.json):
    - nie robi żadnego I/O,
    - nie buduje ścieżek,
    - nie otwiera plików.

    Logika jest 1:1 z poprzednim check_low_fuel, z tą różnicą,
    że dane są już wczytane do dict.

    W ETAPIE C3 dodano lekki anty-spam z użyciem DEBOUNCER:
    - klucz: 'LOW_FUEL'
    - context: nazwa systemu (jeśli dostępna)
    - cooldown: 300 sekund
    """

    # nowa flaga z JSON-a zamiast SETTINGS["FUEL"]
    if not config.get("fuel_warning", True):
        return

    global LOW_FUEL_WARNED

    if not isinstance(status, dict):
        return

    # Jeśli jesteśmy zadokowani – paliwo ignorujemy
    if bool(status.get("Docked")):
        LOW_FUEL_WARNED = False
        return

    # Spróbuj policzyć procent paliwa
    fuel_percent = None
    fuel = status.get("Fuel") or {}
    fuel_main = fuel.get("FuelMain")
    try:
        if fuel_main is not None:
            val = float(fuel_main)
            # Heurystyka: jeśli 0–1 → traktuj jako 0–100%
            if 0.0 <= val <= 1.0:
                fuel_percent = val * 100.0
            else:
                # klasyczny poziom / pojemność, jeśli masz FuelCapacity.Main
                cap = status.get("FuelCapacity") or {}
                cap_main = cap.get("Main")
                if cap_main:
                    fuel_percent = (val / float(cap_main)) * 100.0
    except Exception:
        fuel_percent = None

    # Flaga z gry
    low_fuel_flag = bool(status.get("LowFuel", False))
    if not low_fuel_flag and "Flags" in status:
        try:
            flags = int(status.get("Flags", 0))
            LOW_FUEL_BIT = 1 << 4  # Low Fuel
            low_fuel_flag = bool(flags & LOW_FUEL_BIT)
        except Exception:
            pass

    # Stałe progowe — konfigurowalne w ustawieniach
    try:
        threshold = float(config.get("fuel_warning_threshold_pct", 15))
    except Exception:
        threshold = 15.0
    if threshold not in (15.0, 25.0, 50.0):
        threshold = 15.0

    MIN_FUEL_PERCENT = threshold
    RESET_FUEL_PERCENT = max(30.0, threshold + 10.0)

    if fuel_percent is not None:
        low_fuel = fuel_percent < MIN_FUEL_PERCENT
    else:
        low_fuel = low_fuel_flag

    # Jeśli realnie nisko i jeszcze nie ostrzegaliśmy – mówimy
    if low_fuel and not LOW_FUEL_WARNED:
        # zachowujemy starą logikę flagi (tylko jeden warning do czasu resetu)
        LOW_FUEL_WARNED = True

        # dodatkowy anty-spam DEBOUNCER (na wypadek glitchy Status.json)
        system_name = (
            status.get("StarSystem")
            or status.get("SystemName")
            or None
        )
        if DEBOUNCER.can_send("LOW_FUEL", 300, context=system_name):
            powiedz("Warning. Fuel reserves critical.", gui_ref)

    # Jeśli zatankowano powyżej progu resetu – odblokowujemy alarm
    elif not low_fuel and fuel_percent is not None and fuel_percent > RESET_FUEL_PERCENT:
        LOW_FUEL_WARNED = False
