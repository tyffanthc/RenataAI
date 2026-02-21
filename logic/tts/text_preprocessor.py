from __future__ import annotations

import re
from typing import Any, Dict, Optional

from logic.tts.message_templates import (
    allowed_message_ids,
    raw_text_first,
    template_for_message,
)

ALLOWED_MESSAGES = allowed_message_ids()


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


_PLAIN_POLISH_REPLACEMENTS = {
    "Skopiowalam": "Skopiowałam",
    "skopiowalam": "skopiowałam",
    "Nastepny": "Następny",
    "nastepny": "następny",
    "trase": "trasę",
    "Trase": "Trasę",
    "wejsciu": "wejściu",
    "Wejsciu": "Wejściu",
    "nieswieze": "nieświeże",
    "Nieswieze": "Nieświeże",
    "przeciazenie": "przeciążenie",
    "Przeciazenie": "Przeciążenie",
    "Blad": "Błąd",
    "blad": "błąd",
    "pokladzie": "pokładzie",
    "Pokladzie": "Pokładzie",
    "ladunek": "ładunek",
    "Ladunek": "Ładunek",
    "sredni": "średni",
    "Sredni": "Średni",
    "srednie": "średnie",
    "Srednie": "Średnie",
    "srednia": "średnia",
    "Srednia": "Średnia",
    "zakonczona": "zakończona",
    "Zakonczona": "Zakończona",
    "wzroslo": "wzrosło",
    "Wzroslo": "Wzrosło",
    "postepu": "postępu",
    "Postepu": "Postępu",
}


def _repair_polish_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    for broken, fixed in _MOJIBAKE_REPLACEMENTS.items():
        if broken in text:
            text = text.replace(broken, fixed)
    for plain, fixed in _PLAIN_POLISH_REPLACEMENTS.items():
        if plain in text:
            text = text.replace(plain, fixed)
    return text


def _render_template(message_id: str, **fields: Any) -> str:
    template = template_for_message(message_id)
    if not template:
        return ""
    normalized_fields: Dict[str, str] = {}
    for key, value in fields.items():
        normalized_fields[str(key)] = _repair_polish_text(value).strip()
    try:
        rendered = template.format(**normalized_fields)
    except KeyError:
        return template
    except Exception:
        return ""
    return _repair_polish_text(rendered).strip()


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
    if raw_text_first(message_id):
        raw_text = ctx.get("raw_text")
        if raw_text:
            fixed = _repair_polish_text(raw_text).strip()
            if fixed:
                return fixed

    if message_id == "MSG.EXPLORATION_SYSTEM_SUMMARY":
        system = _normalize_system_name(ctx.get("system"))
        if system:
            return _finalize_tts(f"Podsumowanie systemu {system} gotowe.")
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.CASH_IN_ASSISTANT":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.CASH_IN_STARTJUMP":
        return _finalize_tts(_render_template(message_id))

    if message_id in {"MSG.SURVIVAL_REBUY_HIGH", "MSG.SURVIVAL_REBUY_CRITICAL"}:
        return _finalize_tts(_render_template(message_id))

    if message_id in {"MSG.COMBAT_AWARENESS_HIGH", "MSG.COMBAT_AWARENESS_CRITICAL"}:
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.HIGH_G_WARNING":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.TRADE_DATA_STALE":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.PPM_SET_TARGET":
        target = _normalize_system_name(ctx.get("target"))
        if target:
            return _finalize_tts(_render_template(message_id, target=target))
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.PPM_PIN_ACTION":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.PPM_COPY_SYSTEM":
        system = _normalize_system_name(ctx.get("system"))
        if system:
            return _finalize_tts(_render_template(message_id, system=system))
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.RUNTIME_CRITICAL":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.NEXT_HOP":
        system = _normalize_system_name(ctx.get("system"))
        if not system:
            return None
        return _finalize_tts(_render_template(message_id, system=system))

    if message_id == "MSG.JUMPED_SYSTEM":
        system = _normalize_system_name(ctx.get("system"))
        if not system:
            return None
        return _finalize_tts(_render_template(message_id, system=system))

    if message_id == "MSG.NEXT_HOP_COPIED":
        system = _normalize_system_name(ctx.get("system"))
        if system:
            return _finalize_tts(_render_template(message_id, system=system))
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.ROUTE_COMPLETE":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.ROUTE_DESYNC":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FUEL_CRITICAL":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.DOCKED":
        station = _normalize_station_name(ctx.get("station"))
        if station:
            return _finalize_tts(_render_template(message_id, station=station))
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.UNDOCKED":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FIRST_DISCOVERY":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FIRST_DISCOVERY_OPPORTUNITY":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.BODY_NO_PREV_DISCOVERY":
        body = _repair_polish_text(ctx.get("body")).strip() if ctx.get("body") else ""
        if body:
            return _finalize_tts(f"Potwierdzono. {body}. Bez wcześniejszego odkrywcy.")
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.SYSTEM_FULLY_SCANNED":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FSS_PROGRESS_25":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FSS_PROGRESS_50":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FSS_PROGRESS_75":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FSS_LAST_BODY":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.MILESTONE_PROGRESS":
        percent = ctx.get("percent")
        target = _normalize_system_name(ctx.get("target"))
        try:
            percent_i = int(percent)
        except Exception:
            percent_i = None
        if percent_i is None:
            return _finalize_tts(_render_template(message_id))
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
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.ELW_DETECTED":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.FOOTFALL":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.ROUTE_FOUND":
        return _finalize_tts(_render_template(message_id))

    if message_id == "MSG.STARTUP_SYSTEMS":
        version = str(ctx.get("version", "")).strip()
        if version:
            return _finalize_tts(f"Renata. {version}. Startuję wszystkie systemy.")
        return _finalize_tts(_render_template(message_id))

    return None
