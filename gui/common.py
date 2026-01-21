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

    header_bar = ttk.Frame(frame)
    header_bar.pack(side="top", fill="x")
    header_label = ttk.Label(
        header_bar,
        text="",
        font=("Consolas", 10, "bold"),
        anchor="w",
    )

    list_frame = ttk.Frame(frame)
    list_frame.pack(side="top", fill="both", expand=True)

    sc = ttk.Scrollbar(list_frame)
    sc.pack(side="right", fill="y")

    lb = tk.Listbox(
        list_frame,
        yscrollcommand=sc.set,
        font=("Consolas", 10),
        activestyle="none",
        selectmode="browse",
        exportselection=False
    )
    lb.pack(side="left", fill="both", expand=True)

    sc.config(command=lb.yview)
    columns_button = ttk.Button(
        header_bar,
        text="⚙ Kolumny",
        command=lambda: _open_columns_picker(lb),
    )
    if config.get("features.tables.column_picker_enabled", False):
        columns_button.pack(side="right", padx=4, pady=(2, 2))
    lb._renata_header_label = header_label  # type: ignore[attr-defined]
    lb._renata_list_frame = list_frame  # type: ignore[attr-defined]
    lb._renata_header_bar = header_bar  # type: ignore[attr-defined]
    lb._renata_columns_button = columns_button  # type: ignore[attr-defined]
    lb._renata_table_schema = None  # type: ignore[attr-defined]
    lb._renata_table_rows = []  # type: ignore[attr-defined]
    return lb


def stworz_tabele_trasy(parent, title="Plan Lotu"):
    frame = ttk.LabelFrame(parent, text=title)
    frame.pack(side="top", fill="both", expand=True, padx=8, pady=8)

    header_bar = ttk.Frame(frame)
    header_bar.pack(side="top", fill="x")

    columns_button = ttk.Button(
        header_bar,
        text="⚙ Kolumny",
        command=lambda: _open_columns_picker(tree),
    )
    if config.get("features.tables.column_picker_enabled", False):
        columns_button.pack(side="right", padx=4, pady=(2, 2))

    tree_frame = ttk.Frame(frame)
    tree_frame.pack(side="top", fill="both", expand=True)

    sc = ttk.Scrollbar(tree_frame)
    sc.pack(side="right", fill="y")

    tree = ttk.Treeview(
        tree_frame,
        columns=(),
        show="headings",
        selectmode="browse",
    )
    tree.pack(side="left", fill="both", expand=True)
    sc.config(command=tree.yview)
    tree.configure(yscrollcommand=sc.set)

    tree._renata_header_bar = header_bar  # type: ignore[attr-defined]
    tree._renata_columns_button = columns_button  # type: ignore[attr-defined]
    tree._renata_table_schema = None  # type: ignore[attr-defined]
    tree._renata_table_rows = []  # type: ignore[attr-defined]
    tree._renata_tree_rows_by_iid = {}  # type: ignore[attr-defined]
    tree._renata_tree_sort = {"column": None, "desc": False}  # type: ignore[attr-defined]
    return tree


def _set_list_header(listbox, text: str | None) -> None:
    label = getattr(listbox, "_renata_header_label", None)
    if label is None:
        return
    if text:
        label.config(text=text)
        if not label.winfo_ismapped():
            label.pack(side="left", fill="x", expand=True, padx=(4, 0))
    else:
        label.config(text="")
        if label.winfo_ismapped():
            label.pack_forget()


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
    visible = []
    visible_cfg = config.get("tables_visible_columns", {})
    if isinstance(visible_cfg, dict):
        visible = visible_cfg.get(schema_id) or []
    if not visible:
        tables_cfg = config.get("tables", {})
        if isinstance(tables_cfg, dict):
            schema_cfg = tables_cfg.get(schema_id)
            if isinstance(schema_cfg, dict):
                candidate = schema_cfg.get("visible_columns") or []
                if isinstance(candidate, list):
                    visible = candidate
    if not isinstance(visible, list) or not visible:
        visible = [col.key for col in schema.columns if col.default_visible]
    if len(visible) < 2:
        visible = [col.key for col in schema.columns[:2]]
    return _sanitize_visible_columns(schema, visible)


