from __future__ import annotations

import re
from typing import Any, Dict, Optional


ALLOWED_MESSAGES = {
    "MSG.NEXT_HOP",
    "MSG.NEXT_HOP_COPIED",
    "MSG.ROUTE_COMPLETE",
    "MSG.ROUTE_DESYNC",
    "MSG.FUEL_CRITICAL",
    "MSG.DOCKED",
    "MSG.UNDOCKED",
    "MSG.FIRST_DISCOVERY",
    "MSG.SYSTEM_FULLY_SCANNED",
    "MSG.ELW_DETECTED",
    "MSG.FOOTFALL",
    "MSG.ROUTE_FOUND",
}


def _normalize_system_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("-", " ")
    text = re.sub(r"[_/]+", " ", text)
    text = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", text)
    text = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_station_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def prepare_tts(message_id: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if not message_id or message_id not in ALLOWED_MESSAGES:
        return None
    ctx = context or {}

    if message_id == "MSG.NEXT_HOP":
        system = _normalize_system_name(ctx.get("system"))
        if not system:
            return None
        return f"Nastepny skok. {system}."

    if message_id == "MSG.NEXT_HOP_COPIED":
        system = _normalize_system_name(ctx.get("system"))
        if system:
            return f"Nastepny cel skopiowany. {system}."
        return "Nastepny cel skopiowany."

    if message_id == "MSG.ROUTE_COMPLETE":
        return "Trasa zakonczona."

    if message_id == "MSG.ROUTE_DESYNC":
        return "Jestes poza trasa."

    if message_id == "MSG.FUEL_CRITICAL":
        return "Uwaga. Niskie paliwo."

    if message_id == "MSG.DOCKED":
        station = _normalize_station_name(ctx.get("station"))
        if station:
            return f"Zadokowano w {station}."
        return "Zadokowano."

    if message_id == "MSG.UNDOCKED":
        return "Odlot z portu."

    if message_id == "MSG.FIRST_DISCOVERY":
        return "Gratulacje. Pierwszy czlowiek w tym ukladzie."

    if message_id == "MSG.SYSTEM_FULLY_SCANNED":
        return "System w pelni przeskanowany."

    if message_id == "MSG.ELW_DETECTED":
        return "Wykryto planete ziemiopodobna."

    if message_id == "MSG.FOOTFALL":
        return "Pierwszy ludzki krok na tej planecie."

    if message_id == "MSG.ROUTE_FOUND":
        return "Trasa wyznaczona."

    return None
