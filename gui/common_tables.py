import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import re
import config
from gui.window_positions import restore_window_geometry, bind_window_geometry, save_window_geometry



# --- delikatny, neutronowy kolor pod skopiowany wiersz
COPIED_BG = "#CFE8FF"   # jasny niebieski, subtelny
COPIED_FG = "#000000"
HOVER_BG = "#273241"


_LISTBOX_REFRESH_OBSERVER = None
_SYSTEM_COPY_FALLBACK = "brak nazwy systemu"


_SYSTEM_KEYS_BY_SCHEMA = {
    "trade": (
        "to_system",
        "from_system",
        "system_name",
        "system",
        "name",
    ),
    "neutron": (
        "system_name",
        "system",
        "name",
        "to_system",
        "from_system",
    ),
}


def _clean_system_candidate(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return " ".join(text.split())


def _extract_system_from_row_text(row_text: str | None) -> str:
    text = str(row_text or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\d+\.\s*", "", text)
    if "->" in text:
        text = text.split("->", 1)[1].strip()
    if re.search(r"\(\d+\s+cial\)\s*$", text):
        text = re.sub(r"\(\d+\s+cial\)\s*$", "", text).strip()
    return _clean_system_candidate(text)


def resolve_copy_system_value(
    schema_id: str,
    row: dict | None,
    row_text: str | None,
    *,
    fallback: str = _SYSTEM_COPY_FALLBACK,
) -> tuple[str, bool]:
    candidate_keys = _SYSTEM_KEYS_BY_SCHEMA.get(
        schema_id,
        (
            "system_name",
            "system",
            "name",
            "to_system",
            "from_system",
        ),
    )
    row_dict = row if isinstance(row, dict) else {}
    for key in candidate_keys:
        value = _clean_system_candidate(row_dict.get(key))
        if value:
            return value, True

    value = _extract_system_from_row_text(row_text)
    if value:
        return value, True
    return _clean_system_candidate(fallback), False


def set_listbox_refresh_observer(observer) -> None:
    global _LISTBOX_REFRESH_OBSERVER
    _LISTBOX_REFRESH_OBSERVER = observer

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
    lb._renata_state_container = list_frame  # type: ignore[attr-defined]
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

    _attach_treeview_hover(tree)
    tree._renata_header_bar = header_bar  # type: ignore[attr-defined]
    tree._renata_columns_button = columns_button  # type: ignore[attr-defined]
    tree._renata_state_container = tree_frame  # type: ignore[attr-defined]
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


def podswietl_cel(lb, idx) -> None:
    try:
        i = int(idx)
    except Exception:
        return
    try:
        lb.selection_clear(0, tk.END)
        lb.selection_set(i)
        lb.activate(i)
        lb.see(i)
    except Exception:
        pass

def _format_bool(value) -> str:
    if value is True:
        return "Y"
    if value is False:
        return ""
    return ""

def _format_number(value, fmt: str) -> str:
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return "-"
            text = re.sub(r"\s+", "", text)
            text = re.sub(r"[^0-9,\.\-]", "", text)
            if text in ("", "-", ".", "-.", ",", "-,"):
                return "-"
            if "," in text and "." not in text:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
            value = text
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

    show_lp = bool(getattr(schema, "show_lp", True))
    lp_key = "__lp__"
    tree["columns"] = ([lp_key] if show_lp else []) + [col.key for col in columns]
    tree["show"] = "headings"

    widths = _compute_column_widths(columns, rows)
    if show_lp:
        tree.column(lp_key, width=40, anchor="e", stretch=False)
        tree.heading(
            lp_key,
            text=_format_treeview_header(tree, lp_key, "LP"),
            command=lambda key=lp_key: _sort_treeview(tree, schema_id, key),
            anchor="e",
        )
    for col in columns:
        width_px = max(60, int(widths.get(col.key, 8) * 8))
        key_text = (col.key or "").lower()
        label_text = (col.label or "").lower()
        if "system" in key_text or label_text.startswith("system"):
            anchor = "w"
        else:
            anchor = "center"
        tree.column(col.key, width=width_px, anchor=anchor, stretch=True)
        tree.heading(
            col.key,
            text=_format_treeview_header(tree, col.key, col.label),
            command=lambda key=col.key: _sort_treeview(tree, schema_id, key),
            anchor=anchor,
        )

    tree.delete(*tree.get_children())
    rows_by_iid = {}
    for idx, row in enumerate(rows):
        iid = str(idx)
        values = [str(idx + 1)] if show_lp else []
        for col in columns:
            value = _get_value_by_key(row, col.value_path or col.key)
            values.append(format_value(value, col.fmt))
        tree.insert("", "end", iid=iid, values=values)
        rows_by_iid[iid] = row
    tree._renata_table_schema = schema_id  # type: ignore[attr-defined]
    tree._renata_table_rows = list(rows)  # type: ignore[attr-defined]
    tree._renata_tree_rows_by_iid = rows_by_iid  # type: ignore[attr-defined]
    tree._renata_tree_show_lp = show_lp  # type: ignore[attr-defined]
    tree.tag_configure("copied", background=COPIED_BG, foreground=COPIED_FG)
    tree.tag_configure("hover", background=HOVER_BG)
    _apply_saved_sort(tree, schema_id, columns, show_lp)
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
    if col_key == lp_key and "__lp__" in list(tree["columns"] or []):
        _apply_treeview_sort(tree, schema_id, col_key, desc=False, persist=True)
        return

    col = next((c for c in schema.columns if c.key == col_key), None)
    if col is None:
        return

    sort_state = getattr(tree, "_renata_tree_sort", {"column": None, "desc": False})
    desc = False
    if sort_state.get("column") == col_key:
        desc = not bool(sort_state.get("desc"))
    _apply_treeview_sort(tree, schema_id, col_key, desc=desc, persist=True)

def _update_treeview_lp(tree) -> None:
    if "__lp__" not in list(tree["columns"] or []):
        return
    for idx, iid in enumerate(tree.get_children()):
        values = list(tree.item(iid, "values") or [])
        if not values:
            values = [str(idx + 1)]
        else:
            values[0] = str(idx + 1)
        tree.item(iid, values=values)

def _apply_treeview_sort(tree, schema_id: str, col_key: str, *, desc: bool, persist: bool) -> None:
    try:
        from gui import table_schemas
    except Exception:
        return
    schema = table_schemas.get_schema(schema_id)
    if schema is None:
        return
    lp_key = "__lp__"
    rows_by_iid = getattr(tree, "_renata_tree_rows_by_iid", {})
    if col_key == lp_key and "__lp__" in list(tree["columns"] or []):
        tree._renata_tree_sort = {"column": lp_key, "desc": False}  # type: ignore[attr-defined]
        items = []
        for iid, row in rows_by_iid.items():
            route_index = row.get("_route_index", 0)
            items.append((iid, route_index))
        items.sort(key=lambda item: item[1])
        for idx, (iid, _) in enumerate(items):
            tree.move(iid, "", idx)
        _update_treeview_lp(tree)
        _update_treeview_sort_indicators(tree, schema_id)
        if persist:
            _save_sort_state(schema_id, lp_key, False)
        return

    col = next((c for c in schema.columns if c.key == col_key), None)
    if col is None:
        return

    tree._renata_tree_sort = {"column": col_key, "desc": bool(desc)}  # type: ignore[attr-defined]
    items = []
    for iid, row in rows_by_iid.items():
        value = _get_value_by_key(row, col.value_path or col.key)
        items.append((iid, _sort_key_for_value(value)))
    items.sort(key=lambda item: item[1], reverse=bool(desc))
    for idx, (iid, _) in enumerate(items):
        tree.move(iid, "", idx)
    _update_treeview_lp(tree)
    _update_treeview_sort_indicators(tree, schema_id)
    if persist:
        _save_sort_state(schema_id, col_key, bool(desc))

def _apply_saved_sort(tree, schema_id: str, columns: list, show_lp: bool) -> None:
    if not _is_persist_sort_enabled():
        return
    sort_state = _get_saved_sort_state(schema_id)
    if not sort_state:
        return
    available = [col.key for col in columns]
    if show_lp:
        available = ["__lp__"] + available
    col_key = sort_state.get("column")
    desc = bool(sort_state.get("desc"))
    if col_key not in available:
        if show_lp:
            col_key = "__lp__"
            desc = False
        elif available:
            col_key = available[0]
            desc = False
        else:
            return
        _save_sort_state(schema_id, col_key, desc)
    _apply_treeview_sort(tree, schema_id, col_key, desc=desc, persist=False)

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
    if "__lp__" in list(tree["columns"] or []):
        tree.heading(
            lp_key,
            text=_format_treeview_header(tree, lp_key, "LP" + (arrow if active == lp_key else "")),
            command=lambda key=lp_key: _sort_treeview(tree, schema_id, key),
            anchor="e",
        )
    for col in schema.columns:
        label = col.label
        key_text = (col.key or "").lower()
        label_text = (col.label or "").lower()
        if "system" in key_text or label_text.startswith("system"):
            anchor = "w"
        else:
            anchor = "center"
        if col.key == active:
            label = f"{label}{arrow}"
        tree.heading(
            col.key,
            text=_format_treeview_header(tree, col.key, label),
            command=lambda key=col.key: _sort_treeview(tree, schema_id, key),
            anchor=anchor,
        )

def _format_treeview_header(tree, col_key: str, label: str) -> str:
    return label

def _attach_treeview_hover(tree) -> None:
    if getattr(tree, "_renata_hover_bound", False):
        return

    def _clear_hover(target):
        prev = getattr(target, "_renata_hover_iid", None)
        if prev:
            tags = tuple(tag for tag in (target.item(prev, "tags") or ()) if tag != "hover")
            target.item(prev, tags=tags)
        target._renata_hover_iid = None  # type: ignore[attr-defined]

    def _on_motion(event):
        target = event.widget
        row_id = target.identify_row(event.y)
        prev = getattr(target, "_renata_hover_iid", None)
        if row_id == prev:
            return
        if prev:
            tags = tuple(tag for tag in (target.item(prev, "tags") or ()) if tag != "hover")
            target.item(prev, tags=tags)
        if not row_id:
            target._renata_hover_iid = None  # type: ignore[attr-defined]
            return
        tags = list(target.item(row_id, "tags") or ())
        if "copied" in tags:
            target._renata_hover_iid = None  # type: ignore[attr-defined]
            return
        if "hover" not in tags:
            tags.append("hover")
            target.item(row_id, tags=tags)
        target._renata_hover_iid = row_id  # type: ignore[attr-defined]

    def _on_leave(event):
        _clear_hover(event.widget)

    tree.bind("<Motion>", _on_motion, add="+")
    tree.bind("<Leave>", _on_leave, add="+")
    tree._renata_hover_bound = True  # type: ignore[attr-defined]

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

def _get_default_visible_columns(schema) -> list[str]:
    defaults = [col.key for col in schema.columns if col.default_visible]
    if not defaults and schema.columns:
        defaults = [schema.columns[0].key]
    return defaults

def _sanitize_visible_columns(schema, visible: list[str]) -> list[str]:
    keys = {col.key for col in schema.columns}
    return [key for key in visible if key in keys]

def _sanitize_preset_columns(schema, columns) -> list[str]:
    if not isinstance(columns, list):
        return []
    cleaned = [str(item) for item in columns if str(item)]
    return _sanitize_visible_columns(schema, cleaned)

def _load_column_presets(schema_id: str, schema, visible_fallback: list[str]) -> tuple[dict[str, list[str]], str]:
    cfg = config.get("column_presets", {})
    if not isinstance(cfg, dict):
        cfg = {}
    schema_cfg = cfg.get(schema_id)
    presets = {}
    active = None
    if isinstance(schema_cfg, dict):
        raw_presets = schema_cfg.get("presets")
        if isinstance(raw_presets, dict):
            presets = raw_presets
        active = schema_cfg.get("active")
    cleaned = {}
    for name, cols in presets.items():
        if not isinstance(name, str) or not name.strip():
            continue
        normalized = _sanitize_preset_columns(schema, cols)
        if normalized:
            cleaned[name.strip()] = normalized
    if not visible_fallback:
        visible_fallback = _get_default_visible_columns(schema)
    if not cleaned:
        cleaned = {"Default": list(visible_fallback)}
        active = "Default"
    if not isinstance(active, str) or active not in cleaned:
        active = next(iter(cleaned))
    return cleaned, active

def _save_column_presets(schema_id: str, presets: dict[str, list[str]], active: str) -> None:
    cfg = config.get("column_presets", {})
    if not isinstance(cfg, dict):
        cfg = {}
    new_cfg = dict(cfg)
    new_cfg[schema_id] = {"active": active, "presets": presets}
    try:
        config.save({"column_presets": new_cfg})
    except Exception:
        pass

def _is_persist_sort_enabled() -> bool:
    return bool(config.get("features.tables.persist_sort_enabled", False))

def _get_saved_sort_state(schema_id: str) -> dict | None:
    cfg = config.get("tables_sort_state", {})
    if not isinstance(cfg, dict):
        return None
    state = cfg.get(schema_id)
    if not isinstance(state, dict):
        return None
    column = state.get("column")
    desc = state.get("desc")
    if not isinstance(column, str) or not column:
        return None
    return {"column": column, "desc": bool(desc)}

def _save_sort_state(schema_id: str, column: str, desc: bool) -> None:
    if not _is_persist_sort_enabled():
        return
    cfg = config.get("tables_sort_state", {})
    if not isinstance(cfg, dict):
        cfg = {}
    new_cfg = dict(cfg)
    new_cfg[schema_id] = {"column": column, "desc": bool(desc)}
    try:
        config.save({"tables_sort_state": new_cfg})
    except Exception:
        pass

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
    observer = _LISTBOX_REFRESH_OBSERVER
    if callable(observer):
        try:
            observer(listbox, schema_id, list(lines), _get_visible_columns(schema_id))
        except Exception:
            pass

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
            save_window_geometry(existing, "column_picker", include_size=False)
            existing.destroy()
            listbox._renata_columns_dialog = None  # type: ignore[attr-defined]
            return
    except Exception:
        listbox._renata_columns_dialog = None  # type: ignore[attr-defined]

    dialog = tk.Toplevel(listbox)
    listbox._renata_columns_dialog = dialog  # type: ignore[attr-defined]
    dialog.title(f"Kolumny: {schema.title}")
    dialog.resizable(False, False)
    dialog.transient(listbox.winfo_toplevel())
    restore_window_geometry(dialog, "column_picker", include_size=False)
    bind_window_geometry(dialog, "column_picker", include_size=False)

    def _close_dialog() -> None:
        save_window_geometry(dialog, "column_picker", include_size=False)
        try:
            dialog.destroy()
        finally:
            listbox._renata_columns_dialog = None  # type: ignore[attr-defined]

    dialog.protocol("WM_DELETE_WINDOW", _close_dialog)

    visible = _get_saved_visible_columns(schema_id)
    if visible is None:
        visible = _get_default_visible_columns(schema)
    visible = _sanitize_visible_columns(schema, visible)
    if not visible:
        visible = _get_default_visible_columns(schema)

    presets, active_preset = _load_column_presets(schema_id, schema, visible)
    preset_var = tk.StringVar(value=active_preset)

    preset_frame = ttk.Frame(dialog)
    preset_frame.pack(fill="x", padx=10, pady=(8, 4))
    ttk.Label(preset_frame, text="Preset:").pack(side="left")
    preset_combo = ttk.Combobox(
        preset_frame,
        textvariable=preset_var,
        values=list(presets.keys()),
        state="readonly",
        width=16,
    )
    preset_combo.pack(side="left", padx=6)
    ttk.Button(preset_frame, text="Save as...", command=lambda: _save_as_preset()).pack(side="left", padx=(6, 0))
    ttk.Button(preset_frame, text="Rename", command=lambda: _rename_preset()).pack(side="left", padx=6)
    ttk.Button(preset_frame, text="Delete", command=lambda: _delete_preset()).pack(side="left")

    vars_map: dict[str, tk.BooleanVar] = {}
    updating = {"value": False}

    def _current_selected() -> list[str]:
        selected = [col.key for col in schema.columns if vars_map[col.key].get()]
        selected = _sanitize_visible_columns(schema, selected)
        if not selected:
            selected = _get_default_visible_columns(schema)
        return selected

    def _refresh_preset_combo() -> None:
        nonlocal active_preset
        preset_combo["values"] = list(presets.keys())
        if active_preset not in presets:
            active_preset = next(iter(presets))
        preset_var.set(active_preset)

    def _apply_selection() -> None:
        nonlocal active_preset
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
        if active_preset:
            presets[active_preset] = list(selected)
            _save_column_presets(schema_id, presets, active_preset)
        if isinstance(listbox, ttk.Treeview):
            _refresh_table_treeview(listbox)
        else:
            _refresh_table_listbox(listbox)

    def _apply_preset(name: str) -> None:
        nonlocal active_preset
        selected = presets.get(name) or _get_default_visible_columns(schema)
        selected = _sanitize_visible_columns(schema, selected)
        if not selected:
            selected = _get_default_visible_columns(schema)
        updating["value"] = True
        for col in schema.columns:
            vars_map[col.key].set(col.key in selected)
        updating["value"] = False
        active_preset = name
        _save_column_presets(schema_id, presets, active_preset)
        _apply_selection()

    def _on_preset_selected(_event=None) -> None:
        name = preset_var.get()
        if name not in presets:
            return
        _apply_preset(name)

    def _save_as_preset() -> None:
        nonlocal active_preset
        name = simpledialog.askstring("Kolumny", "Nazwa presetu:", parent=dialog)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in presets:
            messagebox.showwarning("Kolumny", "Preset o tej nazwie juz istnieje.", parent=dialog)
            return
        presets[name] = _current_selected()
        active_preset = name
        _save_column_presets(schema_id, presets, active_preset)
        _refresh_preset_combo()

    def _rename_preset() -> None:
        nonlocal active_preset
        if not active_preset:
            return
        name = simpledialog.askstring("Kolumny", "Nowa nazwa presetu:", initialvalue=active_preset, parent=dialog)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in presets and name != active_preset:
            messagebox.showwarning("Kolumny", "Preset o tej nazwie juz istnieje.", parent=dialog)
            return
        if name == active_preset:
            return
        presets[name] = presets.pop(active_preset)
        active_preset = name
        _save_column_presets(schema_id, presets, active_preset)
        _refresh_preset_combo()

    def _delete_preset() -> None:
        nonlocal active_preset
        if len(presets) <= 1:
            messagebox.showwarning("Kolumny", "Nie mozna usunac ostatniego presetu.", parent=dialog)
            return
        if not messagebox.askyesno("Kolumny", "Usunac aktywny preset?", parent=dialog):
            return
        if active_preset in presets:
            presets.pop(active_preset, None)
        active_preset = next(iter(presets))
        _save_column_presets(schema_id, presets, active_preset)
        _refresh_preset_combo()
        _apply_preset(active_preset)

    preset_combo.bind("<<ComboboxSelected>>", _on_preset_selected)

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
