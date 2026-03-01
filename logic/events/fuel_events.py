import config
import math
from logic.utils import DEBOUNCER
from logic.insight_dispatcher import emit_insight
from logic.utils.renata_log import log_event_throttled


# --- GLOBAL FLAGS / STATE (paliwo) ---

LOW_FUEL_WARNED = False
LOW_FUEL_FLAG_PENDING = False
LOW_FUEL_FLAG_PENDING_TS = 0.0
_FUEL_STATUS_INITIALIZED = False
_FUEL_SEEN_VALID_SAMPLE = False


def _reset_low_fuel_pending_confirmation() -> None:
    global LOW_FUEL_FLAG_PENDING, LOW_FUEL_FLAG_PENDING_TS
    LOW_FUEL_FLAG_PENDING = False
    LOW_FUEL_FLAG_PENDING_TS = 0.0


def _log_uncertain_startup_sample_ignored(*, reason: str) -> None:
    log_event_throttled(
        f"fuel_startup_uncertain_sample_ignored:{str(reason or 'unknown')}",
        5000,
        "FUEL",
        "fuel startup uncertain sample ignored",
        reason=str(reason or "unknown"),
    )


def _safe_positive_float(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    if out <= 0.0:
        return None
    return float(out)


def _extract_status_fuel_capacity(status: dict) -> float | None:
    cap = (status or {}).get("FuelCapacity") or {}
    if not isinstance(cap, dict):
        return _safe_positive_float(cap)

    main = _safe_positive_float(cap.get("Main") or cap.get("main") or cap.get("FuelMain"))
    reserve = _safe_positive_float(
        cap.get("Reserve")
        or cap.get("Reservoir")
        or cap.get("reserve")
        or cap.get("reservoir")
        or cap.get("FuelReservoir")
    )
    total = float(main or 0.0) + float(reserve or 0.0)
    if total > 0.0:
        return float(total)
    return None


def _resolve_confirmed_fuel_capacity(status: dict) -> float | None:
    status_capacity = _extract_status_fuel_capacity(status)
    if status_capacity is not None:
        try:
            from app.state import app_state

            prev = _safe_positive_float(getattr(app_state, "fuel_capacity", None))
            app_state.fuel_capacity = float(status_capacity)
            config.STATE["fuel_capacity"] = float(status_capacity)
            if prev is None or abs(float(prev) - float(status_capacity)) > 0.0001:
                log_event_throttled(
                    "fuel_capacity_confirmed_from_status",
                    500,
                    "FUEL",
                    "fuel capacity confirmed from status sample",
                    fuel_capacity=float(status_capacity),
                )
        except Exception:
            pass
        return float(status_capacity)

    try:
        from app.state import app_state

        return _safe_positive_float(getattr(app_state, "fuel_capacity", None))
    except Exception:
        return None


def handle_status_update(status: dict, gui_ref=None):
    """
    Czysta logika niskiego paliwa oparta o przekazany dict status.
    Brak I/O, brak odczytu plikow.
    """
    if not config.get("fuel_warning", True):
        return

    global LOW_FUEL_WARNED, LOW_FUEL_FLAG_PENDING, LOW_FUEL_FLAG_PENDING_TS
    global _FUEL_STATUS_INITIALIZED, _FUEL_SEEN_VALID_SAMPLE

    if not isinstance(status, dict):
        return

    if not _FUEL_STATUS_INITIALIZED:
        _FUEL_STATUS_INITIALIZED = True

    # Zadokowany statek -> ignorujemy alert i resetujemy stan.
    if bool(status.get("Docked")):
        LOW_FUEL_WARNED = False
        _FUEL_SEEN_VALID_SAMPLE = False
        _reset_low_fuel_pending_confirmation()
        return

    # Flaga low fuel z gry.
    low_fuel_flag = bool(status.get("LowFuel", False))
    if not low_fuel_flag and "Flags" in status:
        try:
            flags = int(status.get("Flags", 0))
            low_fuel_flag = bool(flags & (1 << 4))
        except (TypeError, ValueError):
            log_event_throttled(
                "fuel_flags_parse",
                10.0,
                "WARN",
                "fuel warning flags parse fallback",
                raw_flags=status.get("Flags"),
            )

    # Proba wyliczenia procentu paliwa.
    fuel_percent = None
    uncertain_low_sample = False
    fuel = status.get("Fuel") or {}
    fuel_main = fuel.get("FuelMain")
    cap = status.get("FuelCapacity") or {}
    cap_main = cap.get("Main")
    has_cap_main = False
    try:
        has_cap_main = bool(cap_main and float(cap_main) > 0.0)
    except (TypeError, ValueError):
        has_cap_main = False
    confirmed_capacity = _resolve_confirmed_fuel_capacity(status)

    # Startup/no-data sample: brak flagi low-fuel + brak danych o paliwie i pojemnosci
    # oznacza brak decyzji diagnostycznej (nie armujemy alertu).
    if fuel_main is None and not low_fuel_flag and not has_cap_main:
        _reset_low_fuel_pending_confirmation()
        _log_uncertain_startup_sample_ignored(reason="missing_fuel_and_capacity")
        return

    try:
        if fuel_main is not None:
            val = float(fuel_main)
            if val > 0.0:
                _FUEL_SEEN_VALID_SAMPLE = True

            # Startup transient: chwilowe zero bez pojemnosci ignorujemy tylko
            # do czasu pierwszej poprawnej probki > 0 po starcie/resecie.
            if (
                val == 0.0
                and not low_fuel_flag
                and not has_cap_main
                and not _FUEL_SEEN_VALID_SAMPLE
            ):
                _reset_low_fuel_pending_confirmation()
                _log_uncertain_startup_sample_ignored(reason="zero_without_capacity")
                return

            # 0..1 traktujemy jako procent 0..100.
            if 0.0 <= val <= 1.0:
                fuel_percent = val * 100.0
                # Przy braku pojemnosci i braku flagi low-fuel traktujemy probe
                # jako niepewna (typowy transient startup/SCO).
                if not low_fuel_flag and not has_cap_main:
                    uncertain_low_sample = True
            elif has_cap_main:
                fuel_percent = (val / float(cap_main)) * 100.0
            elif not low_fuel_flag:
                # Wysoka wartosc bez pojemnosci tez jest niejednoznaczna semantycznie.
                uncertain_low_sample = True
    except (TypeError, ValueError):
        fuel_percent = None

    # Niepewna probka liczbowa (np. transient startup/SCO/launch) bez flagi low-fuel z gry
    # nie moze budowac alertu ani pending-confirmation. Traktujemy jako "brak decyzji".
    if uncertain_low_sample and not low_fuel_flag:
        _reset_low_fuel_pending_confirmation()
        _log_uncertain_startup_sample_ignored(reason="ambiguous_numeric_without_capacity")
        return

    try:
        threshold = float(config.get("fuel_warning_threshold_pct", 15))
    except (TypeError, ValueError):
        threshold = 15.0
    if threshold not in (15.0, 25.0, 50.0):
        threshold = 15.0

    min_fuel_percent = threshold
    reset_fuel_percent = max(30.0, threshold + 10.0)

    low_fuel = (fuel_percent < min_fuel_percent) if fuel_percent is not None else low_fuel_flag

    if low_fuel and not LOW_FUEL_WARNED:
        if confirmed_capacity is None:
            _reset_low_fuel_pending_confirmation()
            _log_uncertain_startup_sample_ignored(reason="fuel_capacity_unconfirmed")
            return

        _reset_low_fuel_pending_confirmation()

        LOW_FUEL_WARNED = True

        system_name = status.get("StarSystem") or status.get("SystemName") or None
        if DEBOUNCER.can_send("LOW_FUEL", 300, context=system_name):
            emit_insight(
                "Warning. Fuel reserves critical.",
                gui_ref=gui_ref,
                message_id="MSG.FUEL_CRITICAL",
                source="fuel_events",
                event_type="SHIP_HEALTH_CHANGED",
                context={
                    "risk_status": "RISK_CRITICAL",
                    "var_status": "VAR_HIGH",
                    "trust_status": "TRUST_HIGH",
                    "confidence": "high",
                    "system": system_name,
                },
                priority="P0_CRITICAL",
                dedup_key=f"low_fuel:{system_name or 'unknown'}",
                cooldown_scope="entity",
                cooldown_seconds=300.0,
                combat_silence_sensitive=False,
            )
        return

    # Reset warning po zatankowaniu.
    if not low_fuel and fuel_percent is not None and fuel_percent > reset_fuel_percent:
        LOW_FUEL_WARNED = False

    # Reset pending, jesli nie ma stanu low fuel.
    if not low_fuel:
        _reset_low_fuel_pending_confirmation()
