#!/usr/bin/env python3
"""
Commit message guard for RenataAI.

Rules:
- First line must start with exactly one prefix: [PUB] or [PRO].
- For [PUB], run public_repo_guard.py against staged/tracked files.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def _first_line(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if stripped:
            return stripped
    return ""


def _run_public_guard() -> int:
    proc = subprocess.run(["py", "tools/public_repo_guard.py"], check=False)
    return proc.returncode


def main() -> int:
    if len(sys.argv) < 2:
        print("FAIL: commit-msg hook missing message file argument.")
        return 1

    msg_file = Path(sys.argv[1])
    first = _first_line(msg_file)
    if not first:
        print("FAIL: empty commit message.")
        return 1

    has_pub = first.startswith("[PUB]")
    has_pro = first.startswith("[PRO]")

    if has_pub == has_pro:
        print("FAIL: commit message must start with exactly one prefix: [PUB] or [PRO].")
        print("First non-empty line does not start with required prefix.")
        return 1

    if has_pub:
        rc = _run_public_guard()
        if rc != 0:
            print("FAIL: [PUB] commit blocked by public_repo_guard.")
            return rc

    print("COMMIT_MSG_GUARD=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
