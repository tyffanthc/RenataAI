"""
Dev tool: quick TTS playback without launching the game.

Goal:
- Use the same production path: notify.powiedz() -> text_preprocessor -> TTS engine (Piper/pyttsx3)
- Read a curated set of message_id one by one with pauses
"""

from __future__ import annotations

import os
import sys
import time
import argparse
from types import SimpleNamespace

# Ensure repo root is on sys.path when running from tools/
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Production entrypoint
from logic.utils import notify  # type: ignore
from logic.utils.notify import powiedz  # type: ignore


# Message IDs (fallback if no enum exists)
MSG = SimpleNamespace(
    NEXT_HOP="MSG.NEXT_HOP",
    NEXT_HOP_COPIED="MSG.NEXT_HOP_COPIED",
    ROUTE_FOUND="MSG.ROUTE_FOUND",
    ROUTE_COMPLETE="MSG.ROUTE_COMPLETE",
    ROUTE_DESYNC="MSG.ROUTE_DESYNC",
    FUEL_CRITICAL="MSG.FUEL_CRITICAL",
    DOCKED="MSG.DOCKED",
    UNDOCKED="MSG.UNDOCKED",
    FIRST_DISCOVERY="MSG.FIRST_DISCOVERY",
    SYSTEM_FULLY_SCANNED="MSG.SYSTEM_FULLY_SCANNED",
    ELW_DETECTED="MSG.ELW_DETECTED",
    FOOTFALL="MSG.FOOTFALL",
)


def _ctx(**kwargs):
    """
    Some projects use a dataclass for context, others pass dict.
    We keep it flexible: dict is OK.
    """
    return kwargs


def say(message_id: str, pause: float = 1.2, *, force: bool = False, **context) -> None:
    """
    Speak a single message_id using production notify.powiedz().
    """
    ctx = _ctx(**context)
    # powiedz requires a text for logging; we keep it minimal.
    powiedz(
        f"TTS_PREVIEW {message_id}",
        message_id=message_id,
        context=ctx,
        force=force,
    )
    time.sleep(pause)


def main() -> None:
    parser = argparse.ArgumentParser(description="Renata TTS preview tool.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore cooldowns and silence rules for preview.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=1.2,
        help="Pause between lines (seconds).",
    )
    args = parser.parse_args()

    print("=== TTS PREVIEW (Renata) ===")
    if args.force:
        print("Mode: FORCE (cooldowns/silence ignored).")
    else:
        print("Mode: normal (cooldowns/silence respected). Use --force to bypass.")
    print("Tip: run multiple times while tuning rate/pauses.\n")

    # --- Core route / nav ---
    say(MSG.ROUTE_FOUND, pause=args.pause, force=args.force)
    say(MSG.NEXT_HOP, system="PSR J1752-2806", pause=args.pause, force=args.force)
    say(MSG.NEXT_HOP_COPIED, pause=args.pause, force=args.force)
    say(MSG.DOCKED, station="Jameson Memorial", pause=args.pause, force=args.force)
    say(MSG.UNDOCKED, pause=args.pause, force=args.force)

    # --- Exploration highlights ---
    time.sleep(0.8)
    say(MSG.ELW_DETECTED, pause=args.pause, force=args.force)
    say(MSG.SYSTEM_FULLY_SCANNED, pause=args.pause, force=args.force)
    say(MSG.FIRST_DISCOVERY, pause=args.pause, force=args.force)
    say(MSG.FOOTFALL, pause=args.pause, force=args.force)

    # --- Alerts ---
    time.sleep(0.8)
    say(MSG.FUEL_CRITICAL, pause=args.pause, force=args.force)

    # --- UTF-8 check ---
    time.sleep(0.8)
    notify._speak_tts("Zażółć gęślą jaźń.")
    time.sleep(args.pause)

    # --- End ---
    say(MSG.ROUTE_COMPLETE, pause=args.pause, force=args.force)

    print("\n=== END ===")


if __name__ == "__main__":
    main()
