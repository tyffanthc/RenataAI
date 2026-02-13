from __future__ import annotations

import re
from typing import Any, Dict, Optional


ALLOWED_MESSAGES = {
    "MSG.NEXT_HOP",
    "MSG.JUMPED_SYSTEM",
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
    "MSG.SMUGGLER_ILLEGAL_CARGO",
    "MSG.WW_DETECTED",
    "MSG.TERRAFORMABLE_DETECTED",
    "MSG.BIO_SIGNALS_HIGH",
    "MSG.TRADE_JACKPOT",
    "MSG.EXOBIO_SAMPLE_LOGGED",
    "MSG.EXOBIO_NEW_ENTRY",
    "MSG.EXOBIO_RANGE_READY",
    "MSG.FSS_PROGRESS_25",
    "MSG.FSS_PROGRESS_50",
    "MSG.FSS_PROGRESS_75",
    "MSG.FSS_LAST_BODY",
    "MSG.MILESTONE_PROGRESS",
    "MSG.MILESTONE_REACHED",
    "MSG.STARTUP_SYSTEMS",
}


_MOJIBAKE_REPLACEMENTS = {
    # UTF-8 decoded as latin/cp125x (common Polish diacritics).
    "Ä…": "ą",
    "Ä‡": "ć",
    "Ä™": "ę",
    "Ä…": "ą",
    "Ä„": "Ą",
    "Ä†": "Ć",
    "Ä˜": "Ę",
    "Å‚": "ł",
    "Å": "Ł",
    "Å„": "ń",
    "Åƒ": "Ń",
    "Ã³": "ó",
    "Ã“": "Ó",
    "Ăł": "ó",
    "Ă“": "Ó",
    "Å›": "ś",
    "Åš": "Ś",
    "Åº": "ź",
    "Å¹": "Ź",
    "Å¼": "ż",
    "Å»": "Ż",
    # Second mojibake family visible in project logs/source snippets.
    "Ĺ‚": "ł",
    "Ĺ": "Ł",
    "Ĺ„": "ń",
    "Ĺƒ": "Ń",
    "Ĺ›": "ś",
    "Ĺš": "Ś",
    "Ĺº": "ź",
    "Ĺ¹": "Ź",
    "Ĺ¼": "ż",
    "Ĺ»": "Ż",
    # Punctuation artifacts.
    "â€“": "-",
    "â€”": "-",
    "â€ž": "\"",
    "â€ť": "\"",
    "â€œ": "\"",
    "â€": "\"",
    "â€™": "'",
    "â€˜": "'",
    "Â ": " ",
}


def _repair_polish_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    for broken, fixed in _MOJIBAKE_REPLACEMENTS.items():
        if broken in text:
            text = text.replace(broken, fixed)
    return text


def _normalize_system_name(value: Any) -> str:
    if value is None:
        return ""
    text = _repair_polish_text(value).strip()
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
    text = _repair_polish_text(value).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _finalize_tts(text: str) -> str:
    text = _repair_polish_text(text)
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
    if message_id in {
        "MSG.ELW_DETECTED",
        "MSG.SMUGGLER_ILLEGAL_CARGO",
        "MSG.WW_DETECTED",
        "MSG.TERRAFORMABLE_DETECTED",
        "MSG.BIO_SIGNALS_HIGH",
        "MSG.TRADE_JACKPOT",
        "MSG.EXOBIO_SAMPLE_LOGGED",
        "MSG.EXOBIO_NEW_ENTRY",
        "MSG.EXOBIO_RANGE_READY",
    }:
        raw_text = ctx.get("raw_text")
        if not raw_text:
            return None
        fixed = _repair_polish_text(raw_text).strip()
        if not fixed:
            return None
        return fixed

    if message_id == "MSG.NEXT_HOP":
        system = _normalize_system_name(ctx.get("system"))
        if not system:
            return None
        return _finalize_tts(f"Następny skok. {system}.")

    if message_id == "MSG.JUMPED_SYSTEM":
        system = _normalize_system_name(ctx.get("system"))
        if not system:
            return None
        return _finalize_tts(f"Aktualnie w {system}.")

    if message_id == "MSG.NEXT_HOP_COPIED":
        system = _normalize_system_name(ctx.get("system"))
        if system:
            return _finalize_tts(f"Cel skopiowany. {system}.")
        return _finalize_tts("Cel skopiowany.")

    if message_id == "MSG.ROUTE_COMPLETE":
        return _finalize_tts("Trasa zakończona.")

    if message_id == "MSG.ROUTE_DESYNC":
        return _finalize_tts("Poza trasą. Nawigacja wstrzymana.")

    if message_id == "MSG.FUEL_CRITICAL":
        return _finalize_tts("Uwaga. Paliwo krytyczne.")

    if message_id == "MSG.DOCKED":
        station = _normalize_station_name(ctx.get("station"))
        if station:
            return _finalize_tts(f"Zadokowano. {station}.")
        return _finalize_tts("Zadokowano.")

    if message_id == "MSG.UNDOCKED":
        return _finalize_tts("Odlot potwierdzony.")

    if message_id == "MSG.FIRST_DISCOVERY":
        return _finalize_tts("Pierwsze odkrycie. Układ potwierdzony.")

    if message_id == "MSG.SYSTEM_FULLY_SCANNED":
        return _finalize_tts("Skan systemu zakończony.")

    if message_id == "MSG.FSS_PROGRESS_25":
        return _finalize_tts("Dwadziescia piec procent systemu przeskanowane.")

    if message_id == "MSG.FSS_PROGRESS_50":
        return _finalize_tts("Połowa systemu przeskanowana.")

    if message_id == "MSG.FSS_PROGRESS_75":
        return _finalize_tts("Siedemdziesiat piec procent systemu przeskanowane.")

    if message_id == "MSG.FSS_LAST_BODY":
        return _finalize_tts("Ostatnia planeta do skanowania.")

    if message_id == "MSG.MILESTONE_PROGRESS":
        percent = ctx.get("percent")
        target = _normalize_system_name(ctx.get("target"))
        try:
            percent_i = int(percent)
        except Exception:
            percent_i = None
        if percent_i is None:
            return _finalize_tts("Trwa lot do kolejnego celu.")
        if target:
            return _finalize_tts(f"Do boosta. {percent_i}% drogi. Cel. {target}.")
        return _finalize_tts(f"Do boosta. {percent_i}% drogi.")

    if message_id == "MSG.MILESTONE_REACHED":
        target = _normalize_system_name(ctx.get("target"))
        next_target = _normalize_system_name(ctx.get("next_target"))
        if target:
            if next_target:
                return _finalize_tts(
                    f"Cel odcinka osiągnięty. {target}. Przechodzę do kolejnego celu. {next_target}."
                )
            return _finalize_tts(f"Cel odcinka osiągnięty. {target}.")
        return _finalize_tts("Cel odcinka osiągnięty.")

    if message_id == "MSG.ELW_DETECTED":
        return _finalize_tts("Wykryto planetę ziemiopodobną. Wysoka wartość.")

    if message_id == "MSG.FOOTFALL":
        return _finalize_tts("Pierwszy krok zarejestrowany.")

    if message_id == "MSG.ROUTE_FOUND":
        return _finalize_tts("Trasa wyznaczona.")

    if message_id == "MSG.STARTUP_SYSTEMS":
        version = str(ctx.get("version", "")).strip()
        if version:
            return _finalize_tts(f"Renata. {version}. Startuję wszystkie systemy.")
        return _finalize_tts("Renata. Startuję wszystkie systemy.")

    return None
