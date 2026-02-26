"""
Analyze Renata `VALUE cashin_sell_snapshot` logs to compare:
- sale_earnings from journal sell events
- balance delta between consecutive sell snapshots
- Renata estimated session/system values

Usage:
    py -3 tools/cashin_value_snapshot_analyzer.py path\\to\\renata.log
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional


FIELD_START_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=")
TS_RE = re.compile(r"^\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*")


@dataclass
class SnapshotRow:
    line_no: int
    timestamp: str | None
    event: str
    sale_earnings: float | None
    balance: float | None
    current_system: str
    estimate_system: float | None
    estimate_session_total: float | None
    estimate_carto: float | None
    estimate_exobio: float | None
    estimate_bonus: float | None


def _to_float(value: str | None) -> float | None:
    txt = str(value or "").strip()
    if txt == "" or txt.lower() in {"none", "null"}:
        return None
    try:
        return float(txt)
    except Exception:
        return None


def _parse_fields(text: str) -> dict[str, str]:
    """
    Parse `key=value` pairs where values may contain spaces.
    We detect all `key=` anchors and slice value until next anchor.
    """
    out: dict[str, str] = {}
    matches = list(FIELD_START_RE.finditer(text))
    for idx, match in enumerate(matches):
        key = str(match.group("key") or "").strip()
        val_start = match.end()
        val_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        value = text[val_start:val_end].strip()
        if key:
            out[key] = value
    return out


def _parse_snapshot_line(line: str, line_no: int) -> Optional[SnapshotRow]:
    if "[VALUE]" not in line or "cashin_sell_snapshot" not in line:
        return None

    ts: str | None = None
    line_wo_ts = line.rstrip("\r\n")
    m_ts = TS_RE.match(line_wo_ts)
    if m_ts:
        ts = str(m_ts.group("ts") or "").strip() or None
        line_wo_ts = line_wo_ts[m_ts.end() :].lstrip()

    marker = "[VALUE] cashin_sell_snapshot"
    pos = line_wo_ts.find(marker)
    if pos < 0:
        return None
    payload = line_wo_ts[pos + len(marker) :].strip()
    fields = _parse_fields(payload)

    return SnapshotRow(
        line_no=int(line_no),
        timestamp=ts,
        event=str(fields.get("event") or "").strip(),
        sale_earnings=_to_float(fields.get("sale_earnings")),
        balance=_to_float(fields.get("balance")),
        current_system=str(fields.get("current_system") or "").strip(),
        estimate_system=_to_float(fields.get("estimate_system")),
        estimate_session_total=_to_float(fields.get("estimate_session_total")),
        estimate_carto=_to_float(fields.get("estimate_carto")),
        estimate_exobio=_to_float(fields.get("estimate_exobio")),
        estimate_bonus=_to_float(fields.get("estimate_bonus")),
    )


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def _fmt_delta(value: float | None, ref: float | None) -> str:
    if value is None or ref is None:
        return "-"
    return f"{(value - ref):+,.2f}"


def _iter_snapshots(path: str) -> list[SnapshotRow]:
    rows: list[SnapshotRow] = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for idx, raw_line in enumerate(handle, start=1):
            row = _parse_snapshot_line(raw_line, idx)
            if row is not None:
                rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Renata VALUE cashin_sell_snapshot logs.")
    parser.add_argument("log_file", help="Path to Renata log file (text).")
    parser.add_argument(
        "--only-events",
        default="",
        help="Comma-separated event names to keep (e.g. SellExplorationData,SellOrganicData).",
    )
    args = parser.parse_args()

    path = os.path.abspath(str(args.log_file))
    if not os.path.isfile(path):
        print(f"[ERR] Log file not found: {path}")
        return 1

    rows = _iter_snapshots(path)
    if args.only_events.strip():
        allow = {x.strip() for x in str(args.only_events).split(",") if x.strip()}
        rows = [r for r in rows if r.event in allow]

    print("=== CASH-IN VALUE SNAPSHOT ANALYZER ===")
    print(f"log_file={path}")
    print(f"snapshots={len(rows)}")
    if not rows:
        return 0

    header = (
        "idx  line   time      event                sale_earnings     balance"
        "          Δbalance       est_session      Δ(est-sale)      system"
    )
    print(header)
    print("-" * len(header))

    prev_balance: float | None = None
    for idx, row in enumerate(rows, start=1):
        delta_balance = None
        if prev_balance is not None and row.balance is not None:
            delta_balance = row.balance - prev_balance
        est_minus_sale = None
        if row.estimate_session_total is not None and row.sale_earnings is not None:
            est_minus_sale = row.estimate_session_total - row.sale_earnings
        print(
            f"{idx:>3}  {row.line_no:>5}  {(row.timestamp or '-'):>8}  "
            f"{(row.event or '-')[:20]:<20}  "
            f"{_fmt_num(row.sale_earnings):>14}  "
            f"{_fmt_num(row.balance):>14}  "
            f"{_fmt_num(delta_balance):>12}  "
            f"{_fmt_num(row.estimate_session_total):>14}  "
            f"{_fmt_num(est_minus_sale):>14}  "
            f"{(row.current_system or '-')[:28]}"
        )
        if row.balance is not None:
            prev_balance = row.balance

    print("\nSummary:")
    rows_with_balance_delta = 0
    rows_balance_match = 0
    rows_est_match = 0
    for row_idx, row in enumerate(rows):
        if row_idx > 0:
            prev = rows[row_idx - 1]
            if row.balance is not None and prev.balance is not None and row.sale_earnings is not None:
                rows_with_balance_delta += 1
                if abs((row.balance - prev.balance) - row.sale_earnings) < 0.01:
                    rows_balance_match += 1
        if row.estimate_session_total is not None and row.sale_earnings is not None:
            if abs(row.estimate_session_total - row.sale_earnings) < 0.01:
                rows_est_match += 1
    print(f"- balance delta comparable rows: {rows_with_balance_delta}")
    print(f"- exact matches (delta balance == sale_earnings): {rows_balance_match}")
    print(f"- exact matches (estimate_session_total == sale_earnings): {rows_est_match}")
    print("- note: mismatch can be valid in some scenarios (partial sell, bonuses, mixed sale order, prior cash-in).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