def _compute_column_widths(columns: list, rows: list[dict], max_rows: int = 25) -> dict:
    widths = {}
    for col in columns:
        label = col.label or ""
        widths[col.key] = max(len(label), col.width or 0)

    for row in rows[:max_rows]:
        for col in columns:
            value = _get_value_by_key(row, col.value_path or col.key)
            text = format_value(value, col.fmt)
            current = widths.get(col.key, 0)
            widths[col.key] = max(current, len(text))
    return widths


def render_table(schema_id: str, rows: list[dict]) -> tuple[str, list[str]]:
    if not config.get("features.tables.spansh_schema_enabled", True):
        return "", []
    if not config.get("features.tables.schema_renderer_enabled", True):
        return "", []
    try:
        from gui import table_schemas
    except Exception:
        return "", []
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return "", []

    visible_cols = _get_visible_columns(schema_id)
    columns = [col for col in schema.columns if col.key in visible_cols]
    if not columns:
        return "", []

    widths = _compute_column_widths(columns, rows)
    header = "  ".join(
        _align_text(col.label, widths.get(col.key), col.align) for col in columns
    )
    lines = []

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
            parts.append(_align_text(text, widths.get(col.key), col.align))
        lines.append("  ".join(parts))

    return header, lines


def _ensure_route_indices(rows: list[dict]) -> None:
    for idx, row in enumerate(rows):
        if isinstance(row, dict) and "_route_index" not in row:
            row["_route_index"] = idx


def render_table_treeview(tree, schema_id: str, rows: list[dict]) -> None:
    try:
        from gui import table_schemas
    except Exception:
        return
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return

    _ensure_route_indices(rows)
    visible_cols = _get_visible_columns(schema_id)
    columns = [col for col in schema.columns if col.key in visible_cols]
    if not columns:
        columns = list(schema.columns)

    lp_key = "__lp__"
    tree["columns"] = [lp_key] + [col.key for col in columns]
    tree["show"] = "headings"

    widths = _compute_column_widths(columns, rows)
    tree.column(lp_key, width=40, anchor="e", stretch=False)
    tree.heading(
        lp_key,
        text="LP",
        command=lambda key=lp_key: _sort_treeview(tree, schema_id, key),
    )
    for col in columns:
        width_px = max(60, int(widths.get(col.key, 8) * 8))
        anchor = "w"
        if col.align == "right":
            anchor = "e"
        elif col.align == "center":
            anchor = "center"
        tree.column(col.key, width=width_px, anchor=anchor, stretch=True)
        tree.heading(
            col.key,
            text=col.label,
            command=lambda key=col.key: _sort_treeview(tree, schema_id, key),
        )

    tree.delete(*tree.get_children())
    rows_by_iid = {}
    for idx, row in enumerate(rows):
        iid = str(idx)
        values = [str(idx + 1)]
        for col in columns:
            value = _get_value_by_key(row, col.value_path or col.key)
            values.append(format_value(value, col.fmt))
        tree.insert("", "end", iid=iid, values=values)
        rows_by_iid[iid] = row
    tree._renata_table_schema = schema_id  # type: ignore[attr-defined]
    tree._renata_table_rows = list(rows)  # type: ignore[attr-defined]
    tree._renata_tree_rows_by_iid = rows_by_iid  # type: ignore[attr-defined]
    tree.tag_configure("copied", background=COPIED_BG, foreground=COPIED_FG)
    _update_treeview_sort_indicators(tree, schema_id)


def _sort_key_for_value(value):
    if value is None:
        return (1, "")
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    try:
        number = float(str(value).replace(" ", "").replace(",", ""))
        return (0, number)
    except Exception:
        return (0, str(value).casefold())


