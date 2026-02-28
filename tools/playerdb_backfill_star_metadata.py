from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
from logic import player_local_db


STAR_META_EVENTS = {"Location", "FSDJump", "CarrierJump", "Scan"}


def _iter_journal_files(log_dir: str, *, limit_files: int | None = None) -> list[str]:
    files = sorted(glob.glob(os.path.join(log_dir, "Journal.*.log")))
    if limit_files is not None and limit_files > 0:
        return files[-int(limit_files):]
    return files


def run_backfill(*, db_path: str, log_dir: str, limit_files: int | None = None) -> dict[str, Any]:
    files = _iter_journal_files(log_dir, limit_files=limit_files)
    if not files:
        return {
            "ok": False,
            "reason": "no_journal_files",
            "log_dir": log_dir,
            "db_path": db_path,
        }

    scanned_lines = 0
    scanned_events = 0
    updated = 0
    skipped_no_meta = 0
    skipped_no_system = 0
    errors = 0

    for path in files:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                scanned_lines += 1
                line = str(raw or "").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                event_name = str(ev.get("event") or "")
                if event_name not in STAR_META_EVENTS:
                    continue
                scanned_events += 1
                try:
                    out = player_local_db.ingest_star_metadata_event(ev, path=db_path)
                except Exception:
                    errors += 1
                    continue
                if bool(out.get("ok")):
                    updated += 1
                    continue
                reason = str(out.get("reason") or "")
                if reason == "no_star_metadata":
                    skipped_no_meta += 1
                elif reason == "missing_system_name":
                    skipped_no_system += 1
                else:
                    errors += 1

    return {
        "ok": True,
        "db_path": db_path,
        "log_dir": log_dir,
        "files": len(files),
        "scanned_lines": scanned_lines,
        "scanned_star_events": scanned_events,
        "updated_systems": updated,
        "skipped_no_star_metadata": skipped_no_meta,
        "skipped_missing_system_name": skipped_no_system,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill playerdb systems.primary_star_type / neutron / black-hole from Journal logs."
    )
    parser.add_argument(
        "--db-path",
        default=player_local_db.default_playerdb_path(),
        help="Path to player_local.db (default: appdata RenataAI db).",
    )
    parser.add_argument(
        "--log-dir",
        default=config.get("log_dir"),
        help="Directory with Journal.*.log files.",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="Only process newest N journal files (optional).",
    )
    args = parser.parse_args()

    result = run_backfill(
        db_path=str(args.db_path),
        log_dir=str(args.log_dir),
        limit_files=args.limit_files,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
