"""
Manual TTS probe: force Renata to read random 6-9 digit numbers.

Uses production text preprocessing (`prepare_tts`) and production TTS backend
selection (`logic.utils.notify._speak_tts`) so it is useful for listening tests.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config as app_config  # type: ignore
from logic.tts.text_preprocessor import prepare_tts  # type: ignore
from logic.utils import notify  # type: ignore


MSG_ID = "MSG.CASH_IN_ASSISTANT"
_GROUP_WORDS = (
    "tysiąc",
    "tysiące",
    "tysięcy",
    "milion",
    "miliony",
    "milionów",
    "miliard",
    "miliardy",
    "miliardów",
    "bilion",
    "biliony",
    "bilionów",
)
_GROUP_WORDS_RE = re.compile(
    r"\b(?P<w>"
    + "|".join(re.escape(w) for w in _GROUP_WORDS)
    + r")\b(?=\s+(?!kredyt)\w)"
)
_PROBE_UNITS_0_19 = {
    0: "zero",
    1: "jeden",
    2: "dwa",
    3: "tszy",
    4: "cztery",
    5: "pięć",
    6: "sześć",
    7: "siedem",
    8: "osiem",
    9: "dziewięć",
    10: "dziesięć",
    11: "jedenaście",
    12: "dwanaście",
    13: "tszynasicie",
    14: "czternasicie",
    15: "piętnasicie",
    16: "szesnasicie",
    17: "siedemnasicie",
    18: "osiemnasicie",
    19: "dziewiętnasicie",
}
_PROBE_TENS = {
    2: "dwadzieścia",
    3: "tszydzieści",
    4: "czterdzieści",
    5: "pięć dziesiąt",
    6: "sześć dziesiąt",
    7: "siedem dziesiąt",
    8: "osiem dziesiąt",
    9: "dziewięć dziesiąt",
}
_PROBE_HUNDREDS = {
    1: "sto",
    2: "dwieście",
    3: "tszy sta",
    4: "cztery sta",
    5: "pięć set",
    6: "sześć set",
    7: "siedem set",
    8: "osiem set",
    9: "dziewięć set",
}
_PROBE_GROUPS = [
    ("", "", ""),
    ("tysiąc", "tysiące", "tysięcy"),
    ("milion", "miliony", "milionów"),
    ("miliard", "miliardy", "miliardów"),
]
_PROBE_PHONETIC_REPLACEMENTS = (
    ("pięćset", "pięć set"),
    ("sześćset", "sześć set"),
    ("siedemset", "siedem set"),
    ("osiemset", "osiem set"),
    ("dziewięćset", "dziewięć set"),
    ("trzysta", "tszy sta"),
    ("dwadzieścia", "dwa dzieścia"),
    ("trzydzieści", "tszy dzieści"),
    ("czterdzieści", "czter dzieści"),
    ("trzynaście", "tszynaśćie"),
    ("czternaście", "czternaśćie"),
    ("piętnaście", "piętnaśćie"),
    ("szesnaście", "szesnaśćie"),
    ("siedemnaście", "siedemnaśćie"),
    ("osiemnaście", "osiemnaśćie"),
    ("dziewiętnaście", "dziewiętnaśćie"),
    ("procent", "pro cent"),
)


def _group_number(n: int, style: str) -> str:
    raw = str(int(n))
    parts: list[str] = []
    while raw:
        parts.insert(0, raw[-3:])
        raw = raw[:-3]
    if style == "comma":
        return ",".join(parts)
    if style == "nbsp":
        return "\u00A0".join(parts)
    return " ".join(parts)


def _pick_group_style(mode: str, rng: random.Random) -> str:
    if mode in {"space", "comma", "nbsp"}:
        return mode
    return rng.choice(["space", "comma", "nbsp"])


def _random_number_6_9_digits(rng: random.Random) -> tuple[int, int]:
    digits = rng.randint(6, 9)
    low = 10 ** (digits - 1)
    high = (10 ** digits) - 1
    return rng.randint(low, high), digits


def _build_raw_text(formatted_number: str) -> str:
    return f"Dane warte {formatted_number} Cr."


def _probe_plural_form_pl(value: int, one: str, few: str, many: str) -> str:
    n = abs(int(value))
    if n == 1:
        return one
    if 10 <= (n % 100) <= 19:
        return many
    if 2 <= (n % 10) <= 4:
        return few
    return many


def _probe_int_to_words_pl_under_1000(value: int) -> str:
    n = abs(int(value))
    parts: list[str] = []
    h = n // 100
    if h:
        parts.append(_PROBE_HUNDREDS.get(h, ""))
    rem = n % 100
    if rem in _PROBE_UNITS_0_19:
        if rem:
            parts.append(_PROBE_UNITS_0_19[rem])
    else:
        t = rem // 10
        u = rem % 10
        if t:
            parts.append(_PROBE_TENS.get(t, ""))
        if u:
            parts.append(_PROBE_UNITS_0_19[u])
    return " ".join(x for x in parts if x).strip()


def _probe_int_to_words_pl(value: int) -> str:
    n = int(value)
    if n == 0:
        return _PROBE_UNITS_0_19[0]
    sign = "minus " if n < 0 else ""
    n_abs = abs(n)
    group_idx = 0
    parts_rev: list[str] = []
    while n_abs > 0:
        group_val = n_abs % 1000
        n_abs //= 1000
        if group_val:
            words = _probe_int_to_words_pl_under_1000(group_val)
            if group_idx == 0:
                chunk = words
            else:
                if group_idx < len(_PROBE_GROUPS):
                    one, few, many = _PROBE_GROUPS[group_idx]
                else:
                    one = few = many = f"10^{group_idx * 3}"
                if group_idx == 1 and group_val == 1:
                    chunk = one
                else:
                    chunk = f"{words} {_probe_plural_form_pl(group_val, one, few, many)}".strip()
            parts_rev.append(chunk.strip())
        group_idx += 1
    return sign + " ".join(reversed([x for x in parts_rev if x])).strip()


def _build_probe_credit_text(value: int) -> str:
    n = max(0, int(round(float(value or 0))))
    words = _probe_int_to_words_pl(n)
    unit = _probe_plural_form_pl(n, "kredyt", "kredyty", "kredytów")
    return f"Dane warte {words} {unit}."


def _inject_probe_phonetics(text: str) -> str:
    """
    Script-only phonetic hacks for Piper listening experiments.
    Production TTS pipeline stays untouched.
    """
    out = str(text or "").strip()
    if not out:
        return ""
    for src, dst in _PROBE_PHONETIC_REPLACEMENTS:
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)
    # "Reset" phrasing before the credit unit can help Piper re-articulate the tail.
    out = re.sub(r"\s+(kredyt(?:y|ów)?)\b", r" ... \1", out, flags=re.IGNORECASE)
    out = re.sub(r"^Dane warte\b", "Dane warte ...", out)
    out = re.sub(r"\.{4,}", "...", out)
    out = re.sub(r"\s+", " ", out).strip()
    if out and not out.endswith("."):
        out += "."
    return out


def _inject_group_pauses_in_verbalized_credits(text: str) -> str:
    """
    Script-only tweak: add commas after Polish large-number group words
    (milion/tysiąc/...) when a lower group follows.

    This creates audible pauses in TTS without changing production code.
    """
    if not text:
        return ""
    return _GROUP_WORDS_RE.sub(lambda m: f"{m.group('w')},", text)


def _inject_semicolon_breaks(text: str) -> str:
    """
    Script-only prosody hack: use semicolons as micro-pause/reset markers.
    This approximates the user's idea without touching production _finalize_tts.
    """
    out = str(text or "").strip()
    if not out:
        return ""
    out = re.sub(r"^Dane warte\b", "Dane warte ;", out)
    out = _GROUP_WORDS_RE.sub(lambda m: f"{m.group('w')} ;", out)
    out = re.sub(r"\s+(kredyt(?:y|ów)?)\b", r" ; \1", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*;\s*", " ; ", out)
    out = re.sub(r"\s+", " ", out).strip()
    if out and not out.endswith("."):
        out += "."
    return out


def _chunk_segments_from_comma_variant(text: str) -> list[str]:
    if not text:
        return []
    core = text.strip()
    trailing_dot = core.endswith(".")
    if trailing_dot:
        core = core[:-1]
    parts = [p.strip() for p in core.split(",") if p.strip()]
    if not parts:
        return [text.strip()]
    # Speak chunks as separate utterances to force pauses without punctuation-induced clipping.
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx == len(parts) - 1 and trailing_dot:
            out.append(part + ".")
        else:
            out.append(part + ".")
    return out


def _speak_text(text: str) -> None:
    if not text:
        return
    notify._speak_tts(text)


def _speak_chunks(chunks: list[str], intra_pause: float) -> None:
    for idx, chunk in enumerate(chunks):
        _speak_text(chunk)
        if idx < len(chunks) - 1 and intra_pause > 0:
            time.sleep(intra_pause)


def _apply_runtime_piper_overrides(length_scale: float, sentence_silence: float) -> tuple[float, float] | None:
    """
    Script-only in-memory override. Does not save user settings to disk.
    """
    try:
        mgr = getattr(app_config, "config", None)
        settings = getattr(mgr, "_settings", None)
        if not isinstance(settings, dict):
            return None
        prev = (
            float(app_config.get("tts.piper_length_scale", 1.0)),
            float(app_config.get("tts.piper_sentence_silence", 0.2)),
        )
        settings["tts.piper_length_scale"] = float(length_scale)
        settings["tts.piper_sentence_silence"] = float(sentence_silence)
        return prev
    except Exception:
        return None


def _restore_runtime_piper_overrides(prev: tuple[float, float] | None) -> None:
    if prev is None:
        return
    try:
        mgr = getattr(app_config, "config", None)
        settings = getattr(mgr, "_settings", None)
        if not isinstance(settings, dict):
            return
        settings["tts.piper_length_scale"] = float(prev[0])
        settings["tts.piper_sentence_silence"] = float(prev[1])
    except Exception:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Renata TTS random-number probe (6-9 digits).")
    parser.add_argument("--count", type=int, default=10, help="How many numbers to read.")
    parser.add_argument("--pause", type=float, default=0.2, help="Pause between utterances (seconds).")
    parser.add_argument(
        "--separator",
        choices=["mixed", "space", "comma", "nbsp"],
        default="comma",
        help="Thousands separator style for raw input numbers.",
    )
    parser.add_argument(
        "--speech-mode",
        choices=["plain", "semi", "comma", "chunk", "compare"],
        default="plain",
        help=(
            "How to speak generated text: base, semicolon pauses, comma pauses, chunk pauses, "
            "or compare comma vs chunk."
        ),
    )
    parser.add_argument(
        "--chunk-pause",
        type=float,
        default=0.18,
        help="Pause between chunk utterances in chunk/compare modes (seconds).",
    )
    parser.add_argument(
        "--piper-length-scale",
        type=float,
        default=0.80,
        help="Script-only runtime override for tts.piper_length_scale (not persisted).",
    )
    parser.add_argument(
        "--piper-sentence-silence",
        type=float,
        default=0.5,
        help="Script-only runtime override for tts.piper_sentence_silence (not persisted).",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for reproducible runs.")
    parser.add_argument("--no-speak", action="store_true", help="Only print generated TTS text, do not play audio.")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    prev_piper = _apply_runtime_piper_overrides(
        float(args.piper_length_scale),
        float(args.piper_sentence_silence),
    )

    print("=== RENATA TTS RANDOM NUMBERS PROBE ===")
    print(
        "count="
        f"{args.count} separator={args.separator} speech_mode={args.speech_mode} "
        f"seed={args.seed!r} speak={not args.no_speak}"
    )
    print(
        "piper_runtime_override="
        f"(length_scale={app_config.get('tts.piper_length_scale')}, "
        f"sentence_silence={app_config.get('tts.piper_sentence_silence')})"
    )

    try:
        for idx in range(1, max(1, int(args.count)) + 1):
            value, digits = _random_number_6_9_digits(rng)
            style = _pick_group_style(args.separator, rng)
            formatted = _group_number(value, style)
            raw_exact_text = _build_raw_text(formatted)
            base_tts_text = prepare_tts(MSG_ID, {"raw_text": raw_exact_text}) or ""
            # Keep standard Polish verbalization; semicolons carry the prosody hack.
            phonetic_tts_text = base_tts_text
            semicolon_tts_text = _inject_semicolon_breaks(phonetic_tts_text)
            comma_tts_text = _inject_group_pauses_in_verbalized_credits(phonetic_tts_text)
            chunk_segments = _chunk_segments_from_comma_variant(comma_tts_text)

            print(f"\n[{idx:02d}] digits={digits} style={style}")
            print(f"raw_exact: {raw_exact_text!r}")
            print(f"tts_base: {base_tts_text!r}")
            print(f"tts_probe_phonetic: {phonetic_tts_text!r}")
            print(f"tts_semicolon: {semicolon_tts_text!r}")
            print(f"tts_comma: {comma_tts_text!r}")
            print(f"tts_chunk_segments: {chunk_segments!r}")

            if not args.no_speak:
                try:
                    if args.speech_mode == "plain":
                        _speak_text(phonetic_tts_text)
                    elif args.speech_mode == "semi":
                        _speak_text(semicolon_tts_text)
                    elif args.speech_mode == "comma":
                        _speak_text(comma_tts_text)
                    elif args.speech_mode == "chunk":
                        _speak_chunks(chunk_segments, float(args.chunk_pause))
                    else:
                        print("[speak] compare: comma")
                        _speak_text(comma_tts_text)
                        if args.pause > 0:
                            time.sleep(args.pause)
                        print("[speak] compare: chunk")
                        _speak_chunks(chunk_segments, float(args.chunk_pause))
                except Exception as exc:
                    print(f"[WARN] speak failed: {type(exc).__name__}: {exc}")
                    return 1
                if args.pause > 0:
                    time.sleep(args.pause)
    finally:
        _restore_runtime_piper_overrides(prev_piper)

    print("\n=== END ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
