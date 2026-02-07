# logic/events/exploration_high_value_events.py

from __future__ import annotations

from typing import Any, Dict

from logic.utils import powiedz


# --- HIGH VALUE PLANETS (S2-LOGIC-03) ---
HV_ELW_WARNED = False          # Earth-like World
HV_WW_WARNED = False           # Water World
HV_HMC_T_WARNED = False        # Terraformable HMC


def _body_label(ev: Dict[str, Any]) -> str:
    body = ev.get("BodyName") or ev.get("Body") or ev.get("BodyID") or ""
    return str(body).strip()


def _dss_hint_text(body: str, fallback: str) -> str:
    if body:
        return f"Planeta {body} jest warta doglebnej analizy DSS."
    return fallback


def reset_high_value_flags() -> None:
    """Reset local anti-spam flags for high-value planet alerts."""
    global HV_ELW_WARNED, HV_WW_WARNED, HV_HMC_T_WARNED
    HV_ELW_WARNED = False
    HV_WW_WARNED = False
    HV_HMC_T_WARNED = False


def check_high_value_planet(ev: Dict[str, Any], gui_ref=None):
    """
    S2-LOGIC-03 - Detect high-value planets:
    ELW / Water World / Terraformable HMC.
    """
    # No GUI/dataframe -> no-op
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

    global HV_ELW_WARNED, HV_WW_WARNED, HV_HMC_T_WARNED

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
            return False

    # 1) Earth-like World
    if (
        (not HV_ELW_WARNED)
        and "earth-like" in planet_class
        and has_body_type("earth-like")
    ):
        body = _body_label(ev)
        raw_text = _dss_hint_text(body, "Wykryto planete ziemiopodobna. Wysoka wartosc.")
        powiedz(
            raw_text,
            gui_ref,
            message_id="MSG.ELW_DETECTED",
            context={"raw_text": raw_text, "body": body},
        )
        HV_ELW_WARNED = True
        return

    # 2) Water World
    if (
        (not HV_WW_WARNED)
        and "water world" in planet_class
        and has_body_type("water world")
    ):
        body = _body_label(ev)
        raw_text = _dss_hint_text(body, "Wykryto oceaniczny swiat. Bardzo wartosciowy.")
        powiedz(
            raw_text,
            gui_ref,
            message_id="MSG.WW_DETECTED",
            context={"raw_text": raw_text, "body": body},
        )
        HV_WW_WARNED = True
        return

    # 3) Terraformable High Metal Content World
    if (
        (not HV_HMC_T_WARNED)
        and "high metal content" in planet_class
        and ("terra" in terraform_state)
        and has_body_type("high metal content", terraformable="yes")
    ):
        body = _body_label(ev)
        raw_text = _dss_hint_text(body, "Wykryto terraformowalny swiat.")
        powiedz(
            raw_text,
            gui_ref,
            message_id="MSG.TERRAFORMABLE_DETECTED",
            context={"raw_text": raw_text, "body": body},
        )
        HV_HMC_T_WARNED = True
