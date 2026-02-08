from __future__ import annotations

from collections.abc import Callable
from typing import Any


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
        except Exception:
            pass

    callback()

