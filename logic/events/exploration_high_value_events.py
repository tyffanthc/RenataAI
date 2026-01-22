# logic/events/exploration_high_value_events.py

from __future__ import annotations

from typing import Any, Dict

from logic.utils import powiedz


# --- HIGH VALUE PLANETS (S2-LOGIC-03) ---
HV_ELW_WARNED = False          # Earth-like World
HV_WW_WARNED = False           # Water World
HV_HMC_T_WARNED = False        # Terraformable HMC


def reset_high_value_flags() -> None:
    """Resetuje lokalne flagi anty-spam dla wysokowartościowych planet."""
    global HV_ELW_WARNED, HV_WW_WARNED, HV_HMC_T_WARNED
    HV_ELW_WARNED = False
    HV_WW_WARNED = False
    HV_HMC_T_WARNED = False


def check_high_value_planet(ev: Dict[str, Any], gui_ref=None):
    """
    S2-LOGIC-03 — Wykrywanie wysokowartościowych planet
    (ELW / Water World / Terraformable HMC)

    Przeniesione z EventHandler._check_high_value_planet.
    """
    # Brak GUI lub brak danych naukowych – nie robimy nic
    if gui_ref is None or not hasattr(gui_ref, "carto_df"):
        return
    carto_df = getattr(gui_ref, "carto_df", None)
    if carto_df is None:
        return

    planet_class_raw = ev.get("PlanetClass") or ""
    if not planet_class_raw:
        return

    planet_class = str(planet_class_raw).lower()
    terraform_state = str(ev.get("TerraformState") or "").lower()

    # Dostęp do globalnych flag anty-spam
    global HV_ELW_WARNED, HV_WW_WARNED, HV_HMC_T_WARNED

    # Helper do sprawdzania, czy dany typ istnieje w arkuszu Cartography
    def has_body_type(keyword: str, terraformable: str | None = None) -> bool:
        try:
            df = carto_df.copy()
            df["Body_Type_norm"] = df["Body_Type"].astype(str).str.lower()
            mask = df["Body_Type_norm"].str.contains(keyword, na=False)
            if terraformable is not None:
                df["Terraformable_norm"] = df["Terraformable"].astype(str).str.lower()
                mask &= df["Terraformable_norm"] == terraformable
            return bool(df[mask].shape[0] > 0)
        except Exception:
            # Jeśli coś jest nie tak z danymi – po prostu nie generujemy komunikatu
            return False

    # 1) Earth-like World
    if (
        (not HV_ELW_WARNED)
        and "earth-like" in planet_class
        and has_body_type("earth-like")
    ):
        powiedz(
            "Wykryto planetę ziemiopodobną. To żyła złota.",
            gui_ref,
            message_id="MSG.ELW_DETECTED",
        )
        HV_ELW_WARNED = True
        return  # priorytet – nie robimy pozostałych komunikatów dla tego samego skanu

    # 2) Water World
    if (
        (not HV_WW_WARNED)
        and "water world" in planet_class
        and has_body_type("water world")
    ):
        powiedz("Wykryto oceaniczny świat – bardzo wartościowy.", gui_ref)
        HV_WW_WARNED = True
        return

    # 3) Terraformable High Metal Content World
    # Warunek: klasa HMC + terraformable w stanie
    if (
        (not HV_HMC_T_WARNED)
        and "high metal content" in planet_class
        and ("terra" in terraform_state)
        and has_body_type("high metal content", terraformable="yes")
    ):
        powiedz("Wykryto terraformowalny świat.", gui_ref)
        HV_HMC_T_WARNED = True
