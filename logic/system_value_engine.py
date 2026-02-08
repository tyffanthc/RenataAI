# logic/system_value_engine.py
"""
System Value Engine (EPIC 1)

Moduł odpowiedzialny za wyliczanie wartości naukowej systemu na podstawie:
- JournalEvents (Scan, FSS/DSS, exobio),
- arkuszy naukowych z renata_science_data.xlsx (Exobiology + Cartography).

Główne metryki:
- c_cartography  – łączna wartość skanów ciał (FSS / DSS),
- c_exobiology   – łączna wartość skanów biologii,
- bonus_discovery – suma bonusów First Discovery / First Footfall,
- total          – suma wszystkiego powyżej.

Zastosowanie:
- exit summary po opuszczeniu systemu (głos + log),
- statystyki / high-value targets dla eksploratora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set, Tuple, List

import pandas as pd


@dataclass
class SystemStats:
    """Stan dla pojedynczego układu gwiezdnego."""

    name: str
    c_cartography: float = 0.0
    c_exobiology: float = 0.0
    bonus_discovery: float = 0.0

    # Techniczne:
    seen_bodies: Set[str] = field(default_factory=set)   # żeby nie liczyć skanu 2x
    seen_species: Set[str] = field(default_factory=set)  # żeby nie liczyć gatunku 2x
    high_value_targets: List[Dict[str, Any]] = field(default_factory=list)

    # --- Discovery status 2.0 ---
    # ile ciał faktycznie zeskanowaliśmy w tym systemie
    total_scanned_bodies: int = 0
    # ile z nich miało WasDiscovered == False (czyli były dziewicze)
    bodies_first_discovery_count: int = 0
    # ile miało WasDiscovered == True (ktoś już je odkrył)
    bodies_previously_discovered_count: int = 0

    # Czy widzieliśmy jakiekolwiek bonusy (First Discovery / Footfall / inne)
    any_discovery_bonuses: bool = False

    # Flaga „wiemy na pewno, że system był wcześniej odkryty”
    # True  – wiemy, że jakieś ciało było już odkryte
    # False – wszystkie znane nam ciała są „WasDiscovered == False”
    # None  – brak danych / niejednoznaczne
    system_previously_discovered: Optional[bool] = None


class SystemValueEngine:
    """
    Główny silnik wyliczający wartość systemu.

    Parametr science_data:
        - może być tuple: (exobio_df, carto_df) z logic.science_data.load_science_data()
        - albo dict: {"exobio": df_exobio, "carto": df_carto}
    """

    def __init__(self, science_data: Any):
        self.exobio_df, self.carto_df = self._normalize_science_data(science_data)

        # Szybszy dostęp po nazwie gatunku (lower-case)
        self._exobio_map: Dict[str, pd.Series] = {
            str(row["Species_Name"]).strip().lower(): row
            for _, row in self.exobio_df.iterrows()
        }

        # Szybszy dostęp po (Body_Type, Terraformable)
        self._carto_map: Dict[Tuple[str, str], pd.Series] = {
            (str(row["Body_Type"]).strip(), str(row["Terraformable"]).strip()): row
            for _, row in self.carto_df.iterrows()
        }

        # Stan per system
        self.systems: Dict[str, SystemStats] = {}
        self.current_system: Optional[str] = None

    # ------------------------------------------------------------------
    # Publiczny interfejs
    # ------------------------------------------------------------------

    def set_current_system(self, system_name: Optional[str]) -> None:
        """
        Ustawia aktualny system. Nie resetuje statystyk, tylko tworzy entry jeśli brak.
        """
        if not system_name:
            self.current_system = None
            return
        self.current_system = system_name
        self._get_or_create_system(system_name)

    def analyze_scan_event(self, event: Dict[str, Any]) -> None:
        """
        Analiza pojedynczego eventu Journal typu 'Scan' (FSS / DSS).

        Zakładamy standardowy format Elite Dangerous:
        - StarSystem
        - BodyName / BodyID / Body
        - PlanetClass / StarType / BodyType
        - TerraformState
        - WasDiscovered (bool / 0/1)
        - WasMapped / Mapped (bool)
        """
        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            # Nie wiemy, jaki system – nie liczymy
            return

        stats = self._get_or_create_system(system_name)

        # Identyfikator ciała (wystarczy coś unikalnego w obrębie systemu)
        body_id = (
            event.get("BodyName")
            or event.get("Body")
            or (str(event.get("BodyID")) if event.get("BodyID") is not None else None)
        )

        if not body_id:
            body_id = f"UNKNOWN_BODY_{len(stats.seen_bodies) + 1}"

        # Nie liczymy wielokrotnego skanu tego samego ciała
        if body_id in stats.seen_bodies:
            return
        stats.seen_bodies.add(body_id)

        # --- Discovery status dla tego ciała ---
        was_discovered = event.get("WasDiscovered")
        # Upewniamy się, że mamy czyste bool
        if was_discovered in (0, 1):
            was_discovered = bool(was_discovered)

        stats.total_scanned_bodies += 1

        if was_discovered is False:
            # Dziewicze ciało – First Discovery
            stats.bodies_first_discovery_count += 1

            # Jeżeli nie mamy jeszcze żadnej informacji o systemie,
            # zakładamy, że system nie był wcześniej odkryty
            if stats.system_previously_discovered is None:
                stats.system_previously_discovered = False

        elif was_discovered is True:
            stats.bodies_previously_discovered_count += 1
            # wiemy na pewno, że system jest „znany”
            stats.system_previously_discovered = True

        body_type, terraformable = self._extract_cartography_type(event)
        if not body_type:
            # Np. gwiazda, której nie mamy w tabeli – pomijamy
            return

        row = self._lookup_cartography_row(body_type, terraformable)
        if row is None:
            return

        was_mapped = event.get("WasMapped") or event.get("Mapped")

        # Bazowa wartość: FSS lub DSS
        fss_value = float(row.get("FSS_Base_Value", 0.0) or 0.0)
        dss_value = float(row.get("DSS_Mapped_Value", 0.0) or 0.0)
        fd_mapped = float(row.get("First_Discovery_Mapped_Value", 0.0) or 0.0)

        if was_mapped:
            base_value = dss_value
        else:
            base_value = fss_value

        stats.c_cartography += base_value

        # Bonus First Discovery (dla planet / ciał)
        bonus = 0.0
        if was_discovered is False or was_discovered == 0:
            if was_mapped and dss_value > 0:
                # Różnica między „zwykłym” DSS a „First Discovery mapped”
                bonus = max(0.0, fd_mapped - dss_value)
            elif fss_value > 0 and dss_value > 0:
                # Przy braku osobnej kolumny dla FSS+FD — przybliżenie:
                ratio = fd_mapped / dss_value if dss_value else 1.0
                bonus = max(0.0, fss_value * (ratio - 1.0))

        stats.bonus_discovery += bonus
        if bonus > 0:
            stats.any_discovery_bonuses = True

        # High-Value Targets (ELW / WW / terraformable)
        if self._is_high_value_target(body_type, terraformable):
            stats.high_value_targets.append(
                {
                    "body_id": body_id,
                    "body_type": body_type,
                    "terraformable": terraformable,
                    "estimated_value": base_value + bonus,
                }
            )

    def analyze_biology_event(self, event: Dict[str, Any]) -> None:
        """
        Analiza eventu związanego z exobiology.

        Obsługujemy generycznie eventy typu:
        - CodexEntry / ScanOrganic / inne z polami:
          Name_Localised / Species_Localised / Species / Genus_Localised / Genus / Name

        Dodatkowe flagi (jeśli występują):
        - FirstDiscovery / IsNewSpecies / NewSpecies
        - FirstFootfall / FirstScan
        """
        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            return

        stats = self._get_or_create_system(system_name)

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

        # dolicz bazową wartość biologii
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

        # First Footfall: zakładamy, że total_ff = base + fd_bonus + extra_ff
        if is_first_footfall and total_ff > 0:
            extra_ff = max(0.0, total_ff - (base_value + fd_bonus))
            bonus += extra_ff

        stats.bonus_discovery += bonus
        if bonus > 0:
            stats.any_discovery_bonuses = True

    def analyze_discovery_meta_event(self, event: Dict[str, Any]) -> None:
        """
        Analiza meta-informacji discovery, które nie są czystym Scan/Biology.

        Wspieramy m.in.:
        - event z polem FirstDiscoveredBy (np. Explore / SAAScanComplete wrapper),
        - FSSSignalDiscovered (sygnały odkryte przez CMDR),
        - ogólne CodexEntry z flagami IsNewDiscovery / NewDiscoveries.

        To jest "miękka" logika – nie rusza kredytów, tylko status.
        """
        system_name = event.get("StarSystem") or self.current_system
        if not system_name:
            return

        stats = self._get_or_create_system(system_name)
        ev_type = event.get("event")

        # 1) FirstDiscoveredBy – jeśli w ogóle istnieje, wiemy, że system ma „autora”
        first_by = event.get("FirstDiscoveredBy")
        if first_by:
            # Niekoniecznie my, ale to oznacza, że system nie jest dziewiczy
            stats.system_previously_discovered = True

        # 2) FSSSignalDiscovered – wiemy, że coś odkryliśmy w tym systemie,
        # ale nie przesądza to o dziewiczości całego układu.
        if ev_type == "FSSSignalDiscovered":
            # To raczej meta-info: „coś nowego w tym systemie”
            # Możemy jedynie traktować to jako sygnał, że discovery w ogóle istnieje.
            stats.any_discovery_bonuses = True

        # 3) CodexEntry z flagami nowości
        if ev_type == "CodexEntry":
            if event.get("IsNewDiscovery") or event.get("NewDiscoveries"):
                # Mamy nową odkrytą rzecz w tym systemie
                stats.any_discovery_bonuses = True
                # Jeśli system_previously_discovered nie został oznaczony jako True,
                # nie nadpisujemy go tutaj – to może być nowy wpis w starym systemie.

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

        # Definicja „dziewiczego systemu”:
        # wszystkie ZESKANOWANE ciała miały WasDiscovered == False
        # (z naszej perspektywy w tym locie).
        is_virgin_system = (
            stats.total_scanned_bodies > 0
            and stats.bodies_first_discovery_count == stats.total_scanned_bodies
        )

        # Jeśli mamy jednocześnie first i previously – system jest na pewno znany.
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
        Zwraca sumaryczne wartości ze wszystkich systemów.

        Format:
        {
            "c_cartography": ...,
            "c_exobiology": ...,
            "bonus_discovery": ...,
            "total": ...
        }
        """
        c_carto = sum(s.c_cartography for s in self.systems.values())
        c_exo = sum(s.c_exobiology for s in self.systems.values())
        bonus = sum(s.bonus_discovery for s in self.systems.values())
        total = c_carto + c_exo + bonus

        return {
            "c_cartography": c_carto,
            "c_exobiology": c_exo,
            "bonus_discovery": bonus,
            "total": total,
        }

    # Dodatkowe helpery do debugowania / GUI (opcjonalne użycie)

    def get_system_stats(self, system_name: str) -> Optional[SystemStats]:
        """Zwraca obiekt SystemStats dla konkretnego układu (lub None)."""
        return self.systems.get(system_name)

    # ------------------------------------------------------------------
    # Implementacja pomocnicza
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_science_data(science_data: Any) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Normalizuje wejście science_data do tuple (exobio_df, carto_df).
        """
        if isinstance(science_data, tuple) and len(science_data) == 2:
            return science_data
        if isinstance(science_data, dict):
            return science_data["exobio"], science_data["carto"]
        raise ValueError(
            "science_data musi być tuple(exobio_df, carto_df) "
            "albo dict {'exobio': df, 'carto': df}"
        )

    def _get_or_create_system(self, name: str) -> SystemStats:
        if name not in self.systems:
            self.systems[name] = SystemStats(name=name)
        return self.systems[name]

    # --- Cartography helpers -------------------------------------------------

    def _extract_cartography_type(
        self, event: Dict[str, Any]
    ) -> Tuple[Optional[str], str]:
        """
        Wyciąga (Body_Type, Terraformable) w formacie zgodnym z arkuszem Cartography.

        Zwraca:
            (body_type, terraformable) – np. ("Water World", "Yes")

        Jeśli nie uda się ustalić typu – (None, "No").
        """
        terraform_state = str(event.get("TerraformState") or "").lower().strip()
        terraformable = "Yes" if terraform_state in {
            "terraformable",
            "terraforming",
            "terraformingcandidate",
            "candidate for terraforming",
        } else "No"

        planet_class = str(event.get("PlanetClass") or "").lower().strip()
        body_type = None

        # Najczęstsze klasy planet – mapowanie do Body_Type z Excela
        mapping = {
            "ammonia world": "Ammonia World",
            "earth-like world": "Earth-like World",
            "earthlike world": "Earth-like World",
            "water world": "Water World",
            "high metal content world": "High Metal Content Planet",
            "icy body": "Icy Body",
            "metal rich body": "Metal Rich Body",
            "rocky body": "Rocky Body",
            "rocky ice world": "Rocky Ice Body",
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
            # miękkie dopasowanie – capitalizacja, bez gwarancji
            candidate = planet_class.title()
            # np. "High Metal Content World" → spróbujmy zastąpić "World" na "Planet"
            if "high metal content world" in planet_class:
                body_type = "High Metal Content Planet"
            else:
                body_type = candidate

        if body_type is None:
            # Jeśli kompletnie nie rozpoznaliśmy – traktujemy jako „Planet Type” (fallback)
            body_type = "Planet Type"

        return body_type, terraformable

    def _lookup_cartography_row(
        self, body_type: str, terraformable: str
    ) -> Optional[pd.Series]:
        key = (body_type, terraformable)
        if key in self._carto_map:
            return self._carto_map[key]

        # Fallback: jeśli nie ma wariantu terraformable – spróbuj niezależnie od tej kolumny
        for (bt, tf), row in self._carto_map.items():
            if bt == body_type:
                return row

        # Ostateczny fallback: jeśli w arkuszu jest ogólny „Planet Type”
        key_generic = ("Planet Type", terraformable)
        return self._carto_map.get(key_generic)

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
        Normalizuje nazwę gatunku z Codex/Journal do formy jak w arkuszu Exobiology.

        Przykłady:
        - "$Codex_Ent_Aleoida_Arcus_Name;" → "Aleoida Arcus"
        - "Aleoida Arcus"                   → "Aleoida Arcus"
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
            # Zamiana underscore → spacja
            name = name.replace("_", " ")

        # Porządkujemy capitalizację (pierwsza litera wielka w każdym członie)
        name = " ".join(part.capitalize() for part in name.split())

        return name or None

    def _lookup_exobio_row(self, species_name: str) -> Optional[pd.Series]:
        key = species_name.strip().lower()
        row = self._exobio_map.get(key)
        if row is not None:
            return row

        # fallback – delikatniejsze porównanie: usuwamy spacje
        key_nospace = key.replace(" ", "")
        for k, v in self._exobio_map.items():
            if k.replace(" ", "") == key_nospace:
                return v

        return None
