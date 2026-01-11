# logic/exit_summary.py
"""
Exit Summary Generator (EPIC 2)

Moduł odpowiedzialny za generowanie tekstowego podsumowania systemu
na podstawie danych z SystemValueEngine oraz (opcjonalnie) statystyk FSS.

Przykładowy output:

🔵 Exit Summary – HIP 12345

Skanowano 18/32 obiektów
🌍 1 × Earth-like (wartość: 27 000 000 Cr)
🌊 2 × Water Worlds (wartość: 6 200 000 Cr)
🔥 3 × terraformable HMC (wartość: 3 900 000 Cr)
🧬 Biologia: 2 gatunki (wartość: 19 600 000 Cr)
✨ First Discovery bonus: 12 000 000 Cr
💰 Łączna wartość systemu: 64 800 000 Cr
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any, Dict, List


@dataclass
class ExitSummaryData:
    system_name: str
    scanned_bodies: Optional[int] = None
    total_bodies: Optional[int] = None

    elw_count: int = 0
    elw_value: float = 0.0

    ww_count: int = 0          # wszystkie Water Worlds
    ww_value: float = 0.0

    # EPIC 4 – terraformable Water Worlds
    ww_t_count: int = 0
    ww_t_value: float = 0.0

    # EPIC 4 – High Metal Content (HMC)
    hmc_t_count: int = 0       # terraformable HMC
    hmc_t_value: float = 0.0
    hmc_n_count: int = 0       # zwykłe HMC (non-terraformable)
    hmc_n_value: float = 0.0

    biology_species_count: int = 0
    biology_value: float = 0.0

    bonus_discovery: float = 0.0
    c_cartography: float = 0.0
    c_exobiology: float = 0.0
    total_value: float = 0.0

    # --- Discovery status (EPIC 3) ---
    discovery_system_previously_discovered: Optional[bool] = None
    discovery_any_virgin_bodies: bool = False
    discovery_has_bonuses: bool = False
    discovery_is_virgin_system: bool = False



class ExitSummaryGenerator:
    """
    Generator tekstowego podsumowania systemu.

    Oczekuje instancji SystemValueEngine, która udostępnia:
        - get_system_stats(system_name) -> SystemStats lub None

    SystemStats powinien zawierać co najmniej:
        - c_cartography (float)
        - c_exobiology (float)
        - bonus_discovery (float)
        - high_value_targets (lista dictów z polami:
              body_type, terraformable, estimated_value)
        - seen_species (set) – do policzenia liczby gatunków
    """

    def __init__(self, system_value_engine: Any):
        self.engine = system_value_engine

    # ------------------------------------------------------------------
    # Publiczny interfejs
    # ------------------------------------------------------------------

    def build_summary_data(
        self,
        system_name: str,
        scanned_bodies: Optional[int] = None,
        total_bodies: Optional[int] = None,
    ) -> Optional[ExitSummaryData]:
        """
        Buduje ExitSummaryData dla podanego systemu.

        Jeśli brak danych w SystemValueEngine – zwraca None.
        """
        stats = getattr(self.engine, "get_system_stats", lambda _: None)(system_name)
        if stats is None:
            return None

        data = ExitSummaryData(
            system_name=system_name,
            scanned_bodies=scanned_bodies,
            total_bodies=total_bodies,
        )

        data.c_cartography = float(getattr(stats, "c_cartography", 0.0) or 0.0)
        data.c_exobiology = float(getattr(stats, "c_exobiology", 0.0) or 0.0)
        data.bonus_discovery = float(getattr(stats, "bonus_discovery", 0.0) or 0.0)
        data.total_value = data.c_cartography + data.c_exobiology + data.bonus_discovery
        # Discovery status (EPIC 3)
        if hasattr(self.engine, "get_discovery_status"):
            ds = self.engine.get_discovery_status(system_name)
            if ds:
                data.discovery_system_previously_discovered = ds.get("system_previously_discovered")
                data.discovery_any_virgin_bodies = bool(ds.get("any_virgin_bodies", False))
                data.discovery_has_bonuses = bool(ds.get("has_bonuses", False))
                data.discovery_is_virgin_system = bool(ds.get("is_virgin_system", False))


        # Biologia – liczba gatunków i wartość
        seen_species = getattr(stats, "seen_species", None)
        if isinstance(seen_species, (set, list, tuple)):
            data.biology_species_count = len(seen_species)
        else:
            data.biology_species_count = 0
        data.biology_value = data.c_exobiology  # na razie 1:1, bo c_exobiology = suma baz

        # High value targets
        hv_targets: List[Dict[str, Any]] = getattr(stats, "high_value_targets", []) or []

        for t in hv_targets:
            body_type = str(t.get("body_type", "")).strip()
            terraformable = str(t.get("terraformable", "")).strip()
            value = float(t.get("estimated_value", 0.0) or 0.0)

            # Earth-like World
            if body_type == "Earth-like World":
                data.elw_count += 1
                data.elw_value += value

            # Water Worlds (łącznie)
            if body_type == "Water World":
                data.ww_count += 1
                data.ww_value += value
                # EPIC 4 – terraformable Water World
                if terraformable == "Yes":
                    data.ww_t_count += 1
                    data.ww_t_value += value

            # High Metal Content Planet – rozdzielenie terraformable / zwykłe
            if body_type == "High Metal Content Planet":
                if terraformable == "Yes":
                    data.hmc_t_count += 1
                    data.hmc_t_value += value
                else:
                    data.hmc_n_count += 1
                    data.hmc_n_value += value


        return data

    def format_summary_text(self, data: ExitSummaryData) -> str:
        """
        Zwraca gotowy tekst raportu w stylu:

        🔵 Exit Summary – HIP 12345

        Skanowano 18/32 obiektów
        ...
        """
        lines: List[str] = []

        # Nagłówek
        lines.append(f"🔵 Exit Summary – {data.system_name}")
        lines.append("")  # pusta linia

        # Skanowanie
        if data.scanned_bodies is not None and data.total_bodies is not None:
            lines.append(
                f"Skanowano {data.scanned_bodies}/{data.total_bodies} obiektów"
            )
        elif data.scanned_bodies is not None:
            lines.append(f"Skanowano {data.scanned_bodies} obiektów")
        lines.append("")  # pusta linia (nawet jeśli brak licznika – zostawmy odstęp)

        # High value targets
        if data.elw_count > 0:
            lines.append(
                f"🌍 Earth-like Worlds: {data.elw_count} "
                f"(wartość: {format_credits(data.elw_value)})"
            )

        if data.ww_count > 0:
            # ogólna linia dla wszystkich Water Worlds (jak w przykładzie z EPIC 4)
            lines.append(
                f"🌊 Water Worlds: {data.ww_count} "
                f"(wartość: {format_credits(data.ww_value)})"
            )

        # EPIC 4 – terraformable Water Worlds (dodatkowa linia, jeśli występują)
        if data.ww_t_count > 0:
            lines.append(
                f"💧 Terraformable Water Worlds: {data.ww_t_count} "
                f"(wartość: {format_credits(data.ww_t_value)})"
            )

        # EPIC 4 – High Metal Content
        if data.hmc_t_count > 0:
            lines.append(
                f"🔥 Terraformable HMC: {data.hmc_t_count} "
                f"(wartość: {format_credits(data.hmc_t_value)})"
            )

        if data.hmc_n_count > 0:
            lines.append(
                f"🪨 High Metal Content (non-terraformable): {data.hmc_n_count} "
                f"(wartość: {format_credits(data.hmc_n_value)})"
            )


        # Biologia
        if data.biology_species_count > 0 or data.biology_value > 0:
            lines.append(
                f"🧬 Biologia: {data.biology_species_count} gatunki "
                f"(wartość: {format_credits(data.biology_value)})"
            )

        # Bonus discovery – pokazujemy zawsze, żeby była jasność
        lines.append(
            f"✨ First Discovery bonus: {format_credits(data.bonus_discovery)}"
        )

        # Komunikat o dziewiczym systemie / dziewiczych obiektach
        if data.discovery_is_virgin_system:
            lines.append(
                "✨ Ten system jest dziewiczy — wszystkie zeskanowane obiekty są warte ×2!"
            )
        elif data.discovery_any_virgin_bodies and data.discovery_has_bonuses:
            lines.append(
                "✨ W tym systemie odkryto dziewicze obiekty — otrzymasz bonusy za First Discovery."
            )

        # Łączna wartość systemu
        lines.append(
            f"💰 Łączna wartość systemu: {format_credits(data.total_value)}"
        )


        return "\n".join(lines)

    # Szybka ścieżka: wszystko w jednym kroku
    def build_and_format(
        self,
        system_name: str,
        scanned_bodies: Optional[int] = None,
        total_bodies: Optional[int] = None,
    ) -> Optional[str]:
        data = self.build_summary_data(
            system_name=system_name,
            scanned_bodies=scanned_bodies,
            total_bodies=total_bodies,
        )
        if data is None:
            return None
        return self.format_summary_text(data)


# ----------------------------------------------------------------------
# Funkcje pomocnicze
# ----------------------------------------------------------------------


def format_credits(value: float) -> str:
    """
    Formatuje kredyty w stylu: 64 800 000 Cr.

    (Bez skracania do M/B – niech VoiceEngine zajmie się mową).
    """
    # Zaokrąglamy do pełnych kredytów
    rounded = int(round(value))
    # Format z separatorem spacji tysiąca
    parts = []
    s = str(abs(rounded))
    while s:
        parts.insert(0, s[-3:])
        s = s[:-3]
    out = " ".join(parts)
    if rounded < 0:
        out = "-" + out
    return f"{out} Cr"
