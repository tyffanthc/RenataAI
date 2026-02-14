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
    print("pre-push now runs tools/public_repo_guard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

