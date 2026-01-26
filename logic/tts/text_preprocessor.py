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


def _finalize_tts(text: str) -> str:
    text = text.replace("?", ".").replace("!", ".").replace(",", ".")
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\.\s*", ". ", text).strip()
    if not text.endswith("."):
        text += "."
    return text


def prepare_tts(message_id: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if not message_id or message_id not in ALLOWED_MESSAGES:
        return None
    ctx = context or {}

    if message_id == "MSG.NEXT_HOP":
        system = _normalize_system_name(ctx.get("system"))
        if not system:
            return None
        return _finalize_tts(f"Nastepny skok. {system}.")

    if message_id == "MSG.NEXT_HOP_COPIED":
        system = _normalize_system_name(ctx.get("system"))
        if system:
            return _finalize_tts(f"Nastepny cel skopiowany. {system}.")
        return _finalize_tts("Nastepny cel skopiowany.")

    if message_id == "MSG.ROUTE_COMPLETE":
        return _finalize_tts("Trasa zakonczona.")

    if message_id == "MSG.ROUTE_DESYNC":
        return _finalize_tts("Jestes poza trasa.")

    if message_id == "MSG.FUEL_CRITICAL":
        return _finalize_tts("Uwaga. Niskie paliwo.")

    if message_id == "MSG.DOCKED":
        station = _normalize_station_name(ctx.get("station"))
        if station:
            return _finalize_tts(f"Zadokowano w {station}.")
        return _finalize_tts("Zadokowano.")

    if message_id == "MSG.UNDOCKED":
        return _finalize_tts("Odlot z portu.")

    if message_id == "MSG.FIRST_DISCOVERY":
        return _finalize_tts("Gratulacje. Pierwszy czlowiek w tym ukladzie.")

    if message_id == "MSG.SYSTEM_FULLY_SCANNED":
        return _finalize_tts("System w pelni przeskanowany.")

    if message_id == "MSG.ELW_DETECTED":
        return _finalize_tts("Wykryto planete ziemiopodobna.")

    if message_id == "MSG.FOOTFALL":
        return _finalize_tts("Pierwszy ludzki krok na tej planecie.")

    if message_id == "MSG.ROUTE_FOUND":
        return _finalize_tts("Trasa wyznaczona.")

    return None
