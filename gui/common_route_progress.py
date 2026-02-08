import time
import threading
from tkinter import ttk
import config
from logic import utils
from gui.common_clipboard import (
    compute_route_signature,
    format_route_for_clipboard,
    try_copy_to_clipboard,
)
from gui.common_tables import (
    _get_visible_columns,
    _set_list_header,
    render_table,
    set_listbox_refresh_observer,
    wypelnij_liste,
)

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
_ACTIVE_ROUTE_DESYNC_STRIKES: int = 0
_ACTIVE_ROUTE_DESYNC_ACTIVE: bool = False
_ACTIVE_MILESTONE_TARGET_NORM: str | None = None
_ACTIVE_MILESTONE_TARGET_RAW: str | None = None
_ACTIVE_MILESTONE_TARGET_INDEX: int | None = None
_ACTIVE_MILESTONE_START_INDEX: int = 0
_ACTIVE_MILESTONE_ANNOUNCED: set[int] = set()
_ACTIVE_MILESTONE_START_REMAINING: int | None = None
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
    "JR_COMPUTE_FAIL": "Jump range: blad obliczen.",
    "JR_VALIDATE_OK": "Jump range: walidacja OK.",
    "JR_VALIDATE_DELTA": "Jump range: odchylka od gry.",
    "JR_ENGINEERING_APPLIED": "Jump range: zastosowano engineering.",
    "JR_NOT_READY_FALLBACK": "Jump range: brak danych, uzywam fallback.",
    "AUTO_CLIPBOARD_OFF": "Auto-schowek wyłączony.",
}


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

def _level_color(level: str) -> str:
    colors = {
        "OK": "green",
        "INFO": "grey",
        "WARN": "orange",
        "ERROR": "red",
        "BUSY": "grey",
    }
    return colors.get(level, "grey")


def _status_log_line(level: str, code: str, text: str, source: str | None) -> str:
    src = str(source or "unspecified").strip() or "unspecified"
    return f"[{level}] {code} ({src}): {text}"

