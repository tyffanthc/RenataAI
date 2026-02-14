#!/usr/bin/env python3
"""
Public repo guard for FREE-only releases.

Checks:
1) Git tracked files do not contain forbidden private/PRO-only paths.
2) Staged additions do not include forbidden private/PRO-only paths.
3) Optional ZIP sanity for release artifacts.

Usage:
  py tools/public_repo_guard.py
  py tools/public_repo_guard.py --zip release/Renata_v0.9.4-preview_win_x64.zip
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import zipfile


FORBIDDEN_PREFIXES = (
    "docs/internal/",
    "docs/Flow/private/",
)

FORBIDDEN_IN_ZIP = (
    "docs/internal/",
    "docs/Flow/private/",
    "user_settings.json",
    "config.json",
    "user_logbook.json",
    "log.txt",
)


def _run_git(args: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def _is_forbidden(path: str, prefixes: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in prefixes)


def check_tracked_files() -> list[str]:
    tracked = _run_git(["ls-files"])
    return [p for p in tracked if _is_forbidden(p, FORBIDDEN_PREFIXES)]


def check_staged_additions() -> list[str]:
    staged_names = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [p for p in staged_names if _is_forbidden(p, FORBIDDEN_PREFIXES)]


def check_zip(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return [f"[missing] {path.as_posix()}"]
    offenders: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            normalized = name.replace("\\", "/")
            if any(normalized.startswith(x) for x in FORBIDDEN_IN_ZIP):
                offenders.append(normalized)
                continue
            if normalized.endswith(".log"):
                offenders.append(normalized)
                continue
            if "/tmp/" in f"/{normalized}":
                offenders.append(normalized)
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard FREE public repo/release from private/PRO leakage.")
    parser.add_argument("--zip", dest="zip_path", help="Optional release ZIP path to validate.")
    args = parser.parse_args()

    failed = False

    tracked_offenders = check_tracked_files()
    if tracked_offenders:
        failed = True
        print("FAIL: forbidden tracked files detected:")
        for item in tracked_offenders:
            print(f"  - {item}")

    staged_offenders = check_staged_additions()
    if staged_offenders:
        failed = True
        print("FAIL: forbidden staged additions detected:")
        for item in staged_offenders:
            print(f"  - {item}")

    if args.zip_path:
        zip_offenders = check_zip(pathlib.Path(args.zip_path))
        if zip_offenders:
            failed = True
            print("FAIL: forbidden files detected in release ZIP:")
            for item in zip_offenders:
                print(f"  - {item}")

    if failed:
        print("\nPUBLIC_GUARD=FAIL")
        return 1

    print("PUBLIC_GUARD=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

