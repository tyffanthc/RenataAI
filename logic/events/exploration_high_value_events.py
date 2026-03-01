# logic/events/exploration_high_value_events.py

from __future__ import annotations

from typing import Any, Dict

from app.state import app_state
from logic.events.exploration_awareness import emit_callout_or_summary
from logic.utils.renata_log import log_event_throttled


# --- HIGH VALUE PLANETS (S2-LOGIC-03) ---
# Track notified bodies per session instead of one global flag per class.
HV_SCANNED_BODIES: Set[str] = set()


def _body_label(ev: Dict[str, Any]) -> str:
    body = ev.get("BodyName") or ev.get("Body") or ev.get("BodyID") or ""
    return str(body).strip()


def _system_label(ev: Dict[str, Any]) -> str:
    system = ev.get("StarSystem") or ev.get("SystemName") or ev.get("StarSystemName")
    if system:
        return str(system).strip()
    return str(getattr(app_state, "current_system", "") or "").strip()


def _dss_hint_text(body: str, fallback: str) -> str:
    if body:
        return f"Planeta {body} jest warta dogłębnej analizy DSS."
    return fallback


def reset_high_value_flags() -> None:
    """Reset local anti-spam flags for high-value planet alerts."""
    global HV_SCANNED_BODIES
    HV_SCANNED_BODIES = set()


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

    global HV_SCANNED_BODIES

    body_id = ev.get("BodyID")
    body = _body_label(ev)
    body_key = str(body_id).strip() if body_id is not None else body
    body_key = str(body_key or "").strip()
    if not body_key:
        return
    if body_key in HV_SCANNED_BODIES:
        return

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
            log_event_throttled(
                "exploration.high_value.has_body_type",
                5000,
                "EXPL",
                "high-value cartography lookup failed",
                keyword=keyword,
                terraformable=terraformable,
                planet_class=planet_class,
            )
            return False

    raw_text: str | None = None
    callout_key: str | None = None

    # 1) Earth-like World
    if "earth-like" in planet_class and has_body_type("earth-like"):
        raw_text = _dss_hint_text(body, "Wykryto planetę ziemiopodobną. Wysoka wartość.")
        callout_key = f"hv_dss_hint:elw:{body_key}"

    # 2) Water World
    elif "water world" in planet_class and has_body_type("water world"):
        raw_text = _dss_hint_text(body, "Wykryto oceaniczny świat. Bardzo wartościowy.")
        callout_key = f"hv_dss_hint:ww:{body_key}"

    # 3) Terraformable High Metal Content World
    elif (
        "high metal content" in planet_class
        and ("terra" in terraform_state)
        and has_body_type("high metal content", terraformable="yes")
    ):
        raw_text = _dss_hint_text(body, "Wykryto terraformowalny świat.")
        callout_key = f"hv_dss_hint:hmc_terraformable:{body_key}"

    if raw_text and callout_key:
        emit_callout_or_summary(
            text=raw_text,
            gui_ref=gui_ref,
            message_id="MSG.HIGH_VALUE_DSS_HINT",
            source="exploration_high_value_events",
            system_name=_system_label(ev),
            body_name=body,
            callout_key=callout_key,
            event_type="BODY_DISCOVERED",
            priority="P2_NORMAL",
            context={"raw_text": raw_text, "body": body},
        )
        HV_SCANNED_BODIES.add(body_key)