def _set_active_route_data(route, text, sig, source: str | None) -> None:
    global _ACTIVE_ROUTE_SYSTEMS, _ACTIVE_ROUTE_SYSTEMS_RAW
    global _ACTIVE_ROUTE_SIG, _ACTIVE_ROUTE_TEXT, _ACTIVE_ROUTE_INDEX
    global _ACTIVE_ROUTE_CURRENT_SYSTEM, _ACTIVE_ROUTE_LAST_COPIED_SYSTEM
    global _ACTIVE_ROUTE_LAST_PROGRESS_AT, _ACTIVE_ROUTE_SOURCE
    global _ACTIVE_ROUTE_DESYNC_STRIKES, _ACTIVE_ROUTE_DESYNC_ACTIVE
    global _ACTIVE_MILESTONE_TARGET_NORM, _ACTIVE_MILESTONE_TARGET_RAW
    global _ACTIVE_MILESTONE_TARGET_INDEX, _ACTIVE_MILESTONE_START_INDEX
    global _ACTIVE_MILESTONE_ANNOUNCED, _ACTIVE_MILESTONE_START_REMAINING

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
    _ACTIVE_ROUTE_DESYNC_STRIKES = 0
    _ACTIVE_ROUTE_DESYNC_ACTIVE = False
    _ACTIVE_MILESTONE_TARGET_NORM = None
    _ACTIVE_MILESTONE_TARGET_RAW = None
    _ACTIVE_MILESTONE_TARGET_INDEX = None
    _ACTIVE_MILESTONE_START_INDEX = 0
    _ACTIVE_MILESTONE_ANNOUNCED = set()
    _ACTIVE_MILESTONE_START_REMAINING = None

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
        header, lines = render_table(schema_id, _ACTIVE_ROUTE_TABLE_ROWS)
        _ACTIVE_ROUTE_LIST_DATA = lines
        _ACTIVE_ROUTE_LIST_NUMERATE = False
        _ACTIVE_ROUTE_LIST_OFFSET = 0
        if not isinstance(listbox, ttk.Treeview):
            _set_list_header(listbox, header)
        listbox._renata_table_schema = schema_id  # type: ignore[attr-defined]
        listbox._renata_table_rows = list(rows)  # type: ignore[attr-defined]
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
        _set_list_header(listbox, None)
        listbox._renata_table_schema = None  # type: ignore[attr-defined]
        listbox._renata_table_rows = []  # type: ignore[attr-defined]
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
        if isinstance(_ACTIVE_ROUTE_LISTBOX, ttk.Treeview):
            for iid in _ACTIVE_ROUTE_LISTBOX.get_children():
                _ACTIVE_ROUTE_LISTBOX.item(iid, tags=())
            target = None
            for iid, row in getattr(_ACTIVE_ROUTE_LISTBOX, "_renata_tree_rows_by_iid", {}).items():
                if row.get("_route_index") == route_index:
                    target = iid
                    break
            if target is not None:
                _ACTIVE_ROUTE_LISTBOX.item(target, tags=("copied",))
                _ACTIVE_ROUTE_LISTBOX.selection_set(target)
                _ACTIVE_ROUTE_LISTBOX.see(target)
            return
        for row in _ACTIVE_ROUTE_TABLE_ROWS:
            meta = row.get("_meta")
            if isinstance(meta, dict):
                meta.pop("badges", None)
        if 0 <= route_index < len(_ACTIVE_ROUTE_TABLE_ROWS):
            meta = _ACTIVE_ROUTE_TABLE_ROWS[route_index].setdefault("_meta", {})
            if isinstance(meta, dict):
                meta["badges"] = ["COPIED"]
        header, lines = render_table(
            _ACTIVE_ROUTE_TABLE_SCHEMA, _ACTIVE_ROUTE_TABLE_ROWS
        )
        _ACTIVE_ROUTE_LIST_DATA = lines
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
        _set_list_header(_ACTIVE_ROUTE_LISTBOX, header)
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
    if code == "NEXT_HOP_COPIED":
        utils.powiedz(
            text,
            message_id="MSG.NEXT_HOP_COPIED",
            context={"system": _ACTIVE_ROUTE_LAST_COPIED_SYSTEM},
        )
    elif code == "ROUTE_COMPLETE":
        utils.powiedz(text, message_id="MSG.ROUTE_COMPLETE")
    elif code == "ROUTE_DESYNC":
        utils.powiedz(text, message_id="MSG.ROUTE_DESYNC")

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

def _get_navroute_context() -> tuple[str, set[str]]:
    try:
        from app.state import app_state  # type: ignore
    except Exception:
        return "", set()

    nav_route = getattr(app_state, "nav_route", None)
    if not isinstance(nav_route, dict):
        return "", set()

    systems_raw = nav_route.get("systems")
    systems_set: set[str] = set()
    if isinstance(systems_raw, list):
        for value in systems_raw:
            norm = normalize_system_name(value)
            if norm:
                systems_set.add(norm)

    endpoint = normalize_system_name(nav_route.get("endpoint"))
    if not endpoint and isinstance(systems_raw, list) and systems_raw:
        endpoint = normalize_system_name(systems_raw[-1])
    return endpoint, systems_set

def _get_navroute_ordered_systems() -> list[str]:
    try:
        from app.state import app_state  # type: ignore
    except Exception:
        return []

    nav_route = getattr(app_state, "nav_route", None)
    if not isinstance(nav_route, dict):
        return []

    systems_raw = nav_route.get("systems")
    if not isinstance(systems_raw, list):
        return []

    ordered: list[str] = []
    for value in systems_raw:
        norm = normalize_system_name(value)
        if not norm:
            continue
        if ordered and ordered[-1] == norm:
            continue
        ordered.append(norm)
    return ordered

def _get_navroute_remaining_to_target(current_norm: str, target_norm: str) -> int | None:
    if not current_norm or not target_norm:
        return None
    ordered = _get_navroute_ordered_systems()
    if not ordered:
        return None
    try:
        current_idx = ordered.index(current_norm)
    except ValueError:
        return None
    try:
        target_idx = ordered.index(target_norm, current_idx)
    except ValueError:
        return None
    return max(0, target_idx - current_idx)

