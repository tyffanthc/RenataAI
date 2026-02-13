from __future__ import annotations

import sys
import ctypes
from ctypes import wintypes


_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _hex_to_colorref(value: str) -> int:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        raise ValueError("Expected #RRGGBB color")
    r = int(text[0:2], 16)
    g = int(text[2:4], 16)
    b = int(text[4:6], 16)
    return (b << 16) | (g << 8) | r


def _set_dwm_color(hwnd: int, attr: int, color_hex: str) -> None:
    color = wintypes.DWORD(_hex_to_colorref(color_hex))
    dwmapi = ctypes.windll.dwmapi
    hr = dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(attr),
        ctypes.byref(color),
        ctypes.sizeof(color),
    )
    if int(hr) != 0:
        raise OSError(f"DwmSetWindowAttribute failed with HRESULT={int(hr)}")


def apply_window_chrome_colors(
    window,
    *,
    caption_hex: str,
    border_hex: str | None = None,
    text_hex: str | None = None,
) -> bool:
    """
    Best-effort: apply Windows titlebar/border/text colors for a Tk window.
    Returns True when at least one attribute is applied.
    """
    if sys.platform != "win32":
        return False

    window.update_idletasks()
    hwnd = int(window.winfo_id())
    applied = False

    _set_dwm_color(hwnd, _DWMWA_CAPTION_COLOR, caption_hex)
    applied = True

    if border_hex:
        _set_dwm_color(hwnd, _DWMWA_BORDER_COLOR, border_hex)
        applied = True

    if text_hex:
        _set_dwm_color(hwnd, _DWMWA_TEXT_COLOR, text_hex)
        applied = True

    return applied


def apply_renata_orange_window_chrome(window) -> bool:
    return apply_window_chrome_colors(
        window,
        caption_hex="#ff7100",
        border_hex="#ff7100",
        text_hex="#0b0c10",
    )

