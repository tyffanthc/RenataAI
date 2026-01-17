import tkinter as tk
from tkinter import ttk
import time
import config
from logic import utils
from logic.route_clipboard import (
    compute_route_signature,
    format_route_for_clipboard,
    try_copy_to_clipboard,
)


# --- delikatny, neutronowy kolor pod skopiowany wiersz
COPIED_BG = "#CFE8FF"   # jasny niebieski, subtelny
COPIED_FG = "#000000"

_LAST_ROUTE_TEXT = ""
_LAST_ROUTE_SIG = None
_LAST_ROUTE_SYSTEMS: list[str] = []
_LAST_STATUS = {"level": None, "message": ""}
_LAST_OVERLAY_TS = 0.0


def stworz_liste_trasy(parent, title="Plan Lotu"):
    """
    Wzornik listy (jak Neutron).
    Zwraca Listbox.
    """
    frame = ttk.LabelFrame(parent, text=title)
    frame.pack(side="top", fill="both", expand=True, padx=8, pady=8)

    sc = ttk.Scrollbar(frame)
    sc.pack(side="right", fill="y")

    lb = tk.Listbox(
        frame,
        yscrollcommand=sc.set,
        font=("Consolas", 10),
        activestyle="none",
        selectmode="browse",
        exportselection=False
    )
    lb.pack(side="left", fill="both", expand=True)

    sc.config(command=lb.yview)
    return lb


def wypelnij_liste(lb, dane, copied_index=None, autoselect=True, autoscroll=True):
    """
    Wypełnia listę z numeracją.
    Jeśli copied_index jest podany (albo zapisany w config.STATE),
    oznacza ten wiersz jako skopiowany, podświetla go,
    opcjonalnie zaznacza i przewija do niego.

    dane: list[str]
    copied_index: int | None (0-based)
    autoselect: bool – czy ustawić selection na skopiowany wiersz
    autoscroll: bool – czy przewinąć listę do skopiowanego wiersza
    """
    lb.delete(0, tk.END)

    if copied_index is None:
        copied_index = config.STATE.get("copied_idx", None)

    for i, it in enumerate(dane):
        suffix = "  [SKOPIOWANO]" if copied_index == i else ""
        lb.insert(tk.END, f"{i+1}. {it}{suffix}")

    # --- jeżeli mamy skopiowany index, stylujemy i ustawiamy focus
    if copied_index is not None and 0 <= copied_index < len(dane):
        # delikatne podświetlenie wiersza
        try:
            lb.itemconfig(copied_index, {'bg': COPIED_BG, 'fg': COPIED_FG})
        except:
            pass

        # automatyczne zaznaczenie
        if autoselect:
            try:
                lb.selection_clear(0, tk.END)
                lb.selection_set(copied_index)
                lb.activate(copied_index)
            except:
                pass

        # automatyczne przewinięcie
        if autoscroll:
            try:
                lb.see(copied_index)
            except:
                pass


def _extract_route_systems(route):
    if not route:
        return []
    if isinstance(route, (list, tuple)):
        return [str(x).strip() for x in route if str(x).strip()]
    if isinstance(route, dict):
        for key in ("route", "systems", "path", "system_list", "points"):
            items = route.get(key)
            if isinstance(items, (list, tuple)):
                return [str(x).strip() for x in items if str(x).strip()]
        name = route.get("system") or route.get("name")
        if name:
            return [str(name).strip()]
    if isinstance(route, str):
        return [route.strip()] if route.strip() else []
    return []


def set_last_route_data(route, text, sig):
    global _LAST_ROUTE_TEXT, _LAST_ROUTE_SIG, _LAST_ROUTE_SYSTEMS
    if text is not None:
        _LAST_ROUTE_TEXT = text
    if sig is not None:
        _LAST_ROUTE_SIG = sig
    _LAST_ROUTE_SYSTEMS = _extract_route_systems(route)


def get_last_route_text():
    return _LAST_ROUTE_TEXT or ""


def get_last_route_sig():
    return _LAST_ROUTE_SIG


def get_last_route_systems():
    return list(_LAST_ROUTE_SYSTEMS)


def _emit_overlay_status(level, message):
    global _LAST_OVERLAY_TS
    now = time.monotonic()
    if now - _LAST_OVERLAY_TS < 1.0:
        return
    _LAST_OVERLAY_TS = now
    _LAST_STATUS["level"] = level
    _LAST_STATUS["message"] = message
    utils.MSG_QUEUE.put(("overlay_status", (level, message)))


def _maybe_toast(owner, status_target, msg, color, debounce_sec):
    now = time.monotonic()
    last_ts = getattr(owner, "_last_clipboard_toast_ts", 0.0) or 0.0
    if now - last_ts < debounce_sec:
        return
    setattr(owner, "_last_clipboard_toast_ts", now)
    utils.MSG_QUEUE.put((f"status_{status_target}", (msg, color)))


def handle_route_ready_autoclipboard(owner, route, *, status_target, debounce_sec=1.5):
    text = format_route_for_clipboard(route)
    sig = compute_route_signature(route)
    set_last_route_data(route, text, sig)

    if not config.get("auto_clipboard"):
        return

    last_sig = getattr(owner, "_last_copied_route_sig", None)
    if sig and last_sig == sig:
        utils.MSG_QUEUE.put(("log", "[AUTO-SCHOWEK] Cache: route clipboard hit/skip"))
        return

    if not text:
        _maybe_toast(
            owner,
            status_target,
            "Nie mogę skopiować do schowka — skopiuj ręcznie",
            "orange",
            debounce_sec,
        )
        _emit_overlay_status("warn", "Nie mogę skopiować — skopiuj ręcznie")
        return

    result = try_copy_to_clipboard(text)
    if result.get("ok"):
        if sig:
            setattr(owner, "_last_copied_route_sig", sig)
        _maybe_toast(
            owner,
            status_target,
            "Trasa skopiowana do schowka",
            "green",
            debounce_sec,
        )
        _emit_overlay_status("ok", "Skopiowano trasę")
    else:
        _maybe_toast(
            owner,
            status_target,
            "Nie mogę skopiować do schowka — skopiuj ręcznie",
            "orange",
            debounce_sec,
        )
        _emit_overlay_status("warn", "Nie mogę skopiować — skopiuj ręcznie")
        err = result.get("error")
        if err:
            utils.MSG_QUEUE.put(("log", f"[AUTO-SCHOWEK] Clipboard error: {err}"))
