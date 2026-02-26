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
    "Rozwaz": "Rozważ",
    "rozwaz": "rozważ",
    "domknieciu": "domknięciu",
    "Domknieciu": "Domknięciu",
    "pozniej": "później",
    "Pozniej": "Później",
}

_UNITS_0_19 = {
    0: "zero",
    1: "jeden",
    2: "dwa",
    3: "trzy",
    4: "cztery",
    5: "pięć",
    6: "sześć",
    7: "siedem",
    8: "osiem",
    9: "dziewięć",
    10: "dziesięć",
    11: "jedenaście",
    12: "dwanaście",
    13: "trzynaście",
    14: "czternaście",
    15: "piętnaście",
    16: "szesnaście",
    17: "siedemnaście",
    18: "osiemnaście",
    19: "dziewiętnaście",
}
_TENS = {
    2: "dwadzieścia",
    3: "trzydzieści",
    4: "czterdzieści",
    5: "pięćdziesiąt",
    6: "sześćdziesiąt",
    7: "siedemdziesiąt",
    8: "osiemdziesiąt",
    9: "dziewięćdziesiąt",
}
_HUNDREDS = {
    1: "sto",
    2: "dwieście",
    3: "trzysta",
    4: "czterysta",
    5: "pięćset",
    6: "sześćset",
    7: "siedemset",
    8: "osiemset",
    9: "dziewięćset",
}
_GROUPS = [
    ("", "", ""),
    ("tysiąc", "tysiące", "tysięcy"),
    ("milion", "miliony", "milionów"),
    ("miliard", "miliardy", "miliardów"),
    ("bilion", "biliony", "bilionów"),
]
_GROUPED_INT_SEP_CLASS = r" \u00A0\u202F,.'"
_GROUPED_INT_PATTERN = re.compile(
    rf"(?:\d+|\d{{1,3}}(?:[{_GROUPED_INT_SEP_CLASS}]\d{{3}})+)"
)
_CREDITS_NUMBER_RE = re.compile(
    rf"(?<![\d,\.\u00A0\u202F'])\b(?P<num>{_GROUPED_INT_PATTERN.pattern})\s*(?:Cr|CR|cr)\b"
)
_STANDALONE_NUMBER_RE = re.compile(
    rf"(?<![\d,\.\u00A0\u202F'])\b(?P<num>(?:\d{{1,3}}(?:[{_GROUPED_INT_SEP_CLASS}]\d{{3}})+|\d+))\b"
    rf"(?!\s*(?:Cr|CR|cr)\b)(?!\s*%)(?!\s*(?:LY|ly)\b)(?![.,]\d)"
)
_NUMBER_GROUP_WORD_RE = re.compile(
    r"\b(?:tysiąc|tysiące|tysięcy|milion|miliony|milionów|miliard|miliardy|miliardów|bilion|biliony|bilionów)\b"
)


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


def _plural_form_pl(value: int, one: str, few: str, many: str) -> str:
    n = abs(int(value))
    if n == 1:
        return one
    if 10 <= (n % 100) <= 19:
        return many
    if 2 <= (n % 10) <= 4:
        return few
    return many


def _int_to_words_pl_under_1000(value: int) -> str:
    n = abs(int(value))
    parts: list[str] = []
    h = n // 100
    if h:
        parts.append(_HUNDREDS.get(h, ""))
    rem = n % 100
    if rem in _UNITS_0_19:
        if rem:
            parts.append(_UNITS_0_19[rem])
    else:
        t = rem // 10
        u = rem % 10
        if t:
            parts.append(_TENS.get(t, ""))
        if u:
            parts.append(_UNITS_0_19[u])
    return " ".join(x for x in parts if x).strip()


def _int_to_words_pl(value: int) -> str:
    n = int(value)
    if n == 0:
        return _UNITS_0_19[0]
    sign = "minus " if n < 0 else ""
    n_abs = abs(n)
    group_idx = 0
    parts_rev: list[str] = []
    while n_abs > 0:
        group_val = n_abs % 1000
        n_abs //= 1000
        if group_val:
            words = _int_to_words_pl_under_1000(group_val)
            if group_idx == 0:
                chunk = words
            else:
                one, few, many = _GROUPS[group_idx] if group_idx < len(_GROUPS) else (
                    f"10^{group_idx*3}",
                    f"10^{group_idx*3}",
                    f"10^{group_idx*3}",
                )
                # "jeden tysiąc" -> "tysiąc", but "jeden milion" is acceptable and clearer for TTS.
                if group_idx == 1 and group_val == 1:
                    chunk = one
                else:
                    chunk = f"{words} {_plural_form_pl(group_val, one, few, many)}".strip()
            parts_rev.append(chunk.strip())
        group_idx += 1
    return sign + " ".join(reversed([x for x in parts_rev if x])).strip()


