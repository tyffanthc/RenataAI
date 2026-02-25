from __future__ import annotations

import json
import os
from typing import Any

from logic.utils.renata_log import log_event_throttled

_DEFAULT_LIMIT = 250


def _default_logbook_cache_file() -> str:
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if appdata:
        return os.path.join(appdata, "RenataAI", "cache", "logbook", "feed.jsonl")
    return os.path.join(os.path.expanduser("~"), ".cache", "RenataAI", "logbook", "feed.jsonl")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _is_valid_feed_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    event_name = str(item.get("event_name") or "").strip()
    return bool(event_name)


def _feed_item_signature(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    parts = [
        str(item.get("timestamp") or "").strip(),
        str(item.get("event_name") or "").strip(),
        str(item.get("system_name") or "").strip(),
        str(item.get("station_name") or "").strip(),
        str(item.get("body_name") or "").strip(),
        str(item.get("summary") or "").strip(),
    ]
    if not any(parts):
        return ""
    return "\x1f".join(parts)


def _read_all_items(path: str) -> list[dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = str(raw_line or "").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    # Tolerate a partially written/truncated line after crash.
                    log_event_throttled(
                        "logbook_feed_cache_jsonl_line",
                        30.0,
                        "WARN",
                        "logbook feed cache: invalid/truncated jsonl line skipped",
                        path=path,
                    )
                    continue
                if _is_valid_feed_item(payload):
                    rows.append(dict(payload))
    except Exception:
        log_event_throttled(
            "logbook_feed_cache_read_all",
            30.0,
            "WARN",
            "logbook feed cache: read failed; using empty cache",
            path=path,
        )
        return []
    return rows


def load_logbook_feed_cache(
    *,
    path: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    cache_path = path or _default_logbook_cache_file()
    rows = _read_all_items(cache_path)
    max_items = max(1, int(limit or _DEFAULT_LIMIT))
    if len(rows) > max_items:
        rows = rows[-max_items:]
    return [dict(row) for row in rows]


def _write_all_items(path: str, items: list[dict[str, Any]]) -> None:
    _ensure_parent_dir(path)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in items:
            if not _is_valid_feed_item(row):
                continue
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    os.replace(tmp_path, path)


def append_logbook_feed_cache_item(
    item: dict[str, Any],
    *,
    path: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> bool:
    if not _is_valid_feed_item(item):
        return False
    cache_path = path or _default_logbook_cache_file()
    max_items = max(1, int(limit or _DEFAULT_LIMIT))
    rows = _read_all_items(cache_path)
    incoming_sig = _feed_item_signature(item)
    if incoming_sig:
        for row in rows:
            if _feed_item_signature(row) == incoming_sig:
                return True
    rows.append(dict(item))
    if len(rows) > max_items:
        rows = rows[-max_items:]
    try:
        _write_all_items(cache_path, rows)
        return True
    except Exception:
        log_event_throttled(
            "logbook_feed_cache_append",
            30.0,
            "WARN",
            "logbook feed cache: append/write failed",
            path=cache_path,
        )
        return False


def clear_logbook_feed_cache(*, path: str | None = None) -> None:
    cache_path = path or _default_logbook_cache_file()
    try:
        if os.path.isfile(cache_path):
            os.remove(cache_path)
    except Exception:
        log_event_throttled(
            "logbook_feed_cache_clear",
            30.0,
            "WARN",
            "logbook feed cache: clear failed",
            path=cache_path,
        )
        return