def _get_active_spansh_milestone_norm() -> str:
    try:
        from app.state import app_state  # type: ignore
    except Exception:
        return ""

    milestone = None
    try:
        getter = getattr(app_state, "get_active_spansh_milestone", None)
        if callable(getter):
            milestone = getter()
    except Exception:
        milestone = None

    if not milestone:
        milestone = get_active_route_next_system()
    return normalize_system_name(milestone)

def _is_navroute_aligned_with_active_milestone(current_norm: str) -> bool:
    """
    Route symbiosis guard:
    if current system belongs to in-game NavRoute and its endpoint equals
    active Spansh milestone, do not treat this jump as desync.
    """
    endpoint_norm, nav_systems = _get_navroute_context()
    milestone_norm = _get_active_spansh_milestone_norm()
    if not endpoint_norm or not milestone_norm:
        return False
    if endpoint_norm != milestone_norm:
        return False
    return bool(current_norm and current_norm in nav_systems)

def _resolve_active_milestone(current_index: int) -> tuple[str, str, int] | None:
    raw_target = None
    try:
        from app.state import app_state  # type: ignore

        getter = getattr(app_state, "get_active_spansh_milestone", None)
        if callable(getter):
            raw_target = getter()
    except Exception:
        raw_target = None

    if not raw_target:
        raw_target = get_active_route_next_system()
    norm_target = normalize_system_name(raw_target)
    if not norm_target:
        return None

    # Prefer first matching occurrence at/after current route index.
    for idx in range(max(0, int(current_index)), len(_ACTIVE_ROUTE_SYSTEMS)):
        if _ACTIVE_ROUTE_SYSTEMS[idx] == norm_target:
            return norm_target, str(raw_target), idx

    # Fallback: any occurrence in route.
    for idx, norm_value in enumerate(_ACTIVE_ROUTE_SYSTEMS):
        if norm_value == norm_target:
            return norm_target, str(raw_target), idx
    return None

def _maybe_emit_milestone_progress(current_index: int, source: str | None) -> None:
    global _ACTIVE_MILESTONE_TARGET_NORM, _ACTIVE_MILESTONE_TARGET_RAW
    global _ACTIVE_MILESTONE_TARGET_INDEX, _ACTIVE_MILESTONE_START_INDEX
    global _ACTIVE_MILESTONE_ANNOUNCED, _ACTIVE_MILESTONE_START_REMAINING

    if not config.get("route_progress_speech", True):
        return
    if not _ACTIVE_ROUTE_SYSTEMS:
        return

    prev_target_norm = _ACTIVE_MILESTONE_TARGET_NORM
    prev_target_raw = _ACTIVE_MILESTONE_TARGET_RAW
    prev_target_index = _ACTIVE_MILESTONE_TARGET_INDEX

    resolved = _resolve_active_milestone(current_index)
    if not resolved:
        return
    target_norm, target_raw, target_index = resolved

    # If previous milestone has just been reached, emit a clear transition cue.
    if (
        prev_target_norm
        and prev_target_raw
        and prev_target_index is not None
        and current_index >= int(prev_target_index)
        and 100 not in _ACTIVE_MILESTONE_ANNOUNCED
    ):
        _ACTIVE_MILESTONE_ANNOUNCED.add(100)
        next_target = ""
        if target_norm != prev_target_norm:
            next_target = target_raw
        utils.powiedz(
            f"Cel odcinka osiagniety. {prev_target_raw}.",
            message_id="MSG.MILESTONE_REACHED",
            context={"target": prev_target_raw, "next_target": next_target, "source": source},
        )
        transition_text = f"Osiagnieto milestone: {prev_target_raw}"
        if next_target:
            transition_text += f" -> kolejny cel: {next_target}"
        emit_status(
            "INFO",
            "MILESTONE_REACHED",
            text=transition_text,
            source=source,
            notify_overlay=False,
        )

    # Reset per active milestone.
    if (
        _ACTIVE_MILESTONE_TARGET_NORM != target_norm
        or _ACTIVE_MILESTONE_TARGET_INDEX != target_index
        or _ACTIVE_MILESTONE_TARGET_RAW != target_raw
    ):
        _ACTIVE_MILESTONE_TARGET_NORM = target_norm
        _ACTIVE_MILESTONE_TARGET_RAW = target_raw
        _ACTIVE_MILESTONE_TARGET_INDEX = target_index
        _ACTIVE_MILESTONE_START_INDEX = max(0, int(current_index))
        _ACTIVE_MILESTONE_START_REMAINING = None
        _ACTIVE_MILESTONE_ANNOUNCED = set()

    if current_index < _ACTIVE_MILESTONE_START_INDEX:
        _ACTIVE_MILESTONE_START_INDEX = current_index
        _ACTIVE_MILESTONE_ANNOUNCED = set()

    start = _ACTIVE_MILESTONE_START_INDEX
    total = max(0, target_index - start)
    done = max(0, current_index - start)
    if total <= 0:
        progress = 100 if current_index >= target_index else 0
    else:
        progress = int((done * 100) / total)
    progress = max(0, min(100, progress))

    pending = [p for p in (25, 50, 75, 100) if p <= progress and p not in _ACTIVE_MILESTONE_ANNOUNCED]
    if not pending:
        return
    threshold = max(pending)
    _ACTIVE_MILESTONE_ANNOUNCED.add(threshold)

    if threshold >= 100:
        utils.powiedz(
            f"Cel odcinka osiagniety. {target_raw}.",
            message_id="MSG.MILESTONE_REACHED",
            context={"target": target_raw, "next_target": "", "source": source},
        )
        emit_status(
            "INFO",
            "MILESTONE_REACHED",
            text=f"Osiagnieto milestone: {target_raw}",
            source=source,
            notify_overlay=False,
        )
        return

    utils.powiedz(
        f"Do boosta. {threshold}% drogi.",
        message_id="MSG.MILESTONE_PROGRESS",
        context={"percent": threshold, "target": target_raw, "source": source},
    )
    emit_status(
        "INFO",
        "MILESTONE_PROGRESS",
        text=f"Progres do milestone {target_raw}: {threshold}%",
        source=source,
        notify_overlay=False,
    )

