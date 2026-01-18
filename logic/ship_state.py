from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config
from logic.utils import MSG_QUEUE, DEBOUNCER


@dataclass
class ShipState:
    ship_id: Optional[int] = None
    ship_type: Optional[str] = None
    unladen_mass_t: Optional[float] = None
    cargo_mass_t: Optional[float] = None
    fuel_main_t: Optional[float] = None
    fuel_reservoir_t: Optional[float] = None
    modules: List[Dict[str, Any]] = field(default_factory=list)
    fsd: Dict[str, Any] = field(
        default_factory=lambda: {
            "present": False,
            "class": None,
            "rating": None,
            "item": "",
            "engineering": None,
            "experimental": None,
        }
    )
    fsd_booster: Dict[str, Any] = field(
        default_factory=lambda: {
            "present": False,
            "class": None,
            "bonus_ly": 0.0,
            "item": "",
        }
    )
    fit_ready_for_jr: bool = False
    jump_range_current_ly: Optional[float] = None
    jump_range_current_source: Optional[str] = None
    jump_range_last_calc_at: Optional[float] = None
    jump_range_limited_by: Optional[str] = None
    jump_range_fuel_needed_t: Optional[float] = None
    loadout_max_jump_range_ly: Optional[float] = None
    jump_range_validate_delta_ly: Optional[float] = None
    _jump_range_last_status_code: Optional[str] = None

    last_update_ts: Optional[float] = None
    last_update_by: Dict[str, float] = field(default_factory=dict)

    def _log_debug(self, message: str) -> None:
        if not config.get("ship_state_debug", False):
            return
        MSG_QUEUE.put(("log", f"[SHIPSTATE] {message}"))

    def _mark_updated(self, source: str) -> None:
        now = time.time()
        self.last_update_ts = now
        self.last_update_by[source] = now

    def _emit_update(self) -> None:
        payload = {
            "ship_id": self.ship_id,
            "ship_type": self.ship_type,
            "unladen_mass_t": self.unladen_mass_t,
            "cargo_mass_t": self.cargo_mass_t,
            "fuel_main_t": self.fuel_main_t,
            "fuel_reservoir_t": self.fuel_reservoir_t,
            "fsd": self.fsd,
            "fsd_booster": self.fsd_booster,
            "fit_ready_for_jr": self.fit_ready_for_jr,
            "jump_range_current_ly": self.jump_range_current_ly,
            "jump_range_current_source": self.jump_range_current_source,
            "jump_range_last_calc_at": self.jump_range_last_calc_at,
            "jump_range_limited_by": self.jump_range_limited_by,
            "jump_range_fuel_needed_t": self.jump_range_fuel_needed_t,
            "loadout_max_jump_range_ly": self.loadout_max_jump_range_ly,
            "jump_range_validate_delta_ly": self.jump_range_validate_delta_ly,
            "completeness": self.get_completeness(),
            "ts": self.last_update_ts,
        }
        MSG_QUEUE.put(("ship_state", payload))

    def _should_compute_jump_range(self, trigger: str) -> bool:
        if not config.get("jump_range_engine_enabled", True):
            return False
        mode = str(config.get("jump_range_compute_on", "both")).strip().lower()
        if mode == "both":
            return True
        if mode == "loadout" and trigger == "loadout":
            return True
        if mode == "status_change" and trigger == "status_change":
            return True
        return False

    def _emit_jump_range_status(
        self,
        level: str,
        code: str,
        text: str | None = None,
        *,
        debug_only: bool = False,
        notify_overlay: bool | None = None,
    ) -> None:
        if debug_only and not config.get("jump_range_engine_debug", False):
            return
        if code == self._jump_range_last_status_code and not debug_only:
            return
        self._jump_range_last_status_code = code
        if notify_overlay is None:
            notify_overlay = not debug_only
        try:
            from gui import common as gui_common  # type: ignore

            gui_common.emit_status(
                level,
                code,
                text=text,
                source="jump_range_engine",
                notify_overlay=bool(notify_overlay),
            )
        except Exception:
            MSG_QUEUE.put(("log", f"[{level}] {code}: {text or code}"))

    def recompute_jump_range(self, trigger: str = "status_change") -> None:
        self._compute_jump_range(trigger)
        if trigger == "loadout":
            self._validate_jump_range()

    def _compute_jump_range(self, trigger: str) -> None:
        if not self._should_compute_jump_range(trigger):
            return
        try:
            from app.state import app_state

            modules_data = getattr(app_state, "modules_data", None)
            modules_data_loaded = bool(getattr(app_state, "modules_data_loaded", False))
        except Exception:
            modules_data = None
            modules_data_loaded = False

        if not self.fit_ready_for_jr or not modules_data_loaded or not modules_data:
            self.jump_range_current_ly = None
            self.jump_range_current_source = None
            self.jump_range_last_calc_at = time.time()
            self.jump_range_limited_by = "unknown"
            self.jump_range_fuel_needed_t = None
            self._emit_jump_range_status(
                "WARN",
                "JR_WAITING_DATA",
                "Jump range: waiting for data",
            )
            return

        try:
            from logic.jump_range_engine import compute_jump_range_current

            result = compute_jump_range_current(self, modules_data)
        except Exception as exc:
            self.jump_range_current_ly = None
            self.jump_range_current_source = None
            self.jump_range_last_calc_at = time.time()
            self.jump_range_limited_by = "unknown"
            self.jump_range_fuel_needed_t = None
            self._emit_jump_range_status(
                "WARN",
                "JR_COMPUTE_FAIL",
                "Jump range compute failed",
            )
            self._log_debug(f"Jump range compute failed: {exc}")
            if config.get("jump_range_engine_debug", False):
                raise
            return

        if result.ok and result.jump_range_ly is not None:
            self.jump_range_current_ly = result.jump_range_ly
            self.jump_range_current_source = result.source
            self.jump_range_last_calc_at = time.time()
            self.jump_range_limited_by = result.jump_range_limited_by
            self.jump_range_fuel_needed_t = result.jump_range_fuel_needed_t
            if result.details.get("engineering_applied") and config.get(
                "jump_range_engineering_debug", False
            ):
                self._emit_jump_range_status(
                    "INFO",
                    "JR_ENGINEERING_APPLIED",
                    "Jump range engineering applied",
                    notify_overlay=False,
                )
            self._emit_jump_range_status("OK", "JR_READY", "Jump range computed")
            return

        self.jump_range_current_ly = None
        self.jump_range_current_source = None
        self.jump_range_last_calc_at = time.time()
        self.jump_range_limited_by = "unknown"
        self.jump_range_fuel_needed_t = None

        if result.error and result.error.startswith("missing_"):
            self._emit_jump_range_status(
                "WARN",
                "JR_WAITING_DATA",
                "Jump range: waiting for data",
            )
        else:
            self._emit_jump_range_status(
                "WARN",
                "JR_COMPUTE_FAIL",
                "Jump range compute failed",
            )

    def _validate_jump_range(self) -> None:
        if not config.get("jump_range_validate_enabled", True):
            return
        if self.loadout_max_jump_range_ly is None:
            return
        if not self.fit_ready_for_jr:
            return
        try:
            from app.state import app_state

            modules_data = getattr(app_state, "modules_data", None)
            modules_data_loaded = bool(getattr(app_state, "modules_data_loaded", False))
        except Exception:
            modules_data = None
            modules_data_loaded = False

        if not modules_data_loaded or not modules_data:
            return

        try:
            from logic.jump_range_engine import compute_jump_range_loadout_max

            result = compute_jump_range_loadout_max(self, modules_data)
        except Exception as exc:
            self._log_debug(f"Jump range validate failed: {exc}")
            if config.get("jump_range_engine_debug", False):
                raise
            return

        if not result.ok or result.jump_range_ly is None:
            return

        try:
            delta = abs(float(self.loadout_max_jump_range_ly) - float(result.jump_range_ly))
        except Exception:
            return

        self.jump_range_validate_delta_ly = delta
        tolerance = config.get("jump_range_validate_tolerance_ly", 0.05)
        try:
            tolerance = float(tolerance)
        except Exception:
            tolerance = 0.05

        code = "JR_VALIDATE_OK"
        level = "INFO"
        text = f"JR validate ok (delta={delta:.3f} ly)"
        if delta > tolerance:
            code = "JR_VALIDATE_DELTA"
            level = "WARN"
            text = f"JR validate delta {delta:.3f} ly"

        log_only = bool(config.get("jump_range_validate_log_only", True))
        if not DEBOUNCER.is_allowed("jr_validate", cooldown_sec=10.0):
            return
        debug_ok = code == "JR_VALIDATE_OK" and not config.get(
            "jump_range_validate_debug", False
        )
        self._emit_jump_range_status(
            level,
            code,
            text,
            debug_only=debug_ok,
            notify_overlay=not log_only,
        )

    def update_from_loadout(self, event: Dict[str, Any], source: str = "journal") -> None:
        if not event:
            return
        ship_id = event.get("ShipID")
        ship_type = event.get("Ship")
        unladen_mass = event.get("UnladenMass")
        modules = event.get("Modules") or []
        max_jump_range = event.get("MaxJumpRange")

        changed = False
        if ship_id is not None:
            try:
                ship_id = int(ship_id)
            except Exception:
                ship_id = None
        if ship_id is not None and ship_id != self.ship_id:
            self.ship_id = ship_id
            changed = True

        if ship_type:
            ship_type = str(ship_type).strip()
            if ship_type and ship_type != self.ship_type:
                self.ship_type = ship_type
                changed = True

        if unladen_mass is not None:
            try:
                unladen_mass = float(unladen_mass)
            except Exception:
                unladen_mass = None
        if unladen_mass is not None and unladen_mass != self.unladen_mass_t:
            self.unladen_mass_t = unladen_mass
            changed = True

        if max_jump_range is not None:
            try:
                max_jump_range = float(max_jump_range)
            except Exception:
                max_jump_range = None
        if max_jump_range is not None and max_jump_range != self.loadout_max_jump_range_ly:
            self.loadout_max_jump_range_ly = max_jump_range
            changed = True

        if isinstance(modules, list) and modules != self.modules:
            self.modules = modules
            changed = True

        if config.get("fit_resolver_enabled", True):
            try:
                from logic.fit_resolver import resolve_fit_from_loadout
                from app.state import app_state

                modules_data = getattr(app_state, "modules_data", None)
                fit = resolve_fit_from_loadout(self.modules, modules_data)
                if fit.get("fsd") != self.fsd:
                    self.fsd = fit.get("fsd") or self.fsd
                    changed = True
                if fit.get("fsd_booster") != self.fsd_booster:
                    self.fsd_booster = fit.get("fsd_booster") or self.fsd_booster
                    changed = True
                if fit.get("fit_ready_for_jr") != self.fit_ready_for_jr:
                    self.fit_ready_for_jr = bool(fit.get("fit_ready_for_jr"))
                    changed = True
            except Exception:
                if config.get("fit_resolver_fail_on_missing", False):
                    raise
                pass

        if changed:
            self._mark_updated(source)
            self._log_debug(
                f"Loadout: ship_id={self.ship_id}, ship_type={self.ship_type}, "
                f"unladen={self.unladen_mass_t}"
            )
            self.recompute_jump_range("loadout")
            self._emit_update()

    def update_from_status_json(self, data: Dict[str, Any], source: str = "status_json") -> None:
        if not data:
            return
        fuel = data.get("Fuel") or {}
        if not isinstance(fuel, dict):
            return

        main_val = fuel.get("FuelMain")
        res_val = fuel.get("FuelReservoir")

        changed = False
        if main_val is not None:
            try:
                main_val = float(main_val)
            except Exception:
                main_val = None
        if main_val is not None and main_val != self.fuel_main_t:
            self.fuel_main_t = main_val
            changed = True

        if res_val is not None:
            try:
                res_val = float(res_val)
            except Exception:
                res_val = None
        if res_val is not None and res_val != self.fuel_reservoir_t:
            self.fuel_reservoir_t = res_val
            changed = True

        if changed:
            self._mark_updated(source)
            self._log_debug(
                f"Fuel: main={self.fuel_main_t}, reservoir={self.fuel_reservoir_t}"
            )
            self._compute_jump_range("status_change")
            self._emit_update()

    def update_from_cargo_json(self, data: Dict[str, Any], source: str = "cargo_json") -> None:
        if not data:
            return

        cargo_mass = None
        for key in ("Cargo", "CargoMass", "cargo", "cargo"):
            if key in data:
                try:
                    cargo_mass = float(data.get(key))
                except Exception:
                    cargo_mass = None
                break

        if cargo_mass is None:
            count = data.get("Count")
            if count is not None:
                try:
                    cargo_mass = float(count)
                except Exception:
                    cargo_mass = None

        if cargo_mass is None:
            inventory = data.get("Inventory")
            if isinstance(inventory, list):
                total = 0.0
                for item in inventory:
                    if not isinstance(item, dict):
                        continue
                    cnt = item.get("Count")
                    if cnt is None:
                        continue
                    try:
                        total += float(cnt)
                    except Exception:
                        continue
                cargo_mass = total

        if cargo_mass is None:
            return

        if cargo_mass != self.cargo_mass_t:
            self.cargo_mass_t = cargo_mass
            self._mark_updated(source)
            self._log_debug(f"Cargo: mass={self.cargo_mass_t}")
            self._compute_jump_range("status_change")
            self._emit_update()

    def get_completeness(self) -> Dict[str, bool]:
        return {
            "ship_id": self.ship_id is not None,
            "ship_type": bool(self.ship_type),
            "unladen_mass_t": self.unladen_mass_t is not None,
            "fuel_main_t": self.fuel_main_t is not None,
            "fuel_reservoir_t": self.fuel_reservoir_t is not None,
            "cargo_mass_t": self.cargo_mass_t is not None,
        }

    def is_complete(self) -> bool:
        comp = self.get_completeness()
        return all(comp.values())