def _sort_treeview(tree, schema_id: str, col_key: str) -> None:
    try:
        from gui import table_schemas
    except Exception:
        return
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return
    lp_key = "__lp__"
    if col_key == lp_key:
        tree._renata_tree_sort = {"column": lp_key, "desc": False}  # type: ignore[attr-defined]
        rows_by_iid = getattr(tree, "_renata_tree_rows_by_iid", {})
        items = []
        for iid, row in rows_by_iid.items():
            route_index = row.get("_route_index", 0)
            items.append((iid, route_index))
        items.sort(key=lambda item: item[1])
        for idx, (iid, _) in enumerate(items):
            tree.move(iid, "", idx)
        _update_treeview_lp(tree)
        _update_treeview_sort_indicators(tree, schema_id)
        return

    col = next((c for c in schema.columns if c.key == col_key), None)
    if col is None:
        return

    sort_state = getattr(tree, "_renata_tree_sort", {"column": None, "desc": False})
    desc = False
    if sort_state.get("column") == col_key:
        desc = not bool(sort_state.get("desc"))
    sort_state = {"column": col_key, "desc": desc}
    tree._renata_tree_sort = sort_state  # type: ignore[attr-defined]

    rows_by_iid = getattr(tree, "_renata_tree_rows_by_iid", {})
    items = []
    for iid, row in rows_by_iid.items():
        value = _get_value_by_key(row, col.value_path or col.key)
        items.append((iid, _sort_key_for_value(value)))
    items.sort(key=lambda item: item[1], reverse=desc)
    for idx, (iid, _) in enumerate(items):
        tree.move(iid, "", idx)
    _update_treeview_lp(tree)
    _update_treeview_sort_indicators(tree, schema_id)


def _update_treeview_lp(tree) -> None:
    for idx, iid in enumerate(tree.get_children()):
        values = list(tree.item(iid, "values") or [])
        if not values:
            values = [str(idx + 1)]
        else:
            values[0] = str(idx + 1)
        tree.item(iid, values=values)


def _update_treeview_sort_indicators(tree, schema_id: str) -> None:
    try:
        from gui import table_schemas
    except Exception:
        return
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return
    sort_state = getattr(tree, "_renata_tree_sort", {"column": None, "desc": False})
    active = sort_state.get("column")
    desc = bool(sort_state.get("desc"))

    lp_key = "__lp__"
    arrow = " ▼" if desc else " ▲"
    tree.heading(
        lp_key,
        text="LP" + (arrow if active == lp_key else ""),
        command=lambda key=lp_key: _sort_treeview(tree, schema_id, key),
    )
    for col in schema.columns:
        label = col.label
        if col.key == active:
            label = f"{label}{arrow}"
        tree.heading(
            col.key,
            text=label,
            command=lambda key=col.key: _sort_treeview(tree, schema_id, key),
        )


def _get_treeview_row(tree, row_id: str) -> dict | None:
    rows_by_iid = getattr(tree, "_renata_tree_rows_by_iid", {})
    return rows_by_iid.get(row_id)


def render_table_lines(schema_id: str, rows: list[dict]) -> list[str]:
    _header, lines = render_table(schema_id, rows)
    return lines


def _escape_delimited_value(value: str, sep: str) -> str:
    text = "" if value is None else str(value)
    if "\"" in text:
        text = text.replace("\"", "\"\"")
    if sep in text or "\n" in text or "\r" in text:
        return f"\"{text}\""
    return text


def format_row_delimited(schema_id: str, row: dict, sep: str) -> str:
    try:
        from gui import table_schemas
    except Exception:
        return ""
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return ""
    visible_cols = _get_visible_columns(schema_id)
    columns = [col for col in schema.columns if col.key in visible_cols]
    values = []
    for col in columns:
        value = _get_value_by_key(row, col.value_path or col.key)
        text = format_value(value, col.fmt)
        values.append(_escape_delimited_value(text, sep))
    return sep.join(values)


def copy_text_to_clipboard(text: str, *, context: str = "context_menu") -> bool:
    if not text:
        return False
    result = try_copy_to_clipboard(text, context=context)
    return bool(result.get("ok"))


def _get_default_visible_columns(schema) -> list[str]:
    defaults = [col.key for col in schema.columns if col.default_visible]
    if not defaults and schema.columns:
        defaults = [schema.columns[0].key]
    return defaults


