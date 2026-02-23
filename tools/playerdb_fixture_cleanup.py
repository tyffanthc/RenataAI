from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.player_local_db import cleanup_fixture_test_data, DEFAULT_FIXTURE_PREFIXES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cleanup fixture/test records from player_local.db (dry-run by default)."
    )
    parser.add_argument("--path", default=None, help="Path to player_local.db (defaults to runtime APPDATA path)")
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        help=(
            "Fixture prefix (repeatable). "
            f"Default prefixes: {', '.join(DEFAULT_FIXTURE_PREFIXES)}"
        ),
    )
    parser.add_argument("--apply", action="store_true", help="Apply deletions (otherwise dry-run)")
    args = parser.parse_args(argv)

    report = cleanup_fixture_test_data(
        path=args.path,
        prefixes=args.prefixes,
        dry_run=not bool(args.apply),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
