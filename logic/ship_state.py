from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config
from logic.utils import MSG_QUEUE


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
            "completeness": self.get_completeness(),
            "ts": self.last_update_ts,
        }
        MSG_QUEUE.put(("ship_state", payload))

    def update_from_loadout(self, event: Dict[str, Any], source: str = "journal") -> None:
        if not event:
            return
        ship_id = event.get("ShipID")
        ship_type = event.get("Ship")
        unladen_mass = event.get("UnladenMass")
        modules = event.get("Modules") or []

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