def _sanitize_visible_columns(schema, visible: list[str]) -> list[str]:
    keys = {col.key for col in schema.columns}
    return [key for key in visible if key in keys]


def _get_saved_visible_columns(schema_id: str) -> list[str] | None:
    cfg = config.get("tables_visible_columns", {})
    if not isinstance(cfg, dict):
        cfg = {}
    visible = cfg.get(schema_id)
    if not visible:
        tables_cfg = config.get("tables", {})
        if isinstance(tables_cfg, dict):
            schema_cfg = tables_cfg.get(schema_id)
            if isinstance(schema_cfg, dict):
                visible = schema_cfg.get("visible_columns")
    if isinstance(visible, list):
        return [str(item) for item in visible if str(item)]
    return None


def _save_visible_columns(schema_id: str, visible: list[str]) -> None:
    cfg = config.get("tables_visible_columns", {})
    if not isinstance(cfg, dict):
        cfg = {}
    new_cfg = dict(cfg)
    new_cfg[schema_id] = list(visible)
    tables_cfg = config.get("tables", {})
    if not isinstance(tables_cfg, dict):
        tables_cfg = {}
    new_tables = dict(tables_cfg)
    new_tables[schema_id] = {"visible_columns": list(visible)}
    try:
        config.save({"tables_visible_columns": new_cfg, "tables": new_tables})
    except Exception:
        pass


def _refresh_table_listbox(listbox) -> None:
    schema_id = getattr(listbox, "_renata_table_schema", None)
    rows = getattr(listbox, "_renata_table_rows", None)
    if not schema_id or rows is None:
        return
    header, lines = render_table(schema_id, rows)
    try:
        wypelnij_liste(
            listbox,
            lines,
            copied_index=None,
            numerate=False,
            show_copied_suffix=False,
        )
    except Exception:
        pass
    _set_list_header(listbox, header)
    if listbox is _ACTIVE_ROUTE_LISTBOX and schema_id == _ACTIVE_ROUTE_TABLE_SCHEMA:
        globals()["_ACTIVE_ROUTE_TABLE_VISIBLE"] = _get_visible_columns(schema_id)
        globals()["_ACTIVE_ROUTE_LIST_DATA"] = list(lines)


def _refresh_table_treeview(tree) -> None:
    schema_id = getattr(tree, "_renata_table_schema", None)
    rows = getattr(tree, "_renata_table_rows", None)
    if not schema_id or rows is None:
        return
    render_table_treeview(tree, schema_id, list(rows))


def _open_columns_picker(listbox) -> None:
    if not config.get("features.tables.column_picker_enabled", False):
        return
    schema_id = getattr(listbox, "_renata_table_schema", None)
    if not schema_id:
        return
    try:
        from gui import table_schemas
    except Exception:
        return
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return

    existing = getattr(listbox, "_renata_columns_dialog", None)
    try:
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return
    except Exception:
        listbox._renata_columns_dialog = None  # type: ignore[attr-defined]

    dialog = tk.Toplevel(listbox)
    listbox._renata_columns_dialog = dialog  # type: ignore[attr-defined]
    dialog.title(f"Kolumny: {schema.title}")
    dialog.resizable(False, False)
    dialog.transient(listbox.winfo_toplevel())

    visible = _get_saved_visible_columns(schema_id)
    if visible is None:
        visible = _get_default_visible_columns(schema)
    visible = _sanitize_visible_columns(schema, visible)
    if not visible:
        visible = _get_default_visible_columns(schema)

    vars_map: dict[str, tk.BooleanVar] = {}
    updating = {"value": False}

    def _apply_selection() -> None:
        if updating["value"]:
            return
        selected = [col.key for col in schema.columns if vars_map[col.key].get()]
        if not selected:
            updating["value"] = True
            selected = _get_default_visible_columns(schema)
            for col in schema.columns:
                vars_map[col.key].set(col.key in selected)
            updating["value"] = False
        selected = _sanitize_visible_columns(schema, selected)
        if not selected:
            return
        _save_visible_columns(schema_id, selected)
        if isinstance(listbox, ttk.Treeview):
            _refresh_table_treeview(listbox)
        else:
            _refresh_table_listbox(listbox)

    for col in schema.columns:
        var = tk.BooleanVar(value=col.key in visible)
        vars_map[col.key] = var
        ttk.Checkbutton(
            dialog,
            text=col.label,
            variable=var,
            command=_apply_selection,
        ).pack(anchor="w", padx=10, pady=2)

    ttk.Label(
        dialog,
        text="Zmiany sa natychmiastowe.",
        foreground="#888888",
    ).pack(anchor="w", padx=10, pady=(6, 8))


