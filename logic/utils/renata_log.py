from __future__ import annotations

from typing import Any

from logic import utils


MAX_FIELD_LEN = 120


def _format_value(value: Any) -> str:
    text = str(value)
    if len(text) > MAX_FIELD_LEN:
        return f"{text[:MAX_FIELD_LEN]}..."
    return text


def log_event(category: str, msg: str, **fields: Any) -> None:
    """
    Emit a short, structured log line to the main log stream.
    Format: [OBS][CATEGORY] message key=value ...
    """
    cat = str(category or "GENERAL").strip().upper()
    base = f"[OBS][{cat}] {msg}"
    if fields:
        parts = [f"{key}={_format_value(value)}" for key, value in fields.items()]
        line = f"{base} " + " ".join(parts)
    else:
        line = base
    try:
        utils.MSG_QUEUE.put(("log", line))
    except Exception:
        print(line)
