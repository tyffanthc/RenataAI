from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Callable

import config
from logic import utils


class _InFlight:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any | None = None
        self.error: BaseException | None = None


_LOCK = threading.Lock()
_IN_FLIGHT: dict[str, _InFlight] = {}


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def make_request_key(provider: str, endpoint: str, params: Any) -> str:
    raw = f"{provider}|{endpoint}|{_stable_json(params)}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{provider}:{endpoint}:{digest}"


def _emit_dedup_status(code: str, text: str) -> None:
    try:
        from gui import common as gui_common  # type: ignore

        gui_common.emit_status(
            "INFO",
            code,
            text=text,
            source="dedup",
            notify_overlay=False,
        )
    except Exception:
        utils.MSG_QUEUE.put(("log", f"[DEDUP] {code}: {text}"))


def run_deduped(key: str, fn: Callable[[], Any]) -> Any:
    owner = False
    with _LOCK:
        inflight = _IN_FLIGHT.get(key)
        if inflight is None:
            inflight = _InFlight()
            _IN_FLIGHT[key] = inflight
            owner = True
        else:
            if config.get("debug_dedup", False):
                _emit_dedup_status("DEDUP_WAIT", "Dedup wait")

    if not owner:
        inflight.event.wait()
        if inflight.error is not None:
            raise inflight.error
        return inflight.result

    try:
        result = fn()
        inflight.result = result
        if config.get("debug_dedup", False):
            _emit_dedup_status("DEDUP_HIT", "Dedup hit")
        return result
    except BaseException as exc:
        inflight.error = exc
        raise
    finally:
        inflight.event.set()
        with _LOCK:
            _IN_FLIGHT.pop(key, None)