def _escape_delimited_value(value: str, sep: str) -> str:
    text = "" if value is None else str(value)
    if "\"" in text:
        text = text.replace("\"", "\"\"")
    if sep in text or "\n" in text or "\r" in text:
        return f"\"{text}\""
    return text


def format_row_delimited(schema_id: str, row: dict, sep: str) -> str:
    try:
        from gui import table_schemas
    except Exception:
        return ""
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return ""
    visible_cols = _get_visible_columns(schema_id)
    columns = [col for col in schema.columns if col.key in visible_cols]
    values = []
    for col in columns:
        value = _get_value_by_key(row, col.value_path or col.key)
        text = format_value(value, col.fmt)
        values.append(_escape_delimited_value(text, sep))
    return sep.join(values)


def copy_text_to_clipboard(text: str, *, context: str = "context_menu") -> bool:
    if not text:
        return False
    result = try_copy_to_clipboard(text, context=context)
    return bool(result.get("ok"))


def attach_results_context_menu(
    widget,
    get_row_payload,
    actions_provider,
    *,
    flag_key: str = "features.ui.results_context_menu",
) -> None:
    if getattr(widget, "_renata_ctx_menu_bound", False):
        return
    widget._renata_ctx_menu_bound = True  # type: ignore[attr-defined]

    def _get_payload(row_id, row_text):
        try:
            return get_row_payload(row_id, row_text)
        except TypeError:
            return get_row_payload(row_id)

    def _on_context_menu(event):
        if not config.get(flag_key, False):
            return
        row_id = None
        row_text = None
        if isinstance(widget, ttk.Treeview):
            row_id = widget.identify_row(event.y)
            if not row_id:
                return
            try:
                widget.selection_set(row_id)
            except Exception:
                pass
            try:
                row_text = " ".join(str(v) for v in widget.item(row_id, "values") or [])
            except Exception:
                row_text = None
            if not row_text:
                row = _get_treeview_row(widget, row_id)
                if isinstance(row, dict):
                    row_text = " ".join(str(v) for v in row.values() if v is not None)
        else:
            try:
                row_id = widget.nearest(event.y)
            except Exception:
                return
            if row_id is None:
                return
            try:
                if row_id < 0 or row_id >= widget.size():
                    return
            except Exception:
                return
            try:
                widget.selection_clear(0, tk.END)
                widget.selection_set(row_id)
                widget.activate(row_id)
            except Exception:
                pass
            try:
                row_text = widget.get(row_id)
            except Exception:
                row_text = None

        payload = _get_payload(row_id, row_text)
        if not payload:
            return
        actions = actions_provider(payload) or []
        if not actions:
            return
        menu = getattr(widget, "_renata_ctx_menu", None)
        if menu is None:
            menu = tk.Menu(widget, tearoff=0)
            widget._renata_ctx_menu = menu  # type: ignore[attr-defined]
        menu.delete(0, tk.END)
        has_action = False
        for item in actions:
            if not item:
                continue
            if item.get("separator"):
                menu.add_separator()
                continue
            label = item.get("label")
            action = item.get("action")
            if not label or not callable(action):
                continue
            enabled = item.get("enabled", True)
            menu.add_command(
                label=label,
                command=lambda fn=action: fn(payload),
                state=("normal" if enabled else "disabled"),
            )
            has_action = True
        if not has_action:
            return
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    widget.bind("<Button-3>", _on_context_menu)


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
