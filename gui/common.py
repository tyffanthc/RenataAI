import tkinter as tk
from tkinter import ttk
import time
import threading
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

STATUS_TEXTS = {
    "ROUTE_COPIED": "Skopiowano trasę",
    "CLIPBOARD_FAIL": "Nie mogę skopiować — skopiuj ręcznie",
    "ROUTE_EMPTY": "Brak wyników.",
    "ROUTE_FOUND": "Znaleziono trasę.",
    "ROUTE_CLEARED": "Wyczyszczono.",
    "ROUTE_ERROR": "Błąd trasy.",
    "TRADE_FOUND": "Znaleziono propozycje.",
    "TRADE_NO_RESULTS": "Brak wyników lub błąd API.",
    "TRADE_INPUT_MISSING": "Podaj system startowy.",
    "TRADE_STATION_REQUIRED": "Wybierz stację startową — SPANSH Trade wymaga system+station.",
    "TRADE_ERROR": "Błąd trade.",
    "CACHE_HIT": "Cache hit",
    "CACHE_MISS": "Cache miss",
    "CACHE_WRITE_FAIL": "Nie udało się zapisać cache.",
    "CACHE_CORRUPT": "Cache uszkodzony.",
    "DEDUP_HIT": "Dedup hit",
    "DEDUP_WAIT": "Dedup wait",
    "AUTO_CLIPBOARD_OFF": "Auto-schowek wyłączony.",
}


def _level_color(level: str) -> str:
    colors = {
        "OK": "green",
        "INFO": "grey",
        "WARN": "orange",
        "ERROR": "red",
        "BUSY": "grey",
    }
    return colors.get(level, "grey")


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


def wypelnij_liste(
    lb,
    dane,
    copied_index=None,
    autoselect=True,
    autoscroll=True,
    numerate=True,
):
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
        if numerate:
            lb.insert(tk.END, f"{i+1}. {it}{suffix}")
        else:
            lb.insert(tk.END, f"{it}{suffix}")

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


def emit_status(
    level: str,
    code: str,
    text: str | None = None,
    *,
    source: str | None = None,
    sticky: bool = False,
    ui_target: str | None = None,
    notify_overlay: bool = True,
) -> dict:
    if text is None:
        text = STATUS_TEXTS.get(code, code)
    event = {
        "level": level,
        "code": code,
        "text": text,
        "ts": time.time(),
        "source": source,
        "sticky": bool(sticky),
    }
    if notify_overlay:
        utils.MSG_QUEUE.put(("status_event", event))
    utils.MSG_QUEUE.put(("log", f"[{level}] {code}: {text}"))
    if ui_target:
        color = _level_color(level)
        utils.MSG_QUEUE.put((f"status_{ui_target}", (text, color)))
    return event


def _maybe_toast(owner, status_target, level, code, text, debounce_sec, source=None):
    now = time.monotonic()
    last_ts = getattr(owner, "_last_clipboard_toast_ts", 0.0) or 0.0
    if now - last_ts < debounce_sec:
        return
    setattr(owner, "_last_clipboard_toast_ts", now)
    emit_status(
        level,
        code,
        text,
        source=source,
        ui_target=status_target,
    )


def handle_route_ready_autoclipboard(owner, route, *, status_target, debounce_sec=1.5):
    text = format_route_for_clipboard(route)
    sig = compute_route_signature(route)
    set_last_route_data(route, text, sig)

    def _do_copy():
        if not config.get("auto_clipboard"):
            emit_status(
                "INFO",
                "AUTO_CLIPBOARD_OFF",
                source=f"spansh.{status_target}",
                notify_overlay=False,
            )
            return

        last_sig = getattr(owner, "_last_copied_route_sig", None)
        if sig and last_sig == sig:
            utils.MSG_QUEUE.put(("log", "[AUTO-SCHOWEK] Cache: route clipboard hit/skip"))
            return

        if not text:
            _maybe_toast(
                owner,
                status_target,
                "WARN",
                "ROUTE_EMPTY",
                STATUS_TEXTS["CLIPBOARD_FAIL"],
                debounce_sec,
                source=f"spansh.{status_target}",
            )
            return

        result = try_copy_to_clipboard(text)
        if result.get("ok"):
            if sig:
                setattr(owner, "_last_copied_route_sig", sig)
            _maybe_toast(
                owner,
                status_target,
                "OK",
                "ROUTE_COPIED",
                STATUS_TEXTS["ROUTE_COPIED"],
                debounce_sec,
                source=f"spansh.{status_target}",
            )
        else:
            _maybe_toast(
                owner,
                status_target,
                "WARN",
                "CLIPBOARD_FAIL",
                STATUS_TEXTS["CLIPBOARD_FAIL"],
                debounce_sec,
                source=f"spansh.{status_target}",
            )
            err = result.get("error")
            if err:
                utils.MSG_QUEUE.put(("log", f"[AUTO-SCHOWEK] Clipboard error: {err}"))

    if threading.current_thread() is not threading.main_thread():
        try:
            owner.after(0, _do_copy)
            return
        except Exception:
            pass

    _do_copy()
