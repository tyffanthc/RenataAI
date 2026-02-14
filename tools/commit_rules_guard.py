#!/usr/bin/env python3
"""
Commit rules acknowledgement guard.

Usage:
  py tools/commit_rules_guard.py --ack
  py tools/commit_rules_guard.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys


RULES_PATH = Path("docs/internal/COMMIT_RULES.md")
ACK_PATH = Path(".git/.commit_rules_ack.json")


def _rules_hash(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _today_iso() -> str:
    return dt.date.today().isoformat()


def ack() -> int:
    if not RULES_PATH.exists():
        print(f"FAIL: missing rules file: {RULES_PATH.as_posix()}")
        return 1

    payload = {
        "date": _today_iso(),
        "rules_hash": _rules_hash(RULES_PATH),
        "rules_path": RULES_PATH.as_posix(),
    }
    ACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACK_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    print("COMMIT_RULES_ACK=OK")
    return 0


def guard() -> int:
    if not RULES_PATH.exists():
        print(f"FAIL: missing rules file: {RULES_PATH.as_posix()}")
        print("Create/read rules first.")
        return 1

    if not ACK_PATH.exists():
        print("FAIL: commit rules not acknowledged.")
        print("Read docs/internal/COMMIT_RULES.md and run:")
        print("  py tools/commit_rules_guard.py --ack")
        return 1

    try:
        payload = json.loads(ACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        print("FAIL: invalid ack file, renew acknowledgement:")
        print("  py tools/commit_rules_guard.py --ack")
        return 1

    expected_hash = _rules_hash(RULES_PATH)
    if payload.get("rules_hash") != expected_hash:
        print("FAIL: COMMIT_RULES changed since last acknowledgement.")
        print("Read docs/internal/COMMIT_RULES.md and run:")
        print("  py tools/commit_rules_guard.py --ack")
        return 1

    if payload.get("date") != _today_iso():
        print("FAIL: commit rules acknowledgement expired (daily).")
        print("Read docs/internal/COMMIT_RULES.md and run:")
        print("  py tools/commit_rules_guard.py --ack")
        return 1

    print("COMMIT_RULES_GUARD=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit rules acknowledgement guard.")
    parser.add_argument("--ack", action="store_true", help="Acknowledge commit rules for today.")
    args = parser.parse_args()
    return ack() if args.ack else guard()


if __name__ == "__main__":
    sys.exit(main())

