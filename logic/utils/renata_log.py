from __future__ import annotations

from typing import Any
import threading
import time

import config

from logic import utils


MAX_FIELD_LEN = 400
MAX_COLLECTION_ITEMS = 12
MAX_OBJECT_FIELDS = 10
MAX_DEPTH = 3

_THROTTLE_LOCK = threading.Lock()
_THROTTLE_LAST: dict[str, float] = {}


def _now() -> float:
    return time.monotonic()


def _debug_logging_enabled() -> bool:
    return bool(config.get("debug_logging", False))


def safe_repr(value: Any, *, max_len: int = MAX_FIELD_LEN) -> str:
    seen: set[int] = set()

    def _inner(val: Any, depth: int) -> str:
        if id(val) in seen:
            return "<recursion>"
        if isinstance(val, (str, int, float, bool)) or val is None:
            return str(val)
        if isinstance(val, bytes):
            try:
                return val.decode("utf-8", errors="replace")
            except Exception:
                return repr(val)
        if depth <= 0:
            return "<...>"
        if isinstance(val, dict):
            seen.add(id(val))
            parts = []
            for idx, (key, item) in enumerate(val.items()):
                if idx >= MAX_COLLECTION_ITEMS:
                    parts.append("...")
                    break
                parts.append(f"{_inner(key, depth - 1)}: {_inner(item, depth - 1)}")
            seen.discard(id(val))
            return "{" + ", ".join(parts) + "}"
        if isinstance(val, (list, tuple, set)):
            seen.add(id(val))
            parts = []
            for idx, item in enumerate(val):
                if idx >= MAX_COLLECTION_ITEMS:
                    parts.append("...")
                    break
                parts.append(_inner(item, depth - 1))
            seen.discard(id(val))
            if isinstance(val, tuple):
                return "(" + ", ".join(parts) + ")"
            if isinstance(val, set):
                return "{" + ", ".join(parts) + "}"
            return "[" + ", ".join(parts) + "]"
        if hasattr(val, "__dict__"):
            seen.add(id(val))
            fields = list(val.__dict__.items())
            parts = []
            for idx, (key, item) in enumerate(fields):
                if idx >= MAX_OBJECT_FIELDS:
                    parts.append("...")
                    break
                parts.append(f"{key}={_inner(item, depth - 1)}")
            seen.discard(id(val))
            return f"<{type(val).__name__} " + " ".join(parts) + ">"
        try:
            return repr(val)
        except Exception:
            return f"<{type(val).__name__}>"

    try:
        text = _inner(value, MAX_DEPTH)
    except Exception:
        text = f"<{type(value).__name__}>"
    if not isinstance(text, str):
        text = str(text)
    if len(text) > max_len:
        return f"{text[:max_len]}..."
    return text


def _format_value(value: Any) -> str:
    return safe_repr(value, max_len=MAX_FIELD_LEN)


def log_event(category: str, msg: str, **fields: Any) -> None:
    """
    Emit a short, structured log line to the main log stream.
    Format: [CATEGORY] message key=value ...
    """
    try:
        cat = str(category or "GENERAL").strip().upper()
        base = f"[{cat}] {msg}"
        if fields:
            parts = [
                f"{key}={_format_value(value)}" for key, value in fields.items()
            ]
            line = f"{base} " + " ".join(parts)
        else:
            line = base
        try:
            utils.MSG_QUEUE.put(("log", line))
        except Exception:
            print(line)
    except Exception:
        if _debug_logging_enabled():
            print("logging failed")


def log_event_throttled(*args: Any, **fields: Any) -> bool:
    """
    Emit throttled structured logs.

    Supported call signatures:
    1) log_event_throttled(key, interval_ms, category, msg, **fields)
    2) legacy:
       log_event_throttled(category, code, msg, cooldown_sec=60.0, context="...", **fields)
    """
    try:
        category = "GENERAL"
        msg = ""
        key = ""
        payload = dict(fields)

        if len(args) >= 4 and isinstance(args[1], (int, float)):
            key = str(args[0] or "").strip()
            interval_sec = max(0.0, float(args[1]) / 1000.0)
            category = str(args[2] or "GENERAL").strip().upper() or "GENERAL"
            msg = str(args[3] or "")
        elif len(args) >= 3:
            # Backward compatibility for older callsites that used
            # (level, code, msg, cooldown_sec=..., context=...).
            category = str(args[0] or "GENERAL").strip().upper() or "GENERAL"
            code = str(args[1] or "").strip()
            msg = str(args[2] or "")
            cooldown_sec_raw = payload.pop("cooldown_sec", 60.0)
            context = str(payload.get("context") or "").strip()
            try:
                interval_sec = max(0.0, float(cooldown_sec_raw))
            except Exception:
                interval_sec = 60.0
            key = context or code or f"{category}:{msg}"
            if code and "code" not in payload:
                payload["code"] = code
        else:
            return False

        if not key:
            key = f"{category}:{msg}".strip() or "GENERAL"

        now = _now()
        with _THROTTLE_LOCK:
            last = _THROTTLE_LAST.get(key)
            if last is not None and (now - last) < interval_sec:
                return False
            _THROTTLE_LAST[key] = now
        log_event(category, msg, **payload)
        return True
    except Exception:
        if _debug_logging_enabled():
            print("logging failed")
        return False
