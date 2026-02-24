from __future__ import annotations

from collections.abc import Callable
from typing import Any

from logic.utils.renata_log import log_event_throttled


def run_on_ui_thread(ui_target: Any, callback: Callable[[], Any]) -> None:
    """
    Schedule callback on Tk main loop.

    Fallback to direct call if target has no .after() (e.g. in tests).
    """
    if not callable(callback):
        return

    after = getattr(ui_target, "after", None)
    if callable(after):
        try:
            after(0, callback)
            return
        except Exception as exc:
            log_event_throttled(
                "GUI:ui_thread.after",
                3000,
                "GUI",
                "failed to schedule callback on UI thread; falling back to direct call",
                error=f"{type(exc).__name__}: {exc}",
            )

    callback()
