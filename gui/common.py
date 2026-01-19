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
_ACTIVE_ROUTE_SYSTEMS: list[str] = []
_ACTIVE_ROUTE_SYSTEMS_RAW: list[str] = []
_ACTIVE_ROUTE_SIG = None
_ACTIVE_ROUTE_TEXT = ""
_ACTIVE_ROUTE_INDEX: int = 0
_ACTIVE_ROUTE_CURRENT_SYSTEM: str | None = None
_ACTIVE_ROUTE_LAST_COPIED_SYSTEM: str | None = None
_ACTIVE_ROUTE_LAST_PROGRESS_AT: float | None = None
_ACTIVE_ROUTE_SOURCE: str | None = None
_ACTIVE_ROUTE_LISTBOX = None
_ACTIVE_ROUTE_LIST_DATA: list[str] = []
_ACTIVE_ROUTE_LIST_NUMERATE = True
_ACTIVE_ROUTE_LIST_OFFSET = 0
_ACTIVE_ROUTE_TABLE_SCHEMA: str | None = None
_ACTIVE_ROUTE_TABLE_ROWS: list[dict] = []
_ACTIVE_ROUTE_TABLE_VISIBLE: list[str] | None = None

STATUS_TEXTS = {
    "NEXT_HOP_COPIED": "Skopiowano nastepny system.",
    "ROUTE_COMPLETE": "Trasa zakonczona.",
    "ROUTE_DESYNC": "Jestes poza trasa - nie kopiuje kolejnego celu.",
    "NEXT_HOP_EMPTY": "Brak kolejnego celu.",
    "AUTO_CLIPBOARD_MODE_NEXT_HOP": "Auto-schowek: tryb NEXT_HOP.",
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
    "JR_READY": "Jump range obliczony.",
    "JR_WAITING_DATA": "Jump range: czekam na dane.",
    "JR_COMPUTE_FAIL": "Jump range: b‘'Žd oblicze‘'.",
    "JR_VALIDATE_OK": "Jump range: walidacja OK.",
    "JR_VALIDATE_DELTA": "Jump range: odchy‘'ka od gry.",
    "JR_ENGINEERING_APPLIED": "Jump range: zastosowano engineering.",
    "JR_NOT_READY_FALLBACK": "Jump range: brak danych, u‘•ywam fallback.",
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
    show_copied_suffix=True,
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
        suffix = "  [SKOPIOWANO]" if show_copied_suffix and copied_index == i else ""
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


def normalize_system_name(name) -> str:
    if not name:
        return ""
    text = " ".join(str(name).strip().split())
    if not text:
        return ""
    return text.casefold()


def _format_bool(value) -> str:
    if value is True:
        return "Y"
    if value is False:
        return ""
    return ""


def _format_number(value, fmt: str) -> str:
    try:
        num = float(value)
    except Exception:
        return "-"
    if fmt == "int":
        return str(int(round(num)))
    if fmt == "percent":
        return f"{num:.0f}%"
    if fmt == "ly":
        return f"{num:.2f}"
    if fmt == "ls":
        return f"{num:.0f}"
    if fmt == "cr":
        try:
            return f"{int(round(num)):,}".replace(",", " ")
        except Exception:
            return str(num)
    return str(num)


def format_value(value, fmt: str) -> str:
    if fmt == "bool":
        return _format_bool(value)
    if fmt in ("int", "float", "percent", "ly", "ls", "cr"):
        return _format_number(value, fmt)
    if value is None:
        return "-"
    return str(value)


def _get_value_by_key(row: dict, key: str):
    if not key:
        return None
    if "." not in key:
        return row.get(key)
    cur = row
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _align_text(text: str, width: int | None, align: str) -> str:
    if width is None:
        return text
    if len(text) > width:
        text = text[:width]
    if align == "right":
        return text.rjust(width)
    if align == "center":
        return text.center(width)
    return text.ljust(width)


def _get_visible_columns(schema_id: str) -> list[str]:
    try:
        from gui import table_schemas
    except Exception:
        return []
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return []
    visible_cfg = config.get("tables_visible_columns", {})
    visible = []
    if isinstance(visible_cfg, dict):
        visible = visible_cfg.get(schema_id) or []
    if not isinstance(visible, list) or not visible:
        visible = [col.key for col in schema.columns if col.default_visible]
    if len(visible) < 2:
        visible = [col.key for col in schema.columns[:2]]
    return visible


def render_table_lines(schema_id: str, rows: list[dict]) -> list[str]:
    if not config.get("features.tables.spansh_schema_enabled", True):
        return []
    if not config.get("features.tables.schema_renderer_enabled", True):
        return []
    try:
        from gui import table_schemas
    except Exception:
        return []
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return []

    visible_cols = _get_visible_columns(schema_id)
    columns = [col for col in schema.columns if col.key in visible_cols]
    if not columns:
        return []

    header = "  ".join(
        _align_text(col.label, col.width, col.align) for col in columns
    )
    lines = [header]

    badges_enabled = bool(config.get("features.tables.ui_badges_enabled", True))
    for row in rows:
        meta = row.get("_meta", {}) if isinstance(row, dict) else {}
        badges = meta.get("badges", []) if isinstance(meta, dict) else []
        suffix = " [SKOPIOWANO]" if badges_enabled and "COPIED" in badges else ""
        primary_key = None
        for key in ("system_name", "body_name", "name"):
            if key in [col.key for col in columns]:
                primary_key = key
                break

        parts = []
        for col in columns:
            value = _get_value_by_key(row, col.value_path or col.key)
            text = format_value(value, col.fmt)
            if suffix and col.key == primary_key:
                text = f"{text}{suffix}"
                suffix = ""
            parts.append(_align_text(text, col.width, col.align))
        lines.append("  ".join(parts))

    return lines


def _set_active_route_data(route, text, sig, source: str | None) -> None:
    global _ACTIVE_ROUTE_SYSTEMS, _ACTIVE_ROUTE_SYSTEMS_RAW
    global _ACTIVE_ROUTE_SIG, _ACTIVE_ROUTE_TEXT, _ACTIVE_ROUTE_INDEX
    global _ACTIVE_ROUTE_CURRENT_SYSTEM, _ACTIVE_ROUTE_LAST_COPIED_SYSTEM
    global _ACTIVE_ROUTE_LAST_PROGRESS_AT, _ACTIVE_ROUTE_SOURCE

    systems_raw = _extract_route_systems(route)
    raw_list: list[str] = []
    norm_list: list[str] = []
    for sys_name in systems_raw:
        raw = str(sys_name).strip()
        if not raw:
            continue
        norm = normalize_system_name(raw)
        if not norm:
            continue
        raw_list.append(raw)
        norm_list.append(norm)

    _ACTIVE_ROUTE_SYSTEMS_RAW = raw_list
    _ACTIVE_ROUTE_SYSTEMS = norm_list
    _ACTIVE_ROUTE_SIG = sig
    _ACTIVE_ROUTE_TEXT = text or ""
    _ACTIVE_ROUTE_INDEX = 0
    _ACTIVE_ROUTE_CURRENT_SYSTEM = None
    _ACTIVE_ROUTE_LAST_COPIED_SYSTEM = None
    _ACTIVE_ROUTE_LAST_PROGRESS_AT = None
    _ACTIVE_ROUTE_SOURCE = source


def get_active_route_next_system() -> str | None:
    if not _ACTIVE_ROUTE_SYSTEMS_RAW:
        return None
    if _ACTIVE_ROUTE_INDEX < 0:
        return _ACTIVE_ROUTE_SYSTEMS_RAW[0]
    if _ACTIVE_ROUTE_INDEX >= len(_ACTIVE_ROUTE_SYSTEMS_RAW):
        return None
    return _ACTIVE_ROUTE_SYSTEMS_RAW[_ACTIVE_ROUTE_INDEX]


def register_active_route_list(
    listbox,
    data,
    *,
    numerate: bool = True,
    offset: int = 0,
    schema_id: str | None = None,
    rows: list[dict] | None = None,
) -> None:
    global _ACTIVE_ROUTE_LISTBOX, _ACTIVE_ROUTE_LIST_DATA
    global _ACTIVE_ROUTE_LIST_NUMERATE, _ACTIVE_ROUTE_LIST_OFFSET
    global _ACTIVE_ROUTE_TABLE_SCHEMA, _ACTIVE_ROUTE_TABLE_ROWS, _ACTIVE_ROUTE_TABLE_VISIBLE
    _ACTIVE_ROUTE_LISTBOX = listbox
    if (
        schema_id
        and rows is not None
        and config.get("features.tables.spansh_schema_enabled", True)
        and config.get("features.tables.schema_renderer_enabled", True)
    ):
        _ACTIVE_ROUTE_TABLE_SCHEMA = schema_id
        _ACTIVE_ROUTE_TABLE_ROWS = list(rows)
        _ACTIVE_ROUTE_TABLE_VISIBLE = _get_visible_columns(schema_id)
        _ACTIVE_ROUTE_LIST_DATA = render_table_lines(schema_id, _ACTIVE_ROUTE_TABLE_ROWS)
        _ACTIVE_ROUTE_LIST_NUMERATE = False
        _ACTIVE_ROUTE_LIST_OFFSET = 1
    else:
        _ACTIVE_ROUTE_TABLE_SCHEMA = None
        _ACTIVE_ROUTE_TABLE_ROWS = []
        _ACTIVE_ROUTE_TABLE_VISIBLE = None
        _ACTIVE_ROUTE_LIST_DATA = list(data) if data else []
        _ACTIVE_ROUTE_LIST_NUMERATE = bool(numerate)
        try:
            _ACTIVE_ROUTE_LIST_OFFSET = int(offset)
        except Exception:
            _ACTIVE_ROUTE_LIST_OFFSET = 0
    config.STATE["copied_idx"] = None


def _update_active_route_list_mark(route_index: int | None) -> None:
    global _ACTIVE_ROUTE_LIST_DATA
    global _ACTIVE_ROUTE_TABLE_SCHEMA, _ACTIVE_ROUTE_TABLE_ROWS
    if _ACTIVE_ROUTE_LISTBOX is None or not _ACTIVE_ROUTE_LIST_DATA:
        return
    if route_index is None:
        config.STATE["copied_idx"] = None
        return
    if _ACTIVE_ROUTE_TABLE_SCHEMA and _ACTIVE_ROUTE_TABLE_ROWS:
        for row in _ACTIVE_ROUTE_TABLE_ROWS:
            meta = row.get("_meta")
            if isinstance(meta, dict):
                meta.pop("badges", None)
        if 0 <= route_index < len(_ACTIVE_ROUTE_TABLE_ROWS):
            meta = _ACTIVE_ROUTE_TABLE_ROWS[route_index].setdefault("_meta", {})
            if isinstance(meta, dict):
                meta["badges"] = ["COPIED"]
        _ACTIVE_ROUTE_LIST_DATA = render_table_lines(
            _ACTIVE_ROUTE_TABLE_SCHEMA, _ACTIVE_ROUTE_TABLE_ROWS
        )
        try:
            wypelnij_liste(
                _ACTIVE_ROUTE_LISTBOX,
                _ACTIVE_ROUTE_LIST_DATA,
                copied_index=None,
                numerate=False,
                show_copied_suffix=False,
            )
        except Exception:
            pass
        return
    list_index = route_index + _ACTIVE_ROUTE_LIST_OFFSET
    config.STATE["copied_idx"] = list_index
    try:
        wypelnij_liste(
            _ACTIVE_ROUTE_LISTBOX,
            _ACTIVE_ROUTE_LIST_DATA,
            copied_index=list_index,
            numerate=_ACTIVE_ROUTE_LIST_NUMERATE,
            show_copied_suffix=True,
        )
    except Exception:
        pass


def _emit_next_hop_status(level: str, code: str, text: str, *, source: str | None) -> None:
    if not utils.DEBOUNCER.is_allowed(code, cooldown_sec=2.0, context=source or ""):
        return
    emit_status(level, code, text, source=source, notify_overlay=True)


def _copy_next_hop_at_index(
    next_index: int, *, source: str | None, advance_index: bool, allow_duplicate: bool = False
) -> bool:
    global _ACTIVE_ROUTE_INDEX, _ACTIVE_ROUTE_LAST_COPIED_SYSTEM, _ACTIVE_ROUTE_LAST_PROGRESS_AT

    if next_index < 0 or next_index >= len(_ACTIVE_ROUTE_SYSTEMS_RAW):
        _emit_next_hop_status("WARN", "NEXT_HOP_EMPTY", STATUS_TEXTS["NEXT_HOP_EMPTY"], source=source)
        return False

    next_system = _ACTIVE_ROUTE_SYSTEMS_RAW[next_index]
    next_norm = _ACTIVE_ROUTE_SYSTEMS[next_index]
    last_norm = normalize_system_name(_ACTIVE_ROUTE_LAST_COPIED_SYSTEM)
    if not allow_duplicate and next_norm and last_norm and next_norm == last_norm:
        return False

    result = try_copy_to_clipboard(next_system, context=source or "next_hop")
    if result.get("ok"):
        _ACTIVE_ROUTE_LAST_COPIED_SYSTEM = next_system
        _ACTIVE_ROUTE_LAST_PROGRESS_AT = time.time()
        if advance_index:
            _ACTIVE_ROUTE_INDEX = next_index + 1
        else:
            _ACTIVE_ROUTE_INDEX = next_index
        _update_active_route_list_mark(next_index)
        _emit_next_hop_status(
            "OK",
            "NEXT_HOP_COPIED",
            f"Skopiowano nastepny system: {next_system}",
            source=source,
        )
        return True

    _emit_next_hop_status("WARN", "CLIPBOARD_FAIL", STATUS_TEXTS["CLIPBOARD_FAIL"], source=source)
    err = result.get("error")
    if err:
        utils.MSG_QUEUE.put(("log", f"[AUTO-SCHOWEK] Clipboard error: {err}"))
    return False


def copy_next_hop_manual(source: str | None = None) -> bool:
    if not config.get("features.clipboard.next_hop_stepper", True):
        return False
    if not config.get("auto_clipboard_next_hop_allow_manual_advance", True):
        return False
    if not _ACTIVE_ROUTE_SYSTEMS_RAW:
        _emit_next_hop_status("WARN", "NEXT_HOP_EMPTY", STATUS_TEXTS["NEXT_HOP_EMPTY"], source=source)
        return False
    if _ACTIVE_ROUTE_INDEX >= len(_ACTIVE_ROUTE_SYSTEMS_RAW):
        _emit_next_hop_status("OK", "ROUTE_COMPLETE", STATUS_TEXTS["ROUTE_COMPLETE"], source=source)
        return False
    return _copy_next_hop_at_index(_ACTIVE_ROUTE_INDEX, source=source, advance_index=True, allow_duplicate=True)


def update_next_hop_on_system(current_system: str | None, trigger: str, source: str | None = None) -> None:
    global _ACTIVE_ROUTE_CURRENT_SYSTEM, _ACTIVE_ROUTE_LAST_PROGRESS_AT, _ACTIVE_ROUTE_INDEX

    mode = str(config.get("auto_clipboard_mode", "FULL_ROUTE")).strip().upper()
    if mode != "NEXT_HOP":
        return
    if not config.get("features.clipboard.next_hop_stepper", True):
        return

    trigger_mode = str(config.get("auto_clipboard_next_hop_trigger", "fsdjump")).strip().lower()
    if trigger_mode not in ("fsdjump", "location", "both"):
        trigger_mode = "fsdjump"
    if trigger_mode != "both" and trigger_mode != trigger:
        return

    if not current_system:
        return

    current_norm = normalize_system_name(current_system)
    if not current_norm:
        return

    _ACTIVE_ROUTE_CURRENT_SYSTEM = current_norm
    _ACTIVE_ROUTE_LAST_PROGRESS_AT = time.time()

    if not _ACTIVE_ROUTE_SYSTEMS:
        return

    policy = str(config.get("auto_clipboard_next_hop_resync_policy", "nearest_forward")).strip().lower()
    if policy not in ("nearest_forward", "strict"):
        policy = "nearest_forward"

    pos = None
    if policy == "nearest_forward":
        start_idx = max(_ACTIVE_ROUTE_INDEX, 0)
        for idx in range(start_idx, len(_ACTIVE_ROUTE_SYSTEMS)):
            if _ACTIVE_ROUTE_SYSTEMS[idx] == current_norm:
                pos = idx
                break
    else:
        try:
            pos = _ACTIVE_ROUTE_SYSTEMS.index(current_norm)
        except ValueError:
            pos = None

    if pos is None:
        _emit_next_hop_status("WARN", "ROUTE_DESYNC", STATUS_TEXTS["ROUTE_DESYNC"], source=source)
        return

    next_index = pos + 1
    if next_index >= len(_ACTIVE_ROUTE_SYSTEMS_RAW):
        _ACTIVE_ROUTE_INDEX = len(_ACTIVE_ROUTE_SYSTEMS_RAW)
        _emit_next_hop_status("OK", "ROUTE_COMPLETE", STATUS_TEXTS["ROUTE_COMPLETE"], source=source)
        return

    _ACTIVE_ROUTE_INDEX = next_index
    if not config.get("auto_clipboard", True):
        if config.get("debug_next_hop", False):
            emit_status("INFO", "AUTO_CLIPBOARD_OFF", source=source, notify_overlay=False)
        return

    _copy_next_hop_at_index(next_index, source=source, advance_index=False)


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


def handle_route_ready_autoclipboard(
    owner, route, *, status_target, debounce_sec=1.5, source: str | None = None
):
    text = format_route_for_clipboard(route)
    sig = compute_route_signature(route)
    set_last_route_data(route, text, sig)
    _set_active_route_data(route, text, sig, source or status_target)

    mode = str(config.get("auto_clipboard_mode", "FULL_ROUTE")).strip().upper()
    if mode == "NEXT_HOP":
        if config.get("debug_next_hop", False):
            emit_status(
                "INFO",
                "AUTO_CLIPBOARD_MODE_NEXT_HOP",
                source=f"spansh.{status_target}",
                notify_overlay=False,
            )
        if not config.get("auto_clipboard_next_hop_copy_on_route_ready", False):
            return
        if not config.get("auto_clipboard", True):
            emit_status(
                "INFO",
                "AUTO_CLIPBOARD_OFF",
                source=f"spansh.{status_target}",
                notify_overlay=False,
            )
            return
        next_index = 0
        try:
            from app.state import app_state  # type: ignore

            current_system = getattr(app_state, "current_system", None)
        except Exception:
            current_system = None

        if current_system:
            current_norm = normalize_system_name(current_system)
            if current_norm in _ACTIVE_ROUTE_SYSTEMS:
                pos = _ACTIVE_ROUTE_SYSTEMS.index(current_norm)
                next_index = pos + 1

        if next_index >= len(_ACTIVE_ROUTE_SYSTEMS_RAW):
            _ACTIVE_ROUTE_INDEX = len(_ACTIVE_ROUTE_SYSTEMS_RAW)
            _emit_next_hop_status("OK", "ROUTE_COMPLETE", STATUS_TEXTS["ROUTE_COMPLETE"], source=source)
            return

        _ACTIVE_ROUTE_INDEX = next_index
        _copy_next_hop_at_index(next_index, source=f"spansh.{status_target}", advance_index=False)
        return

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

        result = try_copy_to_clipboard(text, context=f"full_route.{status_target}")
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