def _maybe_emit_milestone_progress_from_navroute(current_norm: str, source: str | None) -> None:
    global _ACTIVE_MILESTONE_TARGET_NORM, _ACTIVE_MILESTONE_TARGET_RAW
    global _ACTIVE_MILESTONE_TARGET_INDEX, _ACTIVE_MILESTONE_START_INDEX
    global _ACTIVE_MILESTONE_ANNOUNCED, _ACTIVE_MILESTONE_START_REMAINING

    if not config.get("route_progress_speech", True):
        return
    if not current_norm:
        return

    resolved = _resolve_active_milestone(_ACTIVE_ROUTE_INDEX)
    if not resolved:
        return
    target_norm, target_raw, target_index = resolved

    if (
        _ACTIVE_MILESTONE_TARGET_NORM != target_norm
        or _ACTIVE_MILESTONE_TARGET_INDEX != target_index
        or _ACTIVE_MILESTONE_TARGET_RAW != target_raw
    ):
        _ACTIVE_MILESTONE_TARGET_NORM = target_norm
        _ACTIVE_MILESTONE_TARGET_RAW = target_raw
        _ACTIVE_MILESTONE_TARGET_INDEX = target_index
        _ACTIVE_MILESTONE_START_INDEX = max(0, int(_ACTIVE_ROUTE_INDEX))
        _ACTIVE_MILESTONE_START_REMAINING = None
        _ACTIVE_MILESTONE_ANNOUNCED = set()

    remaining = _get_navroute_remaining_to_target(current_norm, target_norm)
    if remaining is None:
        return

    if _ACTIVE_MILESTONE_START_REMAINING is None:
        _ACTIVE_MILESTONE_START_REMAINING = max(remaining, 1)
    elif remaining > _ACTIVE_MILESTONE_START_REMAINING:
        # Route was replanned/extended; restart progress window for this milestone.
        _ACTIVE_MILESTONE_START_REMAINING = remaining
        _ACTIVE_MILESTONE_ANNOUNCED = set()

    total = max(1, int(_ACTIVE_MILESTONE_START_REMAINING))
    done = max(0, total - int(remaining))
    progress = int((done * 100) / total)
    progress = max(0, min(99, progress))

    pending = [p for p in (25, 50, 75) if p <= progress and p not in _ACTIVE_MILESTONE_ANNOUNCED]
    if not pending:
        return
    threshold = max(pending)
    _ACTIVE_MILESTONE_ANNOUNCED.add(threshold)

    utils.powiedz(
        f"Do boosta. {threshold}% drogi.",
        message_id="MSG.MILESTONE_PROGRESS",
        context={"percent": threshold, "target": target_raw, "source": source},
    )
    emit_status(
        "INFO",
        "MILESTONE_PROGRESS",
        text=f"Progres do milestone {target_raw}: {threshold}%",
        source=source,
        notify_overlay=False,
    )

