"""
Manual TTS probe: make Renata read random real messages with script-only prosody hacks.

This script uses production `prepare_tts(...)` and production TTS backend selection
(`logic.utils.notify._speak_tts`) but applies optional "humanization/prosody hacks"
only in this probe script for listening experiments.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Callable


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config as app_config  # type: ignore
from logic.tts.text_preprocessor import prepare_tts  # type: ignore
from logic.utils import notify  # type: ignore


LETTER_NAMES_PL = {
    "A": "a",
    "B": "be",
    "C": "ce",
    "D": "de",
    "E": "e",
    "F": "ef",
    "G": "gie",
    "H": "ha",
    "I": "i",
    "J": "jota",
    "K": "ka",
    "L": "el",
    "M": "em",
    "N": "en",
    "O": "o",
    "P": "pe",
    "Q": "ku",
    "R": "er",
    "S": "es",
    "T": "te",
    "U": "u",
    "V": "fał",
    "W": "wu",
    "X": "iks",
    "Y": "igrek",
    "Z": "zet",
}
SPELL_TOKEN_SKIP = {"SOL"}
SYSTEM_TOKEN_RE = re.compile(r"\b[A-Z]{2,4}\b")


@dataclass
class Scenario:
    label: str
    message_id: str
    context: dict[str, object]
    tone: str  # warning | confirm | neutral
    spell_tokens: list[str]


@dataclass
class HackProfile:
    emotion: bool
    vowel_stretch: bool
    breaths: bool
    system_spelling: bool
    fillers: bool
    long_sentence_semis: bool


def _group_number(n: int, style: str = "comma") -> str:
    raw = str(int(n))
    parts: list[str] = []
    while raw:
        parts.insert(0, raw[-3:])
        raw = raw[:-3]
    sep = "," if style == "comma" else (" " if style == "space" else "\u00A0")
    return sep.join(parts)


def _random_credit_value(rng: random.Random) -> int:
    digits = rng.randint(6, 9)
    return rng.randint(10 ** (digits - 1), (10 ** digits) - 1)


def _random_system_name(rng: random.Random) -> str:
    names = [
        "SOL",
        "LHS 20",
        "HIP 36601",
        "XJ-5",
        "COL 285 SECTOR AB-C d12-34",
        "WREGOE XX-D C28-15",
        "HD 189733",
        "NGC 7822 SECTOR GW-W d1-45",
        "PRAEA EUQ AA-A h54",
        "Pleiades Sector HR-W d1-41",
    ]
    return rng.choice(names)


def _random_station_name(rng: random.Random) -> str:
    return rng.choice(
        [
            "Jameson Memorial",
            "Ray Gateway",
            "Obsidian Orbital",
            "Sagan Station",
            "Porta 7",
            "XJ Transfer Hub 12",
        ]
    )


def _random_body_name(rng: random.Random) -> str:
    base = rng.choice(["A 2", "B 3", "C 1 A", "3", "4 a", "AB 7"])
    return f"{_random_system_name(rng)} {base}"


def _random_version(rng: random.Random) -> str:
    return f"{rng.randint(0, 2)}.{rng.randint(0, 9)}.{rng.randint(0, 99)}"


def _extract_spell_tokens(value: str) -> list[str]:
    if not value:
        return []
    seen: list[str] = []
    for token in SYSTEM_TOKEN_RE.findall(str(value)):
        if token in SPELL_TOKEN_SKIP:
            continue
        if token not in seen:
            seen.append(token)
    return seen


def _scenario_next_hop(rng: random.Random) -> Scenario:
    system = _random_system_name(rng)
    return Scenario("next_hop", "MSG.NEXT_HOP", {"system": system}, "neutral", _extract_spell_tokens(system))


def _scenario_jumped_system(rng: random.Random) -> Scenario:
    system = _random_system_name(rng)
    return Scenario("jumped_system", "MSG.JUMPED_SYSTEM", {"system": system}, "neutral", _extract_spell_tokens(system))


def _scenario_next_hop_copied(rng: random.Random) -> Scenario:
    system = _random_system_name(rng)
    return Scenario(
        "next_hop_copied",
        "MSG.NEXT_HOP_COPIED",
        {"system": system},
        "confirm",
        _extract_spell_tokens(system),
    )


def _scenario_ppm_set_target(rng: random.Random) -> Scenario:
    target = _random_system_name(rng)
    return Scenario("ppm_set_target", "MSG.PPM_SET_TARGET", {"target": target}, "confirm", _extract_spell_tokens(target))


def _scenario_ppm_copy_system(rng: random.Random) -> Scenario:
    system = _random_system_name(rng)
    return Scenario("ppm_copy_system", "MSG.PPM_COPY_SYSTEM", {"system": system}, "confirm", _extract_spell_tokens(system))


def _scenario_docked(rng: random.Random) -> Scenario:
    station = _random_station_name(rng)
    return Scenario("docked", "MSG.DOCKED", {"station": station}, "confirm", [])


def _scenario_undocked(rng: random.Random) -> Scenario:
    return Scenario("undocked", "MSG.UNDOCKED", {}, "confirm", [])


def _scenario_route_complete(rng: random.Random) -> Scenario:
    _ = rng
    return Scenario("route_complete", "MSG.ROUTE_COMPLETE", {}, "confirm", [])


def _scenario_route_desync(rng: random.Random) -> Scenario:
    _ = rng
    return Scenario("route_desync", "MSG.ROUTE_DESYNC", {}, "warning", [])


def _scenario_fuel_critical(rng: random.Random) -> Scenario:
    _ = rng
    return Scenario("fuel_critical", "MSG.FUEL_CRITICAL", {}, "warning", [])


def _scenario_cash_in(rng: random.Random) -> Scenario:
    credits = _group_number(_random_credit_value(rng), "comma")
    raw_text = f"Podsumowanie gotowe. Dane warte {credits} Cr. Rozwaz ladowanie pod exobio."
    return Scenario("cash_in", "MSG.CASH_IN_ASSISTANT", {"raw_text": raw_text}, "neutral", [])


def _scenario_exploration_nic(rng: random.Random) -> Scenario:
    system = _random_system_name(rng)
    credits = _group_number(_random_credit_value(rng), "comma")
    raw_text = (
        f"Tutaj nie ma nic wartego mapowania. System {system}. "
        f"Szacowana wartosc danych {credits} Cr."
    )
    return Scenario(
        "exploration_nic",
        "MSG.EXPLORATION_SYSTEM_SUMMARY",
        {"raw_text": raw_text},
        "neutral",
        _extract_spell_tokens(system),
    )


def _scenario_runtime_critical(rng: random.Random) -> Scenario:
    percent = rng.choice([12, 18, 25, 33, 47, 62, 75, 88])
    distance = rng.choice(["9.4", "12.7", "33.9", "55.2"])
    raw_text = (
        f"Blad krytyczny runtime. Do kolejnego odcinka {percent}% drogi. "
        f"Odleglosc do celu {distance} LY."
    )
    return Scenario("runtime_critical", "MSG.RUNTIME_CRITICAL", {"raw_text": raw_text}, "warning", [])


def _scenario_high_g_warning(rng: random.Random) -> Scenario:
    g_val = rng.choice(["3.2", "5.1", "8.4", "11.7"])
    raw_text = f"Uwaga. Wykryto wysokie przeciazenie grawitacyjne. Odczyt {g_val} g."
    return Scenario("high_g_warning", "MSG.HIGH_G_WARNING", {"raw_text": raw_text}, "warning", [])


def _scenario_trade_data_stale(rng: random.Random) -> Scenario:
    minutes = rng.choice([37, 58, 92, 140])
    raw_text = f"Dane rynkowe sa nieswieze. Ostatnia aktualizacja {minutes} minut temu."
    return Scenario("trade_data_stale", "MSG.TRADE_DATA_STALE", {"raw_text": raw_text}, "warning", [])


def _scenario_milestone_progress(rng: random.Random) -> Scenario:
    target = _random_system_name(rng)
    percent = rng.choice([12, 25, 38, 50, 67, 75, 91])
    return Scenario(
        "milestone_progress",
        "MSG.MILESTONE_PROGRESS",
        {"percent": percent, "target": target},
        "neutral",
        _extract_spell_tokens(target),
    )


def _scenario_milestone_reached(rng: random.Random) -> Scenario:
    target = _random_system_name(rng)
    next_target = _random_system_name(rng)
    return Scenario(
        "milestone_reached",
        "MSG.MILESTONE_REACHED",
        {"target": target, "next_target": next_target},
        "confirm",
        _extract_spell_tokens(target) + [t for t in _extract_spell_tokens(next_target) if t not in _extract_spell_tokens(target)],
    )


def _scenario_startup(rng: random.Random) -> Scenario:
    return Scenario("startup", "MSG.STARTUP_SYSTEMS", {"version": _random_version(rng)}, "neutral", [])


def _scenario_body_no_prev_discovery(rng: random.Random) -> Scenario:
    body = _random_body_name(rng)
    return Scenario(
        "body_no_prev_discovery",
        "MSG.BODY_NO_PREV_DISCOVERY",
        {"body": body},
        "confirm",
        _extract_spell_tokens(body),
    )


SCENARIO_BUILDERS: tuple[Callable[[random.Random], Scenario], ...] = (
    _scenario_next_hop,
    _scenario_jumped_system,
    _scenario_next_hop_copied,
    _scenario_ppm_set_target,
    _scenario_ppm_copy_system,
    _scenario_docked,
    _scenario_undocked,
    _scenario_route_complete,
    _scenario_route_desync,
    _scenario_fuel_critical,
    _scenario_cash_in,
    _scenario_exploration_nic,
    _scenario_runtime_critical,
    _scenario_high_g_warning,
    _scenario_trade_data_stale,
    _scenario_milestone_progress,
    _scenario_milestone_reached,
    _scenario_startup,
    _scenario_body_no_prev_discovery,
)


def _profile_from_name(name: str) -> HackProfile:
    if str(name).lower() == "safe":
        return HackProfile(
            emotion=True,
            vowel_stretch=False,
            breaths=True,
            system_spelling=True,
            fillers=True,
            long_sentence_semis=True,
        )
    return HackProfile(
        emotion=True,
        vowel_stretch=True,
        breaths=True,
        system_spelling=True,
        fillers=True,
        long_sentence_semis=True,
    )


def _spell_token_pl(token: str) -> str:
    parts = [LETTER_NAMES_PL.get(ch, ch.lower()) for ch in str(token)]
    return " ".join(part for part in parts if part).strip()


def _apply_system_spelling_hints(text: str, spell_tokens: list[str]) -> str:
    out = str(text or "")
    if not out or not spell_tokens:
        return out
    for token in sorted(set(spell_tokens), key=len, reverse=True):
        spelled = _spell_token_pl(token)
        if not spelled:
            continue
        out = re.sub(rf"\b{re.escape(token)}\b", spelled, out)
    return out


def _apply_fillers(text: str, scenario: Scenario, rng: random.Random) -> str:
    out = str(text or "").strip()
    if not out:
        return ""
    if scenario.tone == "warning":
        if rng.random() < 0.35 and not out.lower().startswith("uwaga"):
            out = "Uwaga, " + out[0].lower() + out[1:]
        return out
    if scenario.tone == "confirm":
        fillers = [
            "Jasne, ",
            "Potwierdzam, ",
            "Dobra, ",
            "Renata tutaj. ",
        ]
        if rng.random() < 0.65:
            out = rng.choice(fillers) + out
        return out
    fillers = [
        "Renata tutaj. ",
        "Okej, ",
        "Dobra, ",
        "Jasne, ",
    ]
    if rng.random() < 0.45:
        out = rng.choice(fillers) + out
    return out


def _apply_vowel_stretch(text: str, scenario: Scenario) -> str:
    out = str(text or "")
    if not out:
        return out
    if scenario.tone == "warning":
        out = re.sub(r"\bBłąd\b", "Błóąąd", out)
        out = re.sub(r"\bbłąd\b", "błóąąd", out)
        out = re.sub(r"\bUwaga\b", "Uwaaaga", out)
        out = re.sub(r"\buwaga\b", "uwaaaga", out)
    if re.search(r"\bnic\b", out, flags=re.IGNORECASE):
        out = re.sub(r"\bNic\b", "Niic", out)
        out = re.sub(r"\bnic\b", "niic", out)
    return out


def _apply_breaths(text: str, profile: HackProfile) -> str:
    out = str(text or "").strip()
    if not out:
        return ""
    out = out.replace("Renata.", "Renata;")
    targeted = {
        "Następny skok.": "Następny skok...",
        "Aktualnie w ": "Aktualnie w... ",
        "Cel skopiowany.": "Cel skopiowany...",
        "Skopiowano system.": "Skopiowano system...",
        "Ustawiono cel.": "Ustawiono cel...",
        "Do boosta.": "Do boosta...",
        "Cel odcinka osiągnięty.": "Cel odcinka osiągnięty...",
    }
    for src, dst in targeted.items():
        out = out.replace(src, dst)
    out = re.sub(r"\bsystem\s+([A-ZŁŚŻŹĆĄĘÓŃ][\w-]+)\b", r"system, \1", out)
    if profile.long_sentence_semis and len(out) > 70:
        # Only replace single sentence dots, keep ellipsis ("...") intact.
        out = re.sub(r"(?<!\.)\.\s+", " ; ", out)
    out = re.sub(r"\s*;\s*", " ; ", out)
    out = re.sub(r"(?:\s;\s){2,}", " ; ", out)
    return out


def _apply_emotional_punctuation(text: str, scenario: Scenario) -> str:
    out = str(text or "").strip()
    if not out:
        return ""
    out = re.sub(r"[.!?]+\s*$", "", out).rstrip(" ;,")
    if scenario.tone == "warning":
        suffix = "!"
    elif scenario.tone == "confirm":
        suffix = "!"
    else:
        suffix = "."
    return out + suffix


def _normalize_hacked_text(text: str) -> str:
    out = str(text or "").strip()
    if not out:
        return ""
    out = re.sub(r"\s*\.\.\.\s*", "... ", out)
    out = re.sub(r"\s*;\s*", " ; ", out)
    out = re.sub(r"\s*,\s*", ", ", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = out.replace(".. ;", "... ;")
    out = out.replace("....", "...")
    out = re.sub(r"(?:\s;\s){2,}", " ; ", out)
    out = re.sub(r"\s+([!?.,])", r"\1", out)
    if not out.endswith((".", "!", "?")):
        out += "."
    return out


def _apply_script_hacks(text: str, scenario: Scenario, profile: HackProfile, rng: random.Random) -> str:
    out = str(text or "").strip()
    if not out:
        return ""
    if profile.system_spelling:
        out = _apply_system_spelling_hints(out, scenario.spell_tokens)
    if profile.fillers:
        out = _apply_fillers(out, scenario, rng)
    if profile.breaths:
        out = _apply_breaths(out, profile)
    if profile.vowel_stretch:
        out = _apply_vowel_stretch(out, scenario)
    if profile.emotion:
        out = _apply_emotional_punctuation(out, scenario)
    return _normalize_hacked_text(out)


def _apply_runtime_piper_overrides(length_scale: float, sentence_silence: float) -> tuple[float, float] | None:
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


def _speak_text(text: str) -> None:
    if text:
        notify._speak_tts(text)


def _pick_scenario(rng: random.Random) -> Scenario:
    builder = rng.choice(SCENARIO_BUILDERS)
    return builder(rng)


def main() -> int:
    parser = argparse.ArgumentParser(description="Renata TTS random messages probe with script-only prosody hacks.")
    parser.add_argument("--count", type=int, default=10, help="How many random messages to generate/read.")
    parser.add_argument("--pause", type=float, default=0.25, help="Pause between utterances (seconds).")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for reproducible runs.")
    parser.add_argument(
        "--speech-mode",
        choices=["base", "hacked", "compare"],
        default="hacked",
        help="Speak the base text, hacked text, or both (compare).",
    )
    parser.add_argument(
        "--profile",
        choices=["safe", "full"],
        default="full",
        help="Prosody hack profile. 'full' includes vowel stretching; 'safe' disables it.",
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
    parser.add_argument("--no-speak", action="store_true", help="Only print generated messages, do not play audio.")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    profile = _profile_from_name(args.profile)
    prev_piper = _apply_runtime_piper_overrides(
        float(args.piper_length_scale),
        float(args.piper_sentence_silence),
    )

    print("=== RENATA TTS RANDOM MESSAGES PROBE ===")
    print(
        "count="
        f"{args.count} speech_mode={args.speech_mode} profile={args.profile} "
        f"seed={args.seed!r} speak={not args.no_speak}"
    )
    print(
        "piper_runtime_override="
        f"(length_scale={app_config.get('tts.piper_length_scale')}, "
        f"sentence_silence={app_config.get('tts.piper_sentence_silence')})"
    )
    print(
        "hacks="
        f"emotion={profile.emotion} vowel_stretch={profile.vowel_stretch} "
        f"breaths={profile.breaths} system_spelling={profile.system_spelling} "
        f"fillers={profile.fillers} long_sentence_semis={profile.long_sentence_semis}"
    )

    try:
        generated = 0
        attempts = 0
        max_attempts = max(20, int(args.count) * 5)
        while generated < max(1, int(args.count)) and attempts < max_attempts:
            attempts += 1
            scenario = _pick_scenario(rng)
            base_tts = prepare_tts(scenario.message_id, dict(scenario.context)) or ""
            if not base_tts:
                print(
                    f"[WARN] empty prepare_tts for {scenario.message_id} label={scenario.label} "
                    f"context={scenario.context!r}"
                )
                continue
            hacked_tts = _apply_script_hacks(base_tts, scenario, profile, rng)
            generated += 1

            print(f"\n[{generated:02d}] {scenario.label} tone={scenario.tone} message_id={scenario.message_id}")
            print(f"context: {scenario.context!r}")
            if scenario.spell_tokens:
                print(f"spell_tokens: {scenario.spell_tokens!r}")
            print(f"tts_base: {base_tts!r}")
            print(f"tts_hacked: {hacked_tts!r}")

            if args.no_speak:
                continue

            try:
                if args.speech_mode == "base":
                    _speak_text(base_tts)
                elif args.speech_mode == "hacked":
                    _speak_text(hacked_tts)
                else:
                    print("[speak] compare: base")
                    _speak_text(base_tts)
                    if args.pause > 0:
                        time.sleep(args.pause)
                    print("[speak] compare: hacked")
                    _speak_text(hacked_tts)
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
