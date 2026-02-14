#!/usr/bin/env python3
"""
Installs repository git hooks by setting:
  git config core.hooksPath .githooks
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    proc = subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr.strip() or "Failed to set core.hooksPath", file=sys.stderr)
        return 1

    print("Git hooks installed: core.hooksPath=.githooks")
    print("Configured hooks:")
    print("- pre-commit: commit rules acknowledgement guard")
    print("- commit-msg: [PUB]/[PRO] prefix + [PUB] public guard")
    print("- pre-push: public guard")
    print("Before first commit each day, run:")
    print("  py tools/commit_rules_guard.py --ack")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
