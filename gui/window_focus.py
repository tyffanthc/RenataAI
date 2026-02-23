from __future__ import annotations

from typing import Any

import config
from logic.utils.renata_log import log_event, log_event_throttled


def _trace_enabled() -> bool:
    return bool(config.get("features.debug.focus_trace", False))


def _target_label(win: Any) -> str:
    try:
        cls = type(win).__name__
    except Exception:
        cls = "unknown"
    try:
        title = str(getattr(win, "title")() or "").strip()
    except Exception:
        title = ""
    if title:
        return f"{cls}:{title}"
    return cls


def _trace(
    action: str,
    *,
    source: str,
    win: Any,
    result: str = "ok",
    user_initiated: bool | None = None,
    reason: str = "",
) -> None:
    if not _trace_enabled():
        return
    fields: dict[str, Any] = {
        "action": action,
        "source": source,
        "target": _target_label(win),
        "result": result,
    }
    if user_initiated is not None:
        fields["user_initiated"] = bool(user_initiated)
    if reason:
        fields["reason"] = reason
    log_event("FOCUS", "window action", **fields)


def _call_window_action(
    win: Any,
    method_name: str,
    *,
    source: str,
    user_initiated: bool | None = None,
) -> bool:
    method = getattr(win, method_name, None)
    if not callable(method):
        _trace(
            method_name,
            source=source,
            win=win,
            result="skip",
            user_initiated=user_initiated,
            reason="method_missing",
        )
        return False
    try:
        method()
        _trace(method_name, source=source, win=win, user_initiated=user_initiated)
        return True
    except Exception as exc:
        _trace(
            method_name,
            source=source,
            win=win,
            result="error",
            user_initiated=user_initiated,
            reason=f"{type(exc).__name__}",
        )
        log_event_throttled(
            f"FOCUS:{source}:{method_name}",
            10_000,
            "FOCUS",
            "window focus action failed",
            action=method_name,
            source=source,
            error=f"{type(exc).__name__}: {exc}",
        )
        return False


def request_window_focus(
    win: Any,
    *,
    source: str,
    user_initiated: bool,
    force: bool = False,
) -> bool:
    # Runtime/autonomous paths must not demand foreground.
    if force and not user_initiated:
        _trace(
            "focus_force",
            source=source,
            win=win,
            result="blocked",
            user_initiated=user_initiated,
            reason="not_user_initiated",
        )
        return False
    method_name = "focus_force" if force else "focus_set"
    return _call_window_action(
        win,
        method_name,
        source=source,
        user_initiated=user_initiated,
    )


def bring_window_to_front(
    win: Any,
    *,
    source: str,
    user_initiated: bool,
    deiconify: bool = True,
    request_focus: bool = True,
    force_focus: bool = False,
) -> bool:
    ok = False
    if deiconify:
        ok = _call_window_action(
            win,
            "deiconify",
            source=source,
            user_initiated=user_initiated,
        ) or ok
    ok = _call_window_action(
        win,
        "lift",
        source=source,
        user_initiated=user_initiated,
    ) or ok
    if request_focus:
        ok = request_window_focus(
            win,
            source=source,
            user_initiated=user_initiated,
            force=force_focus,
        ) or ok
    return ok

