# logic/system_value_engine.py
"""
System Value Engine (EPIC 1)

ModuĹ‚ odpowiedzialny za wyliczanie wartoĹ›ci naukowej systemu na podstawie:
- JournalEvents (Scan, FSS/DSS, exobio),
- arkuszy naukowych z renata_science_data.xlsx (Exobiology + Cartography).

GĹ‚Ăłwne metryki:
- c_cartography  â€“ Ĺ‚Ä…czna wartoĹ›Ä‡ skanĂłw ciaĹ‚ (FSS / DSS),
- c_exobiology   â€“ Ĺ‚Ä…czna wartoĹ›Ä‡ skanĂłw biologii,
- bonus_discovery â€“ suma bonusĂłw First Discovery / First Footfall,
- total          â€“ suma wszystkiego powyĹĽej.

Zastosowanie:
- exit summary po opuszczeniu systemu (gĹ‚os + log),
- statystyki / high-value targets dla eksploratora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Optional, Set, Tuple, List

import pandas as pd


@dataclass
class SystemStats:
    """Stan dla pojedynczego ukĹ‚adu gwiezdnego."""

    name: str
    c_cartography: float = 0.0
    c_exobiology: float = 0.0
    bonus_discovery: float = 0.0
    # Domain-level bonus buckets (used for sale-aware clears):
    # - cartography: first discovery bonuses tied to Scan/DSS
    # - exobiology: first discovery / footfall bonuses tied to biology
    bonus_discovery_cartography: float = 0.0
    bonus_discovery_exobiology: float = 0.0

    # Techniczne:
    seen_bodies: Set[str] = field(default_factory=set)   # ĹĽeby nie liczyÄ‡ skanu 2x
    seen_species: Set[str] = field(default_factory=set)  # ĹĽeby nie liczyÄ‡ gatunku 2x
    high_value_targets: List[Dict[str, Any]] = field(default_factory=list)
    cartography_bodies: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # body_id -> applied valuation state

    # --- Discovery status 2.0 ---
    # ile ciaĹ‚ faktycznie zeskanowaliĹ›my w tym systemie
    total_scanned_bodies: int = 0
    # ile z nich miaĹ‚o WasDiscovered == False (czyli byĹ‚y dziewicze)
    bodies_first_discovery_count: int = 0
    # ile miaĹ‚o WasDiscovered == True (ktoĹ› juĹĽ je odkryĹ‚)
    bodies_previously_discovered_count: int = 0

    # Czy widzieliĹ›my jakiekolwiek bonusy (First Discovery / Footfall / inne)
    any_discovery_bonuses: bool = False

    # Flaga â€žwiemy na pewno, ĹĽe system byĹ‚ wczeĹ›niej odkrytyâ€ť
    # True  â€“ wiemy, ĹĽe jakieĹ› ciaĹ‚o byĹ‚o juĹĽ odkryte
    # False â€“ wszystkie znane nam ciaĹ‚a sÄ… â€žWasDiscovered == Falseâ€ť
    # None  â€“ brak danych / niejednoznaczne
    system_previously_discovered: Optional[bool] = None


class SystemValueEngine:
    """
    GĹ‚Ăłwny silnik wyliczajÄ…cy wartoĹ›Ä‡ systemu.

    Parametr science_data:
        - moĹĽe byÄ‡ tuple: (exobio_df, carto_df) z logic.science_data.load_science_data()
        - albo dict: {"exobio": df_exobio, "carto": df_carto}
    """

    def __init__(self, science_data: Any):
        self.exobio_df, self.carto_df = self._normalize_science_data(science_data)

        # Szybszy dostÄ™p po nazwie gatunku (lower-case)
        self._exobio_map: Dict[str, pd.Series] = {
            str(row["Species_Name"]).strip().lower(): row
            for _, row in self.exobio_df.iterrows()
        }

        # Szybszy dostÄ™p po (Body_Type, Terraformable)
        self._carto_map: Dict[Tuple[str, str], pd.Series] = {
            (str(row["Body_Type"]).strip(), str(row["Terraformable"]).strip()): row
            for _, row in self.carto_df.iterrows()
        }

        # Stan per system
        self.systems: Dict[str, SystemStats] = {}
        self.current_system: Optional[str] = None
        self._diag_counts: Dict[str, int] = {
            "scan_star_counted": 0,
            "scan_star_skipped_unmapped": 0,
            "scan_planet_skipped_unmapped": 0,
        }

    # ------------------------------------------------------------------
    # Publiczny interfejs
    # ------------------------------------------------------------------

    def set_current_system(self, system_name: Optional[str]) -> None:
        """
        Ustawia aktualny system. Nie resetuje statystyk, tylko tworzy entry jeĹ›li brak.
        """
        if not system_name:
            self.current_system = None
            return
        self.current_system = system_name
        self._get_or_create_system(system_name)

    def clear_value_domain(
        self,
        *,
        domain: str = "all",
        system_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Clears runtime valuation state after sell events.

        domain:
        - "cartography" / "carto" / "uc"
        - "exobiology" / "exo" / "vista"
        - "all"

        system_name:
        - if provided: clear only this system
        - else: clear all systems
        """
        norm = str(domain or "all").strip().lower()
        if norm in {"carto", "cartography", "uc", "exploration"}:
            mode = "cartography"
        elif norm in {"exo", "exobiology", "vista", "organic"}:
            mode = "exobiology"
        else:
            mode = "all"

        if system_name:
            target_names = [str(system_name)]
        else:
            target_names = list(self.systems.keys())

        touched = 0
        for name in target_names:
            stats = self.systems.get(str(name))
            if not isinstance(stats, SystemStats):
                continue
            self._ensure_bonus_components(stats)
            if mode == "cartography":
                self._clear_cartography_state(stats)
            elif mode == "exobiology":
                self._clear_exobiology_state(stats)
            else:
                self._clear_all_state(stats)
            touched += 1

        totals = self.calculate_totals()
        return {
            "ok": True,
            "domain": mode,
            "systems_touched": int(touched),
            "scope": ("single" if system_name else "all"),
            "system_name": (str(system_name) if system_name else None),
            "totals": dict(totals or {}),
        }

    def analyze_scan_event(self, event: Dict[str, Any]) -> None:
        """
        Analiza pojedynczego eventu Journal typu 'Scan' (FSS / DSS).

        ZakĹ‚adamy standardowy format Elite Dangerous:
        - StarSystem
        - BodyName / BodyID / Body
        - PlanetClass / StarType / BodyType
        - TerraformState
        - WasDiscovered (bool / 0/1)
        - WasMapped / Mapped (bool)
        """
        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            # Nie wiemy, jaki system â€“ nie liczymy
            return

        stats = self._get_or_create_system(system_name)
        self._ensure_bonus_components(stats)

        # Identyfikator ciaĹ‚a (wystarczy coĹ› unikalnego w obrÄ™bie systemu)
        body_id = (
            event.get("BodyName")
            or event.get("Body")
            or (str(event.get("BodyID")) if event.get("BodyID") is not None else None)
        )

        if not body_id:
            body_id = f"UNKNOWN_BODY_{len(stats.seen_bodies) + 1}"

        # Nie liczymy wielokrotnego skanu tego samego ciaĹ‚a
        if body_id in stats.seen_bodies:
            return
        stats.seen_bodies.add(body_id)

        # --- Discovery status dla tego ciaĹ‚a ---
        was_discovered = event.get("WasDiscovered")
        # Upewniamy siÄ™, ĹĽe mamy czyste bool
        if was_discovered in (0, 1):
            was_discovered = bool(was_discovered)

        stats.total_scanned_bodies += 1

        if was_discovered is False:
            # Dziewicze ciaĹ‚o â€“ First Discovery
            stats.bodies_first_discovery_count += 1

            # JeĹĽeli nie mamy jeszcze ĹĽadnej informacji o systemie,
            # zakĹ‚adamy, ĹĽe system nie byĹ‚ wczeĹ›niej odkryty
            if stats.system_previously_discovered is None:
                stats.system_previously_discovered = False

        elif was_discovered is True:
            stats.bodies_previously_discovered_count += 1
            # wiemy na pewno, ĹĽe system jest â€žznanyâ€ť
            stats.system_previously_discovered = True

        star_values = self._lookup_star_cartography_values(event)
        if star_values is not None:
            base_value = float(star_values.get("fss_value") or 0.0)
            fd_bonus = float(star_values.get("fd_bonus") or 0.0)
            bonus = fd_bonus if (was_discovered is False or was_discovered == 0) else 0.0

            stats.c_cartography += base_value
            stats.bonus_discovery_cartography += bonus
            self._sync_bonus_aggregate(stats)
            if bonus > 0.0:
                stats.any_discovery_bonuses = True

            stats.cartography_bodies[str(body_id)] = {
                "body_type": str(star_values.get("body_type") or "Star"),
                "terraformable": "No",
                "was_discovered": was_discovered,
                "fss_value": base_value,
                "dss_value": 0.0,
                "fd_mapped": base_value + bonus,
                "base_applied": base_value,
                "bonus_applied": bonus,
                "mapped_accounted": True,
                "valuation_source": "star_tier",
                "star_tier": str(star_values.get("tier") or "unknown"),
                "star_type_raw": str(star_values.get("star_type_raw") or ""),
            }
            self._diag_counts["scan_star_counted"] = int(self._diag_counts.get("scan_star_counted", 0)) + 1
            return

        body_type, terraformable = self._extract_cartography_type(event)
        if not body_type:
            # Np. gwiazda, ktĂłrej nie mamy w tabeli â€“ pomijamy
            self._diag_counts["scan_planet_skipped_unmapped"] = int(self._diag_counts.get("scan_planet_skipped_unmapped", 0)) + 1
            return

        row = self._lookup_cartography_row(body_type, terraformable)
        if row is None:
            self._diag_counts["scan_planet_skipped_unmapped"] = int(self._diag_counts.get("scan_planet_skipped_unmapped", 0)) + 1
            return

        was_mapped = bool(event.get("WasMapped") or event.get("Mapped"))
        mapped_from_scan_allowed = bool(was_mapped and (was_discovered is False or was_discovered == 0))

        # Bazowa wartoĹ›Ä‡: FSS lub DSS
        fss_value = self._finite_row_float(row, "FSS_Base_Value")
        dss_value = self._finite_row_float(row, "DSS_Mapped_Value")
        fd_mapped = self._finite_row_float(row, "First_Discovery_Mapped_Value")

        if mapped_from_scan_allowed:
            base_value = dss_value
        else:
            base_value = fss_value

        stats.c_cartography += base_value

        # Bonus First Discovery (dla planet / ciaĹ‚)
        bonus = 0.0
        if was_discovered is False or was_discovered == 0:
            if mapped_from_scan_allowed and dss_value > 0:
                # RĂłĹĽnica miÄ™dzy â€žzwykĹ‚ymâ€ť DSS a â€žFirst Discovery mappedâ€ť
                bonus = max(0.0, fd_mapped - dss_value)
            elif fss_value > 0 and dss_value > 0:
                # Przy braku osobnej kolumny dla FSS+FD â€” przybliĹĽenie:
                ratio = fd_mapped / dss_value if dss_value else 1.0
                bonus = max(0.0, fss_value * (ratio - 1.0))

        stats.bonus_discovery_cartography += bonus
        self._sync_bonus_aggregate(stats)
        if bonus > 0:
            stats.any_discovery_bonuses = True

        # Track applied cartography state so SAAScanComplete can upgrade FSS -> DSS.
        stats.cartography_bodies[str(body_id)] = {
            "body_type": body_type,
            "terraformable": terraformable,
            "was_discovered": was_discovered,
            "fss_value": fss_value,
            "dss_value": dss_value,
            "fd_mapped": fd_mapped,
            "base_applied": base_value,
            "bonus_applied": bonus,
            "mapped_accounted": bool(mapped_from_scan_allowed),
        }

        # High-Value Targets (ELW / WW / terraformable)
        if self._is_high_value_target(body_type, terraformable):
            self._upsert_high_value_target(
                stats,
                body_id=str(body_id),
                body_type=body_type,
                terraformable=terraformable,
                estimated_value=base_value + bonus,
            )

    def get_runtime_diagnostics(self) -> Dict[str, int]:
        return {str(k): int(v or 0) for k, v in dict(self._diag_counts or {}).items()}

    def analyze_dss_scan_complete_event(self, event: Dict[str, Any]) -> None:
        """
        Upgrade cartography valuation for a body when DSS mapping completes (SAAScanComplete).

        Journal SAAScanComplete usually does not carry enough body type/value metadata on its
        own, so this method upgrades a body that was previously seen in `Scan` based on the
        cached row/values captured during `analyze_scan_event`.
        """
        if str(event.get("event") or "").strip() != "SAAScanComplete":
            return

        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            return

        stats = self.systems.get(str(system_name))
        if not stats:
            return
        self._ensure_bonus_components(stats)

        body_id = (
            event.get("BodyName")
            or event.get("Body")
            or (str(event.get("BodyID")) if event.get("BodyID") is not None else None)
        )
        if not body_id:
            return

        row = stats.cartography_bodies.get(str(body_id))
        if not isinstance(row, dict):
            return

        if bool(row.get("mapped_accounted")):
            return

        current_base = float(row.get("base_applied", 0.0) or 0.0)
        current_bonus = float(row.get("bonus_applied", 0.0) or 0.0)
        dss_value = float(row.get("dss_value", 0.0) or 0.0)
        fd_mapped = float(row.get("fd_mapped", 0.0) or 0.0)
        was_discovered = row.get("was_discovered")

        if dss_value <= 0.0:
            row["mapped_accounted"] = True
            return

        target_base = dss_value
        target_bonus = 0.0
        if was_discovered is False or was_discovered == 0:
            target_bonus = max(0.0, fd_mapped - dss_value)

        stats.c_cartography += (target_base - current_base)
        stats.bonus_discovery_cartography += (target_bonus - current_bonus)
        self._sync_bonus_aggregate(stats)
        if target_bonus > 0.0:
            stats.any_discovery_bonuses = True

        row["base_applied"] = target_base
        row["bonus_applied"] = target_bonus
        row["mapped_accounted"] = True

        # Keep high-value breakdown in sync after DSS upgrades.
        body_type = str(row.get("body_type") or "")
        terraformable = str(row.get("terraformable") or "No")
        if body_type and self._is_high_value_target(body_type, terraformable):
            self._upsert_high_value_target(
                stats,
                body_id=str(body_id),
                body_type=body_type,
                terraformable=terraformable,
                estimated_value=target_base + target_bonus,
            )

    def analyze_biology_event(self, event: Dict[str, Any]) -> None:
        """
        Analiza eventu zwiÄ…zanego z exobiology.

        ObsĹ‚ugujemy generycznie eventy typu:
        - CodexEntry / ScanOrganic / inne z polami:
          Name_Localised / Species_Localised / Species / Genus_Localised / Genus / Name

        Dodatkowe flagi (jeĹ›li wystÄ™pujÄ…):
        - FirstDiscovery / IsNewSpecies / NewSpecies
        - FirstFootfall / FirstScan
        """
        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            return

        stats = self._get_or_create_system(system_name)
        self._ensure_bonus_components(stats)

        raw_name = (
            event.get("Name_Localised")
            or event.get("Species_Localised")
            or event.get("Species")
            or event.get("Genus_Localised")
            or event.get("Genus")
            or event.get("Name")
        )
        if not raw_name:
            return

        species_name = self._normalize_species_name(raw_name)
        if not species_name:
            return

        # Nie liczymy gatunku dwu-/trzykrotnie w tym samym systemie
        if species_name in stats.seen_species:
            return
        stats.seen_species.add(species_name)

        row = self._lookup_exobio_row(species_name)
        if row is None:
            return

        base_value = float(row.get("Base_Value", 0.0) or 0.0)
        fd_bonus = float(row.get("First_Discovery_Bonus", 0.0) or 0.0)
        total_ff = float(row.get("Total_First_Footfall", 0.0) or 0.0)

        # dolicz bazowÄ… wartoĹ›Ä‡ biologii
        stats.c_exobiology += base_value

        # Flagi "first discovery / first footfall" z eventu
        is_first_discovery = bool(
            event.get("FirstDiscovery")
            or event.get("IsNewSpecies")
            or event.get("NewSpecies")
        )
        is_first_footfall = bool(
            event.get("FirstFootfall")
            or event.get("FirstScan")
        )

        bonus = 0.0
        if is_first_discovery:
            bonus += fd_bonus

        # First Footfall: zakĹ‚adamy, ĹĽe total_ff = base + fd_bonus + extra_ff
        if is_first_footfall and total_ff > 0:
            extra_ff = max(0.0, total_ff - (base_value + fd_bonus))
            bonus += extra_ff

        stats.bonus_discovery_exobiology += bonus
        self._sync_bonus_aggregate(stats)
        if bonus > 0:
            stats.any_discovery_bonuses = True

    def analyze_discovery_meta_event(self, event: Dict[str, Any]) -> None:
        """
        Analiza meta-informacji discovery, ktĂłre nie sÄ… czystym Scan/Biology.

        Wspieramy m.in.:
        - event z polem FirstDiscoveredBy (np. Explore / SAAScanComplete wrapper),
        - FSSSignalDiscovered (sygnaĹ‚y odkryte przez CMDR),
        - ogĂłlne CodexEntry z flagami IsNewDiscovery / NewDiscoveries.

        To jest "miÄ™kka" logika â€“ nie rusza kredytĂłw, tylko status.
        """
        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            return

        stats = self._get_or_create_system(system_name)
        ev_type = event.get("event")

        # 1) FirstDiscoveredBy â€“ jeĹ›li w ogĂłle istnieje, wiemy, ĹĽe system ma â€žautoraâ€ť
        first_by = event.get("FirstDiscoveredBy")
        if first_by:
            # Niekoniecznie my, ale to oznacza, ĹĽe system nie jest dziewiczy
            stats.system_previously_discovered = True

        # 2) FSSSignalDiscovered â€“ wiemy, ĹĽe coĹ› odkryliĹ›my w tym systemie,
        # ale nie przesÄ…dza to o dziewiczoĹ›ci caĹ‚ego ukĹ‚adu.
        if ev_type == "FSSSignalDiscovered":
            # To raczej meta-info: â€žcoĹ› nowego w tym systemieâ€ť
            # MoĹĽemy jedynie traktowaÄ‡ to jako sygnaĹ‚, ĹĽe discovery w ogĂłle istnieje.
            stats.any_discovery_bonuses = True

        # 3) CodexEntry z flagami nowoĹ›ci
        if ev_type == "CodexEntry":
            if event.get("IsNewDiscovery") or event.get("NewDiscoveries"):
                # Mamy nowÄ… odkrytÄ… rzecz w tym systemie
                stats.any_discovery_bonuses = True
                # JeĹ›li system_previously_discovered nie zostaĹ‚ oznaczony jako True,
                # nie nadpisujemy go tutaj â€“ to moĹĽe byÄ‡ nowy wpis w starym systemie.

    def get_discovery_status(self, system_name: str) -> Dict[str, Any]:
        """
        Zwraca skondensowany discovery_status dla danego systemu:

        {
            "system_previously_discovered": bool | None,
            "any_virgin_bodies": bool,
            "has_bonuses": bool,
            "is_virgin_system": bool
        }
        """
        stats = self.systems.get(system_name)
        if not stats:
            return {
                "system_previously_discovered": None,
                "any_virgin_bodies": False,
                "has_bonuses": False,
                "is_virgin_system": False,
            }

        any_virgin = stats.bodies_first_discovery_count > 0
        has_bonuses = stats.any_discovery_bonuses or stats.bonus_discovery > 0

        # Definicja â€ždziewiczego systemuâ€ť:
        # wszystkie ZESKANOWANE ciaĹ‚a miaĹ‚y WasDiscovered == False
        # (z naszej perspektywy w tym locie).
        is_virgin_system = (
            stats.total_scanned_bodies > 0
            and stats.bodies_first_discovery_count == stats.total_scanned_bodies
        )

        # JeĹ›li mamy jednoczeĹ›nie first i previously â€“ system jest na pewno znany.
        if stats.bodies_previously_discovered_count > 0:
            system_prev = True
        else:
            system_prev = stats.system_previously_discovered

        return {
            "system_previously_discovered": system_prev,
            "any_virgin_bodies": any_virgin,
            "has_bonuses": has_bonuses,
            "is_virgin_system": is_virgin_system,
        }

    def calculate_totals(self) -> Dict[str, float]:
        """
        Zwraca sumaryczne wartoĹ›ci ze wszystkich systemĂłw.

        Format:
        {
            "c_cartography": ...,
            "c_exobiology": ...,
            "bonus_discovery": ...,
            "total": ...
        }
        """
        c_carto = 0.0
        c_exo = 0.0
        bonus = 0.0
        for s in self.systems.values():
            self._ensure_bonus_components(s)
            c_carto += float(s.c_cartography or 0.0)
            c_exo += float(s.c_exobiology or 0.0)
            bonus += float(s.bonus_discovery or 0.0)
        total = c_carto + c_exo + bonus

        return {
            "c_cartography": c_carto,
            "c_exobiology": c_exo,
            "bonus_discovery": bonus,
            "total": total,
        }

    # Dodatkowe helpery do debugowania / GUI (opcjonalne uĹĽycie)

    def get_system_stats(self, system_name: str) -> Optional[SystemStats]:
        """Zwraca obiekt SystemStats dla konkretnego ukĹ‚adu (lub None)."""
        stats = self.systems.get(system_name)
        if isinstance(stats, SystemStats):
            self._ensure_bonus_components(stats)
        return stats

    # ------------------------------------------------------------------
    # Implementacja pomocnicza
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_science_data(science_data: Any) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Normalizuje wejĹ›cie science_data do tuple (exobio_df, carto_df).
        """
        if isinstance(science_data, tuple) and len(science_data) == 2:
            return science_data
        if isinstance(science_data, dict):
            return science_data["exobio"], science_data["carto"]
        raise ValueError(
            "science_data musi byÄ‡ tuple(exobio_df, carto_df) "
            "albo dict {'exobio': df, 'carto': df}"
        )

    def _get_or_create_system(self, name: str) -> SystemStats:
        if name not in self.systems:
            self.systems[name] = SystemStats(name=name)
        stats = self.systems[name]
        self._ensure_bonus_components(stats)
        return stats

    @staticmethod
    def _sync_bonus_aggregate(stats: SystemStats) -> None:
        stats.bonus_discovery = float(stats.bonus_discovery_cartography or 0.0) + float(
            stats.bonus_discovery_exobiology or 0.0
        )

    def _ensure_bonus_components(self, stats: SystemStats) -> None:
        # Backward compatibility for state that existed before domain-level buckets.
        if not hasattr(stats, "bonus_discovery_cartography"):
            setattr(stats, "bonus_discovery_cartography", float(getattr(stats, "bonus_discovery", 0.0) or 0.0))
        if not hasattr(stats, "bonus_discovery_exobiology"):
            setattr(stats, "bonus_discovery_exobiology", 0.0)
        self._sync_bonus_aggregate(stats)

    def _clear_cartography_state(self, stats: SystemStats) -> None:
        stats.c_cartography = 0.0
        stats.bonus_discovery_cartography = 0.0
        stats.seen_bodies.clear()
        stats.high_value_targets.clear()
        stats.cartography_bodies.clear()
        stats.total_scanned_bodies = 0
        stats.bodies_first_discovery_count = 0
        stats.bodies_previously_discovered_count = 0
        stats.system_previously_discovered = None
        self._sync_bonus_aggregate(stats)
        stats.any_discovery_bonuses = bool(stats.bonus_discovery > 0.0)

    def _clear_exobiology_state(self, stats: SystemStats) -> None:
        stats.c_exobiology = 0.0
        stats.bonus_discovery_exobiology = 0.0
        stats.seen_species.clear()
        self._sync_bonus_aggregate(stats)
        if stats.total_scanned_bodies <= 0 and stats.bodies_first_discovery_count <= 0:
            stats.any_discovery_bonuses = bool(stats.bonus_discovery > 0.0)

    def _clear_all_state(self, stats: SystemStats) -> None:
        stats.c_cartography = 0.0
        stats.c_exobiology = 0.0
        stats.bonus_discovery_cartography = 0.0
        stats.bonus_discovery_exobiology = 0.0
        stats.seen_bodies.clear()
        stats.seen_species.clear()
        stats.high_value_targets.clear()
        stats.cartography_bodies.clear()
        stats.total_scanned_bodies = 0
        stats.bodies_first_discovery_count = 0
        stats.bodies_previously_discovered_count = 0
        stats.any_discovery_bonuses = False
        stats.system_previously_discovered = None
        self._sync_bonus_aggregate(stats)

    @staticmethod
    def _upsert_high_value_target(
        stats: SystemStats,
        *,
        body_id: str,
        body_type: str,
        terraformable: str,
        estimated_value: float,
    ) -> None:
        body_key = str(body_id or "").strip()
        if not body_key:
            return
        target_value = float(estimated_value or 0.0)
        for item in list(stats.high_value_targets or []):
            if str((item or {}).get("body_id") or "").strip() != body_key:
                continue
            item["body_type"] = str(body_type or "")
            item["terraformable"] = str(terraformable or "No")
            item["estimated_value"] = target_value
            return
        stats.high_value_targets.append(
            {
                "body_id": body_key,
                "body_type": str(body_type or ""),
                "terraformable": str(terraformable or "No"),
                "estimated_value": target_value,
            }
        )

    # --- Cartography helpers -------------------------------------------------

    @staticmethod
    def _normalize_star_type_token(raw: Any) -> str:
        token = str(raw or "").strip()
        if not token:
            return ""
        return token.upper().replace(" ", "").replace("-", "").replace("_", "")

    def _lookup_star_cartography_values(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Best-effort support for star Scan valuation (`StarType`).

        The Cartography sheet used by Renata is planet-centric, so stars would otherwise
        be skipped and summary could remain at 0 Cr during "star-heavy" exploration.
        """
        star_type_raw = str(event.get("StarType") or "").strip()
        if not star_type_raw:
            return None

        token = self._normalize_star_type_token(star_type_raw)
        if not token:
            return None

        tier: Optional[str] = None
        if "BLACKHOLE" in token or token in {"H", "SUPERMASSIVEBLACKHOLE"}:
            tier = "black_hole"
        elif "NEUTRON" in token or token == "N":
            tier = "neutron"
        elif "WOLFRAYET" in token or token in {"W", "WC", "WN", "WO"}:
            tier = "wolf_rayet"
        elif "WHITEDWARF" in token or token.startswith("D"):
            tier = "white_dwarf"
        elif "TTAURI" in token or "PROTO" in token or token == "TTS":
            tier = "protostar"
        elif "HERBIG" in token or "AEBE" in token:
            tier = "herbig_ae_be"
        elif token in {"C", "CN", "CJ"} or token.startswith("S"):
            tier = "carbon_like"
        elif token.startswith("L") or token.startswith("T") or token.startswith("Y"):
            tier = "brown_dwarf"
        elif token[:1] in {"O", "B", "A", "F", "G", "K", "M"}:
            tier = "main_sequence"

        tier_values: Dict[str, Tuple[float, float, str]] = {
            # Conservative FSS + first discovery bonus heuristics (runtime summary only).
            "main_sequence": (1200.0, 1200.0, "Star"),
            "brown_dwarf": (600.0, 600.0, "Brown Dwarf"),
            "protostar": (900.0, 900.0, "Protostar"),
            "herbig_ae_be": (2500.0, 2500.0, "Herbig Ae/Be Star"),
            "carbon_like": (3500.0, 3500.0, "Carbon Star"),
            "white_dwarf": (14000.0, 14000.0, "White Dwarf"),
            "wolf_rayet": (18000.0, 18000.0, "Wolf-Rayet Star"),
            "neutron": (22000.0, 22000.0, "Neutron Star"),
            "black_hole": (32000.0, 32000.0, "Black Hole"),
        }

        if tier not in tier_values:
            self._diag_counts["scan_star_skipped_unmapped"] = int(self._diag_counts.get("scan_star_skipped_unmapped", 0)) + 1
            return None

        fss_value, fd_bonus, body_type = tier_values[tier]
        return {
            "tier": tier,
            "star_type_raw": star_type_raw,
            "body_type": body_type,
            "fss_value": float(fss_value),
            "fd_bonus": float(fd_bonus),
        }

    def _extract_cartography_type(
        self, event: Dict[str, Any]
    ) -> Tuple[Optional[str], str]:
        """
        WyciÄ…ga (Body_Type, Terraformable) w formacie zgodnym z arkuszem Cartography.

        Zwraca:
            (body_type, terraformable) â€“ np. ("Water World", "Yes")

        JeĹ›li nie uda siÄ™ ustaliÄ‡ typu â€“ (None, "No").
        """
        terraform_state = str(event.get("TerraformState") or "").lower().strip()
        terraformable = "Yes" if terraform_state in {
            "terraformable",
            "terraforming",
            "terraformingcandidate",
            "candidate for terraforming",
        } else "No"

        planet_class = str(event.get("PlanetClass") or "").lower().strip()
        if not planet_class:
            # Journal Scan entries without PlanetClass are typically non-valued
            # entities (e.g. belt clusters/rings from NavBeaconDetail). Never
            # coerce them into generic "Planet Type", because that inflates
            # cartography estimates.
            return None, terraformable
        body_type = None

        # NajczÄ™stsze klasy planet â€“ mapowanie do Body_Type z Excela
        mapping = {
            "ammonia world": "Ammonia World",
            "earth-like world": "Earth-like World",
            "earthlike world": "Earth-like World",
            "water world": "Water World",
            "high metal content world": "High Metal Content Planet",
            "high metal content body": "High Metal Content Planet",
            "high metal content planet": "High Metal Content Planet",
            "icy body": "Icy Body",
            "icy world": "Icy Body",
            "icy planet": "Icy Body",
            "metal rich body": "Metal Rich Body",
            "metal-rich body": "Metal Rich Body",
            "metal rich world": "Metal Rich Body",
            "metal-rich world": "Metal Rich Body",
            "rocky body": "Rocky Body",
            "rocky world": "Rocky Body",
            "rocky planet": "Rocky Body",
            "rocky ice world": "Rocky Ice Body",
            "rocky ice body": "Rocky Ice Body",
            "class i gas giant": "Class I Gas Giant",
            "class ii gas giant": "Class II Gas Giant",
            "class iii gas giant": "Class III Gas Giant",
            "class iv gas giant": "Class IV Gas Giant",
            "class v gas giant": "Class V Gas Giant",
            "gas giant with ammonia-based life": "Gas Giant with Ammonia-based Life",
            "gas giant with water-based life": "Gas Giant with Water-based Life",
            "helium-rich gas giant": "Helium-Rich Gas Giant",
            "water giant": "Water Giant",
        }

        if planet_class in mapping:
            body_type = mapping[planet_class]
        elif planet_class:
            # miÄ™kkie dopasowanie â€“ capitalizacja, bez gwarancji
            candidate = planet_class.title()
            # np. "High Metal Content World" â†’ sprĂłbujmy zastÄ…piÄ‡ "World" na "Planet"
            if "high metal content world" in planet_class:
                body_type = "High Metal Content Planet"
            else:
                body_type = candidate

        if body_type is None:
            # JeĹ›li kompletnie nie rozpoznaliĹ›my â€“ traktujemy jako â€žPlanet Typeâ€ť (fallback)
            body_type = "Planet Type"

        return body_type, terraformable

    def _lookup_cartography_row(
        self, body_type: str, terraformable: str
    ) -> Optional[pd.Series]:
        key = (body_type, terraformable)
        row = self._carto_map.get(key)
        if row is not None and self._row_has_finite_cartography_values(row):
            return row

        # Fallback: jeĹ›li nie ma wariantu terraformable â€“ sprĂłbuj niezaleĹĽnie od tej kolumny
        for (bt, tf), row in self._carto_map.items():
            if bt == body_type and self._row_has_finite_cartography_values(row):
                return row

        # Ostateczny fallback: jeĹ›li w arkuszu jest ogĂłlny â€žPlanet Typeâ€ť
        key_generic = ("Planet Type", terraformable)
        row_generic = self._carto_map.get(key_generic)
        if row_generic is not None and self._row_has_finite_cartography_values(row_generic):
            return row_generic

        row_generic_any = None
        for (bt, _tf), row in self._carto_map.items():
            if bt == "Planet Type" and self._row_has_finite_cartography_values(row):
                row_generic_any = row
                break
        return row_generic_any

    @staticmethod
    def _finite_row_float(row: pd.Series, key: str) -> float:
        try:
            out = float(row.get(key, 0.0) or 0.0)
        except Exception:
            return 0.0
        if not math.isfinite(out):
            return 0.0
        return out

    @classmethod
    def _row_has_finite_cartography_values(cls, row: pd.Series) -> bool:
        return any(
            cls._finite_row_float(row, key) > 0.0
            for key in ("FSS_Base_Value", "DSS_Mapped_Value", "First_Discovery_Mapped_Value")
        )

    def _is_high_value_target(self, body_type: str, terraformable: str) -> bool:
        """
        Lightweight classification for high-value bodies in system summary.
        """
        body_norm = str(body_type or "").strip().lower()
        terra_norm = str(terraformable or "").strip().lower()

        if body_norm in {"earth-like world", "water world", "ammonia world"}:
            return True

        if body_norm in {"high metal content planet", "high metal content world"}:
            return terra_norm == "yes"

        return False

    # --- Exobiology helpers --------------------------------------------------

    def _normalize_species_name(self, raw_name: str) -> Optional[str]:
        """
        Normalizuje nazwÄ™ gatunku z Codex/Journal do formy jak w arkuszu Exobiology.

        PrzykĹ‚ady:
        - "$Codex_Ent_Aleoida_Arcus_Name;" â†’ "Aleoida Arcus"
        - "Aleoida Arcus"                   â†’ "Aleoida Arcus"
        """
        if not raw_name:
            return None

        name = raw_name.strip()

        # Usuwamy ewentualne placeholdery w stylu $...;
        if name.startswith("$") and ";" in name:
            name = name.split(";", 1)[0]
            # Usuwamy prefixy $Codex_Ent_ etc.
            name = name.replace("$Codex_Ent_", "")
            name = name.replace("_Name", "")
            name = name.replace("_name", "")
            # Zamiana underscore â†’ spacja
            name = name.replace("_", " ")

        # PorzÄ…dkujemy capitalizacjÄ™ (pierwsza litera wielka w kaĹĽdym czĹ‚onie)
        name = " ".join(part.capitalize() for part in name.split())

        return name or None

    def _lookup_exobio_row(self, species_name: str) -> Optional[pd.Series]:
        key = species_name.strip().lower()
        row = self._exobio_map.get(key)
        if row is not None:
            return row

        # fallback â€“ delikatniejsze porĂłwnanie: usuwamy spacje
        key_nospace = key.replace(" ", "")
        for k, v in self._exobio_map.items():
            if k.replace(" ", "") == key_nospace:
                return v

        return None