def _decimal_to_words_pl(value_text: str) -> str:
    text = _repair_polish_text(value_text).strip()
    text = text.replace(" ", "")
    if not text:
        return ""
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    if "," in text:
        int_part, frac = text.split(",", 1)
    elif "." in text:
        int_part, frac = text.split(".", 1)
    else:
        try:
            return _int_to_words_pl(int(text))
        except Exception:
            return _repair_polish_text(value_text).strip()
    try:
        int_words = _int_to_words_pl(int(int_part or "0"))
    except Exception:
        return _repair_polish_text(value_text).strip()
    frac_digits = [ch for ch in frac if ch.isdigit()]
    if not frac_digits:
        return ("minus " if negative else "") + int_words
    frac_words = " ".join(_UNITS_0_19[int(ch)] for ch in frac_digits)
    return f"{'minus ' if negative else ''}{int_words} przecinek {frac_words}".strip()


def _parse_grouped_int(value_text: str) -> Optional[int]:
    text = _repair_polish_text(value_text).strip()
    if not text:
        return None
    if not _GROUPED_INT_PATTERN.fullmatch(text):
        return None
    digits = re.sub(rf"[{_GROUPED_INT_SEP_CLASS}]", "", text)
    try:
        return int(digits)
    except Exception:
        return None


def _with_tts_number_semicolon_breaks(number_words: str, *, unit: Optional[str] = None) -> str:
    """
    Piper-specific prosody helper: semicolons work as reliable micro-pauses/"reset"
    for long number phrases without changing the spoken words themselves.
    """
    words = _repair_polish_text(number_words).strip()
    if not words:
        return ""
    out = _NUMBER_GROUP_WORD_RE.sub(lambda m: f"{m.group(0)} ;", words)
    if unit:
        unit_txt = _repair_polish_text(unit).strip()
        if unit_txt:
            out = f"{out} ; {unit_txt}"
    else:
        out = f"{out} ;"
    out = "; " + out.lstrip()
    out = re.sub(r"\s*;\s*", " ; ", out)
    out = re.sub(r"(?:\s;\s){2,}", " ; ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _verbalize_tts_numbers(text: str) -> str:
    if not text:
        return ""

    def _credits_sub(match: re.Match[str]) -> str:
        raw_num = str(match.group("num") or "")
        n = _parse_grouped_int(raw_num)
        if n is None:
            return match.group(0)
        unit = _plural_form_pl(n, "kredyt", "kredyty", "kredytów")
        return _with_tts_number_semicolon_breaks(_int_to_words_pl(n), unit=unit)

    def _percent_sub(match: re.Match[str]) -> str:
        raw_num = str(match.group("num") or "")
        words = _decimal_to_words_pl(raw_num)
        if not words:
            return match.group(0)
        return _with_tts_number_semicolon_breaks(words, unit="procent")

    def _ly_sub(match: re.Match[str]) -> str:
        raw_num = str(match.group("num") or "")
        words = _decimal_to_words_pl(raw_num)
        if not words:
            return match.group(0)
        return _with_tts_number_semicolon_breaks(words, unit="lat świetlnych")

    def _standalone_sub(match: re.Match[str]) -> str:
        raw_num = str(match.group("num") or "")
        n = _parse_grouped_int(raw_num)
        if n is None:
            return match.group(0)
        return _with_tts_number_semicolon_breaks(_int_to_words_pl(n))

    out = text
    out = _CREDITS_NUMBER_RE.sub(_credits_sub, out)
    out = re.sub(r"(?P<num>\d+(?:[.,]\d+)?)\s*%", _percent_sub, out)
    out = re.sub(r"\b(?P<num>\d+(?:[.,]\d+)?)\s*(?:LY|ly)\b", _ly_sub, out)
    out = _STANDALONE_NUMBER_RE.sub(_standalone_sub, out)
    return out


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
    text = _verbalize_tts_numbers(text)
    # Keep commas - they improve Polish prosody (lists, clauses, number phrasing).
    # We normalize hard sentence terminators only.
    # Protect decimal dots so "100.5" is not split into "100. 5" by sentence normalization.
    text = re.sub(r"(?<=\d)\.(?=\d)", "__RENATA_DECIMAL_DOT__", text)
    text = text.replace("?", ".").replace("!", ".")
    text = re.sub(r"\s*;\s*", " ; ", text)
    text = re.sub(r"(?:\s;\s){2,}", " ; ", text)
    text = re.sub(r"\s*;\s*\.", ".", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\.\s*", ". ", text).strip()
    text = text.replace("__RENATA_DECIMAL_DOT__", ".")
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
                return _finalize_tts(fixed)

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

    # Generic fallback for message IDs that have a template but do not need
    # custom field normalization/branching in prepare_tts().
    fallback = _render_template(message_id)
    if fallback:
        return _finalize_tts(fallback)
    return None