def update_next_hop_on_system(current_system: str | None, trigger: str, source: str | None = None) -> None:
    global _ACTIVE_ROUTE_CURRENT_SYSTEM, _ACTIVE_ROUTE_LAST_PROGRESS_AT, _ACTIVE_ROUTE_INDEX
    global _ACTIVE_ROUTE_DESYNC_STRIKES, _ACTIVE_ROUTE_DESYNC_ACTIVE

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
        if _is_navroute_aligned_with_active_milestone(current_norm):
            _ACTIVE_ROUTE_DESYNC_STRIKES = 0
            _ACTIVE_ROUTE_DESYNC_ACTIVE = False
            _maybe_emit_milestone_progress_from_navroute(current_norm, source)
            if config.get("debug_next_hop", False):
                emit_status(
                    "INFO",
                    "ROUTE_ALIGNED_INGAME",
                    text="Trasa in-game zgodna z aktywnym milestone.",
                    source=source,
                    notify_overlay=False,
                )
            return

        try:
            confirm_jumps = int(config.get("auto_clipboard_next_hop_desync_confirm_jumps", 2))
        except Exception:
            confirm_jumps = 2
        if confirm_jumps < 1:
            confirm_jumps = 1

        _ACTIVE_ROUTE_DESYNC_STRIKES += 1
        if _ACTIVE_ROUTE_DESYNC_STRIKES < confirm_jumps:
            if config.get("debug_next_hop", False):
                emit_status(
                    "INFO",
                    "ROUTE_DESYNC_PENDING",
                    text=f"Poza trasa: {_ACTIVE_ROUTE_DESYNC_STRIKES}/{confirm_jumps}",
                    source=source,
                    notify_overlay=False,
                )
            return

        if not _ACTIVE_ROUTE_DESYNC_ACTIVE:
            _ACTIVE_ROUTE_DESYNC_ACTIVE = True
            _emit_next_hop_status("WARN", "ROUTE_DESYNC", STATUS_TEXTS["ROUTE_DESYNC"], source=source)
        return

    next_index = pos + 1
    _ACTIVE_ROUTE_DESYNC_STRIKES = 0
    _ACTIVE_ROUTE_DESYNC_ACTIVE = False
    if next_index >= len(_ACTIVE_ROUTE_SYSTEMS_RAW):
        _ACTIVE_ROUTE_INDEX = len(_ACTIVE_ROUTE_SYSTEMS_RAW)
        _emit_next_hop_status("OK", "ROUTE_COMPLETE", STATUS_TEXTS["ROUTE_COMPLETE"], source=source)
        return

    _ACTIVE_ROUTE_INDEX = next_index
    _maybe_emit_milestone_progress(pos, source)
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
    utils.MSG_QUEUE.put(("log", _status_log_line(level, code, text, source)))
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
    if utils.DEBOUNCER.is_allowed("tts_route_found", cooldown_sec=2.0, context=source or status_target):
        utils.powiedz("Trasa wyznaczona.", message_id="MSG.ROUTE_FOUND")

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

def _on_table_listbox_refreshed(listbox, schema_id: str, lines: list[str], visible_columns: list[str]) -> None:
    global _ACTIVE_ROUTE_TABLE_VISIBLE, _ACTIVE_ROUTE_LIST_DATA
    if listbox is _ACTIVE_ROUTE_LISTBOX and schema_id == _ACTIVE_ROUTE_TABLE_SCHEMA:
        _ACTIVE_ROUTE_TABLE_VISIBLE = list(visible_columns)
        _ACTIVE_ROUTE_LIST_DATA = list(lines)


set_listbox_refresh_observer(_on_table_listbox_refreshed)
