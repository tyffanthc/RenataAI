import json
import os
import re
import tkinter as tk
import time
from datetime import datetime, timezone
from tkinter import messagebox, simpledialog, ttk
from typing import Any

import config
from app.state import app_state
from gui.dialogs.add_entry import AddEntryDialog
from gui.tabs.journal_map import JournalMapTab
from logic.entry_repository import EntryRepository, EntryValidationError
from logic.entry_templates import EntryTemplateError, build_template_entry
from logic.journal_entry_mapping import build_mvp_entry_draft
from logic.journal_navigation import (
    extract_navigation_chips,
    resolve_chip_nav_target,
    resolve_entry_nav_target_typed,
    resolve_logbook_nav_target_typed,
    resolve_logbook_nav_target,
)
from logic.logbook_feed import (
    build_logbook_info_rows,
    build_logbook_summary_snapshot,
    classify_logbook_event,
)
from logic.logbook_feed_cache import (
    append_logbook_feed_cache_item,
    clear_logbook_feed_cache,
    load_logbook_feed_cache,
)
from logic.utils.renata_log import log_event_throttled

try:
    import pyperclip
except ImportError:
    pyperclip = None

COLOR_BG = "#0b0c10"
COLOR_FG = "#ff7100"
COLOR_SEC = "#c5c6c7"
COLOR_ACCENT = "#1f2833"

_CATEGORY_ALL = "(Wszystkie)"
_CATEGORY_FALLBACK = "Dziennik/Ogolne"
_LOGBOOK_CLASS_ALL = "Wszystkie (ALL)"
_LOGBOOK_FEED_CLASS_ORDER = (
    "Nawigacja",
    "Eksploracja",
    "Exobio",
    "Handel",
    "Stacja",
    "Incydent",
    "Combat",
    "TECH",
)
_DEFAULT_METADATA_TAGS = [
    "exploration",
    "scan",
    "dss",
    "navigation",
    "jump",
    "station",
    "docked",
    "undocked",
    "trade",
    "market",
    "marketbuy",
    "marketsell",
    "mining",
    "prospecting",
    "asteroid",
]


def _merge_default_tags(local_tags: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for raw_tag in list(local_tags):
        tag = str(raw_tag or "").strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)

    for raw_tag in _DEFAULT_METADATA_TAGS:
        tag = str(raw_tag or "").strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)

    out.sort()
    return out


def _to_iso_date(value: str, *, end_of_day: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.strptime(text, "%Y-%m-%d")
    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    else:
        parsed = parsed.replace(hour=0, minute=0, second=0)
    return parsed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _today_date_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _format_ts(iso_text: str) -> str:
    text = str(iso_text or "").strip()
    if not text:
        return "-"
    if text.endswith("Z"):
        text = text[:-1]
    return text.replace("T", " ")[:16]


def _parse_lat_lon(coords_text: str) -> tuple[float | None, float | None]:
    text = str(coords_text or "")
    match = re.search(
        r"lat\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*lon\s*:\s*(-?\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def _maybe_station_name(body_text: str) -> str | None:
    text = str(body_text or "").strip()
    if not text:
        return None
    lower = text.lower()
    station_tokens = (
        "station",
        "gateway",
        "terminal",
        "port",
        "outpost",
        "hub",
        "settlement",
        "carrier",
        "dock",
        "base",
        "city",
    )
    if any(token in lower for token in station_tokens):
        return text
    return None


def _logbook_feed_item_signature(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ""
    parts = [
        str(item.get("timestamp") or "").strip(),
        str(item.get("event_name") or "").strip(),
        str(item.get("system_name") or "").strip(),
        str(item.get("station_name") or "").strip(),
        str(item.get("body_name") or "").strip(),
        str(item.get("summary") or "").strip(),
    ]
    if not any(parts):
        return ""
    return "\x1f".join(parts)


class LogbookTab(tk.Frame):
    DEFAULT_CATEGORIES = [
        "Gornictwo",
        "Eksploracja",
        "Handel",
        "Ciekawe miejsca",
    ]

    def __init__(self, parent, app=None, manager=None, repository=None, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)
        self.app = app
        self.manager = manager  # legacy manager kept for compatibility
        self.repository = repository or EntryRepository()
        self._category_store_path = config.renata_user_home_file("user_entry_categories.json")

        self._category_display_to_path: dict[str, str] = {}
        self._entry_item_to_id: dict[str, str] = {}
        self._logbook_item_to_payload: dict[str, dict] = {}
        self._logbook_chip_item_to_payload: dict[str, dict] = {}
        self._selected_entry_id: str | None = None
        self._selected_logbook_item_id: str | None = None
        self._selected_logbook_chip_item_id: str | None = None
        self._selected_category: str = _CATEGORY_ALL
        self._saved_categories = self._load_saved_categories()

        self.filter_text_var = tk.StringVar()
        self.filter_tag_var = tk.StringVar(value="Wszystkie (ALL)")
        self.filter_date_from_var = tk.StringVar(value="forever")
        self.filter_date_to_var = tk.StringVar(value=_today_date_text())
        self.filter_tag_mode_var = tk.StringVar(value="ALL")
        self.filter_pinned_only_var = tk.BooleanVar(value=False)
        self.sort_var = tk.StringVar(value="Najnowsze")
        self.status_var = tk.StringVar(value="")
        self.preview_title_var = tk.StringVar(value="Brak wybranego wpisu")
        self.preview_meta_var = tk.StringVar(value="-")
        self.logbook_status_var = tk.StringVar(value="Feed pusty.")
        self.logbook_summary_var = tk.StringVar(value="Podsumowanie: brak danych.")
        self._logbook_feed_limit = 250
        self.logbook_class_filter_var = tk.StringVar(value=_LOGBOOK_CLASS_ALL)
        self.logbook_show_tech_var = tk.BooleanVar(value=False)
        self._logbook_feed_sort_column = "time"
        self._logbook_feed_sort_desc = True
        self._logbook_feed_items: list[dict] = []
        self._selected_filter_tags: set[str] = set()
        self._active_popover: tk.Widget | None = None
        self._active_popover_anchor: tk.Widget | None = None
        self._active_popover_opened_at: float = 0.0
        self._ui_state_suppress_persist = True
        self._pending_subtab_key = "entries"
        self._pending_map_ui_state: dict[str, Any] = {}
        self._logbook_feed_restore_in_progress = False
        self._load_ui_state()

        self._configure_style()
        self._build_ui()
        try:
            self.tab_map.apply_persisted_ui_state(self._pending_map_ui_state)
        except Exception:
            log_event_throttled(
                "logbook.map_ui_state.apply",
                3000,
                "WARN",
                "Logbook: failed to apply persisted map UI state",
            )
        self._restore_logbook_feed_from_cache()
        self.sub_notebook.bind("<<NotebookTabChanged>>", self._on_subtab_changed, add="+")
        self._restore_subtab_from_ui_state()
        self._set_filter_tag_display()
        self.bind_all("<Button-1>", self._on_global_click_maybe_close_popover, add="+")
        self._refresh_categories()
        self._refresh_entries()
        self._ui_state_suppress_persist = False

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.configure(
            "Journal.Treeview",
            background=COLOR_ACCENT,
            fieldbackground=COLOR_ACCENT,
            foreground=COLOR_FG,
            rowheight=24,
        )
        style.configure(
            "Journal.Treeview.Heading",
            background=COLOR_ACCENT,
            foreground=COLOR_SEC,
            relief="flat",
        )
        style.map("Journal.Treeview.Heading", background=[("active", COLOR_ACCENT)])

    def _create_spansh_like_treeview(
        self,
        parent,
        *,
        columns: tuple[str, ...],
        selectmode: str = "browse",
        height: int | None = None,
    ) -> ttk.Treeview:
        kwargs = {
            "columns": columns,
            "show": "headings",
            "style": "Treeview",
            "selectmode": selectmode,
        }
        if height is not None:
            kwargs["height"] = int(height)
        return ttk.Treeview(parent, **kwargs)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.sub_notebook = ttk.Notebook(self)
        self.sub_notebook.grid(row=0, column=0, sticky="nsew")

        self.tab_entries = tk.Frame(self.sub_notebook, bg=COLOR_BG)
        self.tab_feed = tk.Frame(self.sub_notebook, bg=COLOR_BG)
        self.tab_map = JournalMapTab(self.sub_notebook, app=self.app, logbook_owner=self)
        self.sub_notebook.add(self.tab_entries, text="Wpisy")
        self.sub_notebook.add(self.tab_feed, text="Logbook")
        self.sub_notebook.add(self.tab_map, text="Mapa")

        self._build_entries_tab()
        self._build_logbook_tab()

    def _build_entries_tab(self) -> None:
        self.tab_entries.columnconfigure(0, weight=1)
        self.tab_entries.rowconfigure(2, weight=1)

        toolbar = tk.Frame(self.tab_entries, bg=COLOR_BG)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        self.btn_add_entry = tk.Button(
            toolbar,
            text="+ Nowy wpis",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._add_entry,
        )
        self.btn_add_entry.pack(side="left", padx=(0, 6))

        self.btn_edit_entry = tk.Button(
            toolbar,
            text="Edytuj",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._edit_selected_entry,
        )
        self.btn_edit_entry.pack(side="left", padx=(0, 6))

        self.btn_delete_entry = tk.Button(
            toolbar,
            text="Usun",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._delete_selected_entry,
        )
        self.btn_delete_entry.pack(side="left", padx=(0, 6))

        self.btn_add_category = tk.Button(
            toolbar,
            text="+ Kategoria",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._add_category,
        )
        self.btn_add_category.pack(side="left", padx=(0, 6))

        self.btn_add_template = tk.Button(
            toolbar,
            text="+ Szablon",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._add_entry_from_template,
        )
        self.btn_add_template.pack(side="left", padx=(0, 6))

        self.btn_pinboard_toggle = tk.Button(
            toolbar,
            text="Pinboard: OFF",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._toggle_pinboard_filter,
        )
        self.btn_pinboard_toggle.pack(side="left", padx=(0, 6))

        filters = tk.Frame(self.tab_entries, bg=COLOR_BG)
        filters.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        filters.columnconfigure(1, weight=2)
        filters.columnconfigure(3, weight=1)
        filters.columnconfigure(5, weight=1)

        tk.Label(filters, text="Szukaj:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=0, sticky="w"
        )
        self.entry_filter_text = tk.Entry(
            filters,
            textvariable=self.filter_text_var,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
        )
        self.entry_filter_text.grid(row=0, column=1, sticky="ew", padx=(4, 12))
        self.entry_filter_text.bind("<KeyRelease>", lambda _e: self._on_filters_changed())

        tk.Label(filters, text="Tagi:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=2, sticky="w"
        )
        self.entry_filter_tags = tk.Entry(
            filters,
            textvariable=self.filter_tag_var,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
            state="readonly",
            readonlybackground=COLOR_ACCENT,
            cursor="hand2",
        )
        self.entry_filter_tags.grid(row=0, column=3, sticky="ew", padx=(4, 12))
        self.entry_filter_tags.bind("<ButtonRelease-1>", self._on_tags_filter_click)

        tk.Label(filters, text="Od (YYYY-MM-DD):", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.entry_filter_date_from = tk.Entry(
            filters,
            textvariable=self.filter_date_from_var,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
            state="readonly",
            readonlybackground=COLOR_ACCENT,
            cursor="hand2",
        )
        self.entry_filter_date_from.grid(
            row=1, column=1, sticky="ew", padx=(4, 12), pady=(6, 0)
        )
        self.entry_filter_date_from.bind("<ButtonRelease-1>", self._on_filter_date_from_click)

        tk.Label(filters, text="Do (YYYY-MM-DD):", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=1, column=2, sticky="w", pady=(6, 0)
        )
        self.entry_filter_date_to = tk.Entry(
            filters,
            textvariable=self.filter_date_to_var,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
            state="readonly",
            readonlybackground=COLOR_ACCENT,
            cursor="hand2",
        )
        self.entry_filter_date_to.grid(row=1, column=3, sticky="ew", padx=(4, 12), pady=(6, 0))
        self.entry_filter_date_to.bind("<ButtonRelease-1>", self._on_filter_date_to_click)

        tk.Label(filters, text="Sort:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=4, sticky="w"
        )
        self.sort_combo = ttk.Combobox(
            filters,
            values=("Najnowsze", "Najstarsze", "System A-Z", "Tytul A-Z"),
            state="readonly",
            textvariable=self.sort_var,
        )
        self.sort_combo.grid(row=0, column=5, sticky="ew", padx=(4, 0))
        self.sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filters_changed())

        self.chk_pinned_only = tk.Checkbutton(
            filters,
            text="Przypiete",
            variable=self.filter_pinned_only_var,
            command=self._on_filters_changed,
            bg=COLOR_BG,
            fg=COLOR_FG,
            selectcolor=COLOR_ACCENT,
            activebackground=COLOR_BG,
            activeforeground=COLOR_FG,
        )
        self.chk_pinned_only.grid(row=0, column=6, sticky="w", padx=(10, 0))

        paned = tk.PanedWindow(self.tab_entries, orient="horizontal", sashwidth=6, bg=COLOR_BG)
        paned.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))

        left = tk.Frame(paned, bg=COLOR_BG)
        middle = tk.Frame(paned, bg=COLOR_BG)
        right = tk.Frame(paned, bg=COLOR_BG)
        paned.add(left, minsize=200)
        paned.add(middle, minsize=340)
        paned.add(right, minsize=320)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        tk.Label(left, text="Kategorie", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=0, sticky="w", pady=(2, 4)
        )
        self.category_list = tk.Listbox(
            left,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            selectbackground=COLOR_FG,
            selectforeground=COLOR_BG,
            relief="flat",
            exportselection=False,
        )
        self.category_list.grid(row=1, column=0, sticky="nsew")
        self.category_list.bind("<<ListboxSelect>>", self._on_category_selected)

        middle.columnconfigure(0, weight=1)
        middle.rowconfigure(1, weight=1)
        tk.Label(middle, text="Lista wpisow", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=0, sticky="w", pady=(2, 4)
        )
        self.entries_tree = ttk.Treeview(
            middle,
            columns=("title", "updated", "system", "tags", "source"),
            show="headings",
            style="Journal.Treeview",
            selectmode="browse",
        )
        self.entries_tree.heading("title", text="Tytul")
        self.entries_tree.heading("updated", text="Aktualizacja")
        self.entries_tree.heading("system", text="System")
        self.entries_tree.heading("tags", text="Tagi")
        self.entries_tree.heading("source", text="Zrodlo")
        self.entries_tree.column("title", width=210, anchor="w")
        self.entries_tree.column("updated", width=135, anchor="w")
        self.entries_tree.column("system", width=120, anchor="w")
        self.entries_tree.column("tags", width=140, anchor="w")
        self.entries_tree.column("source", width=80, anchor="w")
        self.entries_tree.grid(row=1, column=0, sticky="nsew")
        self.entries_tree.bind("<<TreeviewSelect>>", self._on_entry_selected)
        self.entries_tree.bind("<Double-1>", lambda _e: self._edit_selected_entry())
        self.entries_tree.bind("<Button-3>", self._on_entry_context_menu)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)
        tk.Label(right, text="Podglad", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=0, sticky="w", pady=(2, 4)
        )
        self.preview_title_label = tk.Label(
            right,
            textvariable=self.preview_title_var,
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
            justify="left",
            font=("Segoe UI", 10, "bold"),
        )
        self.preview_title_label.grid(row=1, column=0, sticky="ew")
        self.preview_title_label.bind("<Button-3>", self._on_entry_context_menu)
        self.preview_meta_label = tk.Label(
            right,
            textvariable=self.preview_meta_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.preview_meta_label.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.preview_meta_label.bind("<Button-3>", self._on_entry_context_menu)

        self.preview_text = tk.Text(
            right,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
            wrap="word",
            state="disabled",
        )
        self.preview_text.grid(row=3, column=0, sticky="nsew")
        self.preview_text.bind("<Button-3>", self._on_entry_context_menu)

        action_row = tk.Frame(right, bg=COLOR_BG)
        action_row.grid(row=4, column=0, sticky="ew", pady=(6, 0))

        self.btn_set_target = tk.Button(
            action_row,
            text="Ustaw cel",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._set_target_from_selected_entry,
        )
        self.btn_set_target.pack(side="left", padx=(0, 6))

        self.btn_toggle_pin = tk.Button(
            action_row,
            text="Przypnij",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._toggle_pin_selected_entry,
        )
        self.btn_toggle_pin.pack(side="left", padx=(0, 6))

        self.btn_copy_system = tk.Button(
            action_row,
            text="Kopiuj system",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._copy_selected_system,
        )
        self.btn_copy_system.pack(side="left", padx=(0, 6))

        status_label = tk.Label(
            self.tab_entries,
            textvariable=self.status_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
        )
        status_label.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))

        self._entry_context_menu = tk.Menu(self, tearoff=0)
        self._entry_context_menu.add_command(
            label="Ustaw cel",
            command=self._set_target_from_selected_entry,
        )
        self._entry_context_menu.add_command(
            label="Przypnij",
            command=self._toggle_pin_selected_entry,
        )
        self._entry_context_menu.add_command(
            label="Kopiuj system",
            command=self._copy_selected_system,
        )
        self._entry_context_menu.add_command(
            label="Pokaz na mapie",
            command=self._show_selected_entry_on_map,
        )
        self._entry_context_menu.add_command(
            label="Edytuj metadane...",
            command=self._edit_selected_entry_metadata,
        )
        self._entry_context_menu.add_separator()
        self._entry_move_menu = tk.Menu(self._entry_context_menu, tearoff=0)
        self._entry_context_menu.add_cascade(
            label="Przenies do...",
            menu=self._entry_move_menu,
        )
        self._sync_pinboard_button_label()

    def _build_logbook_tab(self) -> None:
        self.tab_feed.columnconfigure(0, weight=1)
        self.tab_feed.columnconfigure(1, weight=0)
        self.tab_feed.rowconfigure(1, weight=1)

        header = tk.Frame(self.tab_feed, bg=COLOR_BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(3, weight=0)

        tk.Label(
            header,
            text="Logbook (feed Journal)",
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Button(
            header,
            text="Wyczysc feed",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._clear_logbook_feed,
        ).grid(row=0, column=1, sticky="e")

        tk.Label(
            header,
            text="Klasy:",
            bg=COLOR_BG,
            fg=COLOR_FG,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.logbook_class_filter_combo = ttk.Combobox(
            header,
            values=(_LOGBOOK_CLASS_ALL, *_LOGBOOK_FEED_CLASS_ORDER),
            state="readonly",
            textvariable=self.logbook_class_filter_var,
            width=22,
        )
        self.logbook_class_filter_combo.grid(row=1, column=1, sticky="e", padx=(6, 0), pady=(6, 0))
        self.logbook_class_filter_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._on_logbook_feed_filters_changed(),
        )

        self.chk_logbook_show_tech = tk.Checkbutton(
            header,
            text="Pokaz TECH",
            variable=self.logbook_show_tech_var,
            command=self._on_logbook_feed_filters_changed,
            bg=COLOR_BG,
            fg=COLOR_FG,
            selectcolor=COLOR_ACCENT,
            activebackground=COLOR_BG,
            activeforeground=COLOR_FG,
        )
        self.chk_logbook_show_tech.grid(row=1, column=2, sticky="e", padx=(10, 0), pady=(6, 0))

        self.logbook_feed_tree = self._create_spansh_like_treeview(
            self.tab_feed,
            columns=("time", "class", "event", "system", "location", "summary"),
            selectmode="browse",
        )
        self._logbook_feed_header_labels = {
            "time": "Czas",
            "class": "Klasa",
            "event": "Event",
            "system": "System",
            "location": "Miejsce",
            "summary": "Podsumowanie",
        }
        self._update_logbook_feed_sort_indicators()

        self.logbook_feed_tree.column("time", width=130, anchor="w")
        self.logbook_feed_tree.column("class", width=120, anchor="w")
        self.logbook_feed_tree.column("event", width=130, anchor="w")
        self.logbook_feed_tree.column("system", width=160, anchor="w")
        self.logbook_feed_tree.column("location", width=180, anchor="w")
        self.logbook_feed_tree.column("summary", width=520, anchor="w")

        feed_scroll = ttk.Scrollbar(
            self.tab_feed,
            orient="vertical",
            command=self.logbook_feed_tree.yview,
        )
        self.logbook_feed_tree.configure(yscrollcommand=feed_scroll.set)

        self.logbook_feed_tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 6))
        feed_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=(0, 6))
        self.logbook_feed_tree.bind("<<TreeviewSelect>>", self._on_logbook_feed_selected)
        self.logbook_feed_tree.bind("<Button-3>", self._on_logbook_context_menu)

        actions = tk.Frame(self.tab_feed, bg=COLOR_BG)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))

        tk.Button(
            actions,
            text="Zapisz jako wpis",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=lambda: self._save_selected_logbook_as_entry(edit_after=False),
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            actions,
            text="Zapisz + edytuj",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=lambda: self._save_selected_logbook_as_entry(edit_after=True),
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            actions,
            text="Dodaj do istniejacego",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._append_selected_logbook_to_existing_entry,
        ).pack(side="left", padx=(0, 6))

        tk.Label(actions, text="|", bg=COLOR_BG, fg=COLOR_SEC).pack(side="left", padx=(2, 6))

        tk.Button(
            actions,
            text="Ustaw cel (event)",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._set_target_from_selected_logbook_event,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            actions,
            text="Ustaw cel (chip)",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._set_target_from_selected_logbook_chip,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            actions,
            text="Kopiuj chip",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._copy_selected_logbook_chip,
        ).pack(side="left", padx=(0, 6))

        details_panel = tk.Frame(self.tab_feed, bg=COLOR_BG)
        details_panel.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 6))
        details_panel.columnconfigure(0, weight=3)
        details_panel.columnconfigure(1, weight=2)
        details_panel.rowconfigure(1, weight=1)

        info_frame = tk.Frame(details_panel, bg=COLOR_BG)
        info_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=0)
        info_frame.rowconfigure(1, weight=1)

        tk.Label(
            info_frame,
            text="Informacje (zdarzenie)",
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        self.logbook_info_tree = self._create_spansh_like_treeview(
            info_frame,
            columns=("label", "value"),
            selectmode="browse",
            height=6,
        )
        self.logbook_info_tree.heading("label", text="Pole")
        self.logbook_info_tree.heading("value", text="Wartosc")
        self.logbook_info_tree.column("label", width=180, anchor="w")
        self.logbook_info_tree.column("value", width=520, anchor="w")
        self.logbook_info_tree.grid(row=1, column=0, sticky="nsew")

        info_scroll = ttk.Scrollbar(
            info_frame,
            orient="vertical",
            command=self.logbook_info_tree.yview,
        )
        self.logbook_info_tree.configure(yscrollcommand=info_scroll.set)
        info_scroll.grid(row=1, column=1, sticky="ns", padx=(6, 0))

        right_panel = tk.Frame(details_panel, bg=COLOR_BG)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.columnconfigure(1, weight=0)
        right_panel.rowconfigure(1, weight=1)

        tk.Label(
            right_panel,
            text="Chips nawigacyjne (SYSTEM/STATION)",
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        self.logbook_chip_tree = self._create_spansh_like_treeview(
            right_panel,
            columns=("kind", "value"),
            selectmode="browse",
            height=6,
        )
        self.logbook_chip_tree.heading("kind", text="Typ")
        self.logbook_chip_tree.heading("value", text="Wartosc")
        self.logbook_chip_tree.column("kind", width=120, anchor="w")
        self.logbook_chip_tree.column("value", width=320, anchor="w")
        self.logbook_chip_tree.grid(row=1, column=0, sticky="nsew")

        chip_scroll = ttk.Scrollbar(
            right_panel,
            orient="vertical",
            command=self.logbook_chip_tree.yview,
        )
        self.logbook_chip_tree.configure(yscrollcommand=chip_scroll.set)
        chip_scroll.grid(row=1, column=1, sticky="ns", padx=(6, 0))

        summary_frame = tk.Frame(details_panel, bg=COLOR_BG)
        summary_frame.grid(row=1, column=1, sticky="nsew", pady=(6, 0))
        summary_frame.columnconfigure(0, weight=1)

        tk.Label(
            summary_frame,
            text="Podsumowanie (aktualny filtr)",
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))
        tk.Label(
            summary_frame,
            textvariable=self.logbook_summary_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=1, column=0, sticky="ew")

        self.logbook_chip_tree.bind("<<TreeviewSelect>>", self._on_logbook_chip_selected)
        self.logbook_chip_tree.bind("<Button-3>", self._on_logbook_chip_context_menu)

        tk.Label(
            self.tab_feed,
            textvariable=self.logbook_status_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
            wraplength=1160,
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        self._logbook_context_menu = tk.Menu(self, tearoff=0)
        self._logbook_context_menu.add_command(
            label="Zapisz jako wpis",
            command=lambda: self._save_selected_logbook_as_entry(edit_after=False),
        )
        self._logbook_context_menu.add_command(
            label="Zapisz + edytuj",
            command=lambda: self._save_selected_logbook_as_entry(edit_after=True),
        )
        self._logbook_context_menu.add_separator()
        self._logbook_context_menu.add_command(
            label="Dodaj do istniejacego",
            command=self._append_selected_logbook_to_existing_entry,
        )
        self._logbook_context_menu.add_separator()
        self._logbook_context_menu.add_command(
            label="Ustaw cel (event)",
            command=self._set_target_from_selected_logbook_event,
        )
        self._logbook_context_menu.add_command(
            label="Pokaz na mapie",
            command=self._show_selected_logbook_event_on_map,
        )

        self._logbook_chip_context_menu = tk.Menu(self, tearoff=0)
        self._logbook_chip_context_menu.add_command(
            label="Ustaw cel (chip)",
            command=self._set_target_from_selected_logbook_chip,
        )
        self._logbook_chip_context_menu.add_command(
            label="Kopiuj chip",
            command=self._copy_selected_logbook_chip,
        )
        self._logbook_chip_context_menu.add_command(
            label="Pokaz na mapie",
            command=self._show_selected_logbook_chip_on_map,
        )

    def append_logbook_feed_item(self, item: dict, *, persist_cache: bool = True) -> None:
        if not isinstance(item, dict):
            return
        row = dict(item)
        event_name = str(row.get("event_name") or "").strip()
        if not event_name:
            return
        if not str(row.get("event_class") or "").strip():
            row["event_class"] = classify_logbook_event(event_name)

        incoming_sig = _logbook_feed_item_signature(row)
        if incoming_sig:
            for existing in self._logbook_feed_items:
                if _logbook_feed_item_signature(existing) == incoming_sig:
                    return
        self._logbook_feed_items.append(row)
        if len(self._logbook_feed_items) > self._logbook_feed_limit:
            self._logbook_feed_items = self._logbook_feed_items[-self._logbook_feed_limit :]
        self._render_logbook_feed_tree()
        if persist_cache and not self._logbook_feed_restore_in_progress:
            append_logbook_feed_cache_item(row, limit=self._logbook_feed_limit)

    def _clear_logbook_feed(self) -> None:
        self.logbook_feed_tree.delete(*self.logbook_feed_tree.get_children())
        self._logbook_item_to_payload.clear()
        self._logbook_feed_items.clear()
        self._selected_logbook_item_id = None
        self._refresh_logbook_nav_chips(None)
        self._refresh_logbook_info_panel(None)
        self._refresh_logbook_summary_panel([])
        self.logbook_status_var.set("Feed wyczyszczony.")
        clear_logbook_feed_cache()

    def _restore_logbook_feed_from_cache(self) -> None:
        rows = load_logbook_feed_cache(limit=self._logbook_feed_limit)
        if not rows:
            return
        self._logbook_feed_restore_in_progress = True
        try:
            # File order is chronological (oldest -> newest). Inserting each item at index 0
            # restores the visible feed with newest items on top.
            for row in rows:
                self.append_logbook_feed_item(row, persist_cache=False)
        finally:
            self._logbook_feed_restore_in_progress = False
        count = len(self.logbook_feed_tree.get_children())
        self.logbook_status_var.set(
            f"Przywrocono feed z cache: {count} (limit {self._logbook_feed_limit})"
        )

    def _on_logbook_feed_filters_changed(self) -> None:
        self._render_logbook_feed_tree()

    def _set_logbook_feed_sort(self, column: str) -> None:
        key = str(column or "").strip().lower()
        valid = {"time", "class", "event", "system", "location", "summary"}
        if key not in valid:
            return
        if self._logbook_feed_sort_column == key:
            self._logbook_feed_sort_desc = not bool(self._logbook_feed_sort_desc)
        else:
            self._logbook_feed_sort_column = key
            self._logbook_feed_sort_desc = key == "time"
        self._update_logbook_feed_sort_indicators()
        self._render_logbook_feed_tree()

    def _update_logbook_feed_sort_indicators(self) -> None:
        if not hasattr(self, "logbook_feed_tree"):
            return
        labels = getattr(self, "_logbook_feed_header_labels", {}) or {}
        active = str(self._logbook_feed_sort_column or "")
        marker = " v" if bool(self._logbook_feed_sort_desc) else " ^"
        for col in ("time", "class", "event", "system", "location", "summary"):
            base = str(labels.get(col) or col)
            text = f"{base}{marker}" if col == active else base
            self.logbook_feed_tree.heading(
                col,
                text=text,
                command=(lambda key=col: self._set_logbook_feed_sort(key)),
            )

    def _logbook_item_class(self, item: dict) -> str:
        event_class = str(item.get("event_class") or "").strip()
        if event_class:
            return event_class
        event_name = str(item.get("event_name") or "").strip()
        if event_name:
            return str(classify_logbook_event(event_name) or "TECH").strip() or "TECH"
        return "TECH"

    def _logbook_item_location(self, item: dict) -> str:
        station_name = str(item.get("station_name") or "").strip()
        body_name = str(item.get("body_name") or "").strip()
        return station_name or body_name or "-"

    def _filtered_sorted_logbook_items(self) -> list[dict]:
        selected_class = str(self.logbook_class_filter_var.get() or "").strip()
        show_tech = bool(self.logbook_show_tech_var.get())

        rows: list[dict] = []
        for item in self._logbook_feed_items:
            if not isinstance(item, dict):
                continue
            event_class = self._logbook_item_class(item)
            if not show_tech and event_class == "TECH":
                continue
            if selected_class and selected_class != _LOGBOOK_CLASS_ALL and event_class != selected_class:
                continue
            rows.append(item)

        sort_col = str(self._logbook_feed_sort_column or "time")
        desc = bool(self._logbook_feed_sort_desc)

        def _sort_key(row: dict) -> tuple:
            if sort_col == "time":
                return (str(row.get("timestamp") or ""), str(row.get("event_name") or ""))
            if sort_col == "class":
                cls = self._logbook_item_class(row)
                try:
                    idx = _LOGBOOK_FEED_CLASS_ORDER.index(cls)
                except ValueError:
                    idx = len(_LOGBOOK_FEED_CLASS_ORDER)
                return (idx, cls, str(row.get("timestamp") or ""))
            if sort_col == "event":
                return (str(row.get("event_name") or "").casefold(), str(row.get("timestamp") or ""))
            if sort_col == "system":
                return (str(row.get("system_name") or "").casefold(), str(row.get("timestamp") or ""))
            if sort_col == "location":
                return (self._logbook_item_location(row).casefold(), str(row.get("timestamp") or ""))
            if sort_col == "summary":
                return (str(row.get("summary") or "").casefold(), str(row.get("timestamp") or ""))
            return (str(row.get("timestamp") or ""),)

        rows.sort(key=_sort_key, reverse=desc)
        return rows

    def _render_logbook_feed_tree(self) -> None:
        selected_payload = self._selected_logbook_item()
        selected_signature = None
        if isinstance(selected_payload, dict):
            selected_signature = (
                str(selected_payload.get("timestamp") or ""),
                str(selected_payload.get("event_name") or ""),
                str(selected_payload.get("summary") or ""),
            )

        self.logbook_feed_tree.delete(*self.logbook_feed_tree.get_children())
        self._logbook_item_to_payload.clear()
        self._selected_logbook_item_id = None

        rows = self._filtered_sorted_logbook_items()
        self._refresh_logbook_summary_panel(rows)
        restore_iid: str | None = None
        for row in rows:
            event_name = str(row.get("event_name") or "").strip() or "-"
            event_class = self._logbook_item_class(row)
            timestamp = _format_ts(str(row.get("timestamp") or ""))
            system_name = str(row.get("system_name") or "").strip() or "-"
            location = self._logbook_item_location(row)
            summary = str(row.get("summary") or "").strip() or event_name
            iid = self.logbook_feed_tree.insert(
                "",
                "end",
                values=(timestamp, event_class, event_name, system_name, location, summary),
            )
            self._logbook_item_to_payload[iid] = dict(row)
            row_signature = (
                str(row.get("timestamp") or ""),
                str(row.get("event_name") or ""),
                str(row.get("summary") or ""),
            )
            if selected_signature and row_signature == selected_signature:
                restore_iid = iid

        if restore_iid:
            try:
                self.logbook_feed_tree.selection_set(restore_iid)
                self.logbook_feed_tree.focus(restore_iid)
                self._selected_logbook_item_id = restore_iid
                selected_item = self._selected_logbook_item()
                self._refresh_logbook_nav_chips(selected_item)
                self._refresh_logbook_info_panel(selected_item)
            except Exception:
                self._selected_logbook_item_id = None
                self._refresh_logbook_nav_chips(None)
                self._refresh_logbook_info_panel(None)
        else:
            self._refresh_logbook_nav_chips(None)
            self._refresh_logbook_info_panel(None)

        visible_count = len(rows)
        total_count = len(self._logbook_feed_items)
        class_filter = str(self.logbook_class_filter_var.get() or _LOGBOOK_CLASS_ALL)
        sort_label = f"{self._logbook_feed_sort_column}{' desc' if self._logbook_feed_sort_desc else ' asc'}"
        self.logbook_status_var.set(
            f"Eventow w feedzie: {visible_count}/{total_count} (limit {self._logbook_feed_limit}) | Klasa: {class_filter} | Sort: {sort_label}"
        )

    def _on_logbook_feed_selected(self, _event=None) -> None:
        selected = self.logbook_feed_tree.selection()
        self._selected_logbook_item_id = selected[0] if selected else None
        item = self._selected_logbook_item()
        if not item:
            self._refresh_logbook_nav_chips(None)
            self._refresh_logbook_info_panel(None)
            return
        self._refresh_logbook_nav_chips(item)
        self._refresh_logbook_info_panel(item)
        default_category = str(item.get("default_category") or "-")
        chips = item.get("chips") or []
        event_class = str(item.get("event_class") or "TECH")
        chips_text = ", ".join(
            f"{str(chip.get('kind') or '')}:{str(chip.get('value') or '')}"
            for chip in chips[:6]
        )
        if len(chips) > 6:
            chips_text += ", ..."
        summary = str(item.get("summary") or "").strip() or str(item.get("event_name") or "")
        self.logbook_status_var.set(
            f"Wybrane: {summary} | Klasa: {event_class} | Domyslna kategoria: {default_category} | Chips: {chips_text or '-'}"
        )

    def _refresh_logbook_nav_chips(self, feed_item: dict | None) -> None:
        self._logbook_chip_item_to_payload.clear()
        self._selected_logbook_chip_item_id = None
        self.logbook_chip_tree.delete(*self.logbook_chip_tree.get_children())
        for chip in extract_navigation_chips(feed_item):
            iid = self.logbook_chip_tree.insert(
                "",
                "end",
                values=(str(chip.get("kind") or ""), str(chip.get("value") or "")),
            )
            self._logbook_chip_item_to_payload[iid] = dict(chip)
        children = self.logbook_chip_tree.get_children()
        if children:
            first = children[0]
            self.logbook_chip_tree.selection_set(first)
            self.logbook_chip_tree.focus(first)
            self._selected_logbook_chip_item_id = first

    def _refresh_logbook_info_panel(self, feed_item: dict | None) -> None:
        if not hasattr(self, "logbook_info_tree"):
            return
        self.logbook_info_tree.delete(*self.logbook_info_tree.get_children())
        rows = build_logbook_info_rows(feed_item)
        if not rows:
            self.logbook_info_tree.insert("", "end", values=("Info", "Brak wybranego zdarzenia"))
            return
        for row in rows[:20]:
            label = str((row or {}).get("label") or "").strip() or "-"
            value = str((row or {}).get("value") or "").strip() or "-"
            self.logbook_info_tree.insert("", "end", values=(label, value))

    def _refresh_logbook_summary_panel(self, feed_items: list[dict]) -> None:
        snapshot = build_logbook_summary_snapshot(feed_items or [])
        total_events = int(snapshot.get("total_events") or 0)
        if total_events <= 0:
            self.logbook_summary_var.set("Brak danych dla aktualnego filtra.")
            return
        class_counts = snapshot.get("class_counts") or {}
        class_parts = []
        for name in _LOGBOOK_FEED_CLASS_ORDER:
            count = int(class_counts.get(name) or 0)
            if count > 0:
                class_parts.append(f"{name}: {count}")
        classes_text = " | ".join(class_parts[:5])
        if len(class_parts) > 5:
            classes_text += " | ..."
        self.logbook_summary_var.set(
            "\n".join(
                [
                    (
                        f"Eventy: {total_events} | Skoki: {int(snapshot.get('jump_count') or 0)} | "
                        f"Ladowania: {int(snapshot.get('landing_count') or 0)} | Dockowania: {int(snapshot.get('dock_count') or 0)} | "
                        f"Neutron: {int(snapshot.get('neutron_boosts') or 0)}"
                    ),
                    (
                        f"Incydenty hull: {int(snapshot.get('hull_incidents') or 0)} | "
                        f"Interdiction: {int(snapshot.get('interdictions') or 0)} | "
                        f"Ucieczki: {int(snapshot.get('interdiction_escapes') or 0)}"
                    ),
                    (
                        f"UC: {int(snapshot.get('uc_sold_cr') or 0)} cr | "
                        f"Vista: {int(snapshot.get('vista_sold_cr') or 0)} cr | "
                        f"Razem: {int(snapshot.get('total_sold_cr') or 0)} cr"
                    ),
                    (f"Klasy: {classes_text}" if classes_text else "Klasy: -"),
                ]
            )
        )

    def _selected_logbook_chip(self) -> dict | None:
        if not self._selected_logbook_chip_item_id:
            return None
        payload = self._logbook_chip_item_to_payload.get(self._selected_logbook_chip_item_id)
        return dict(payload) if isinstance(payload, dict) else None

    def _on_logbook_chip_selected(self, _event=None) -> None:
        selected = self.logbook_chip_tree.selection()
        self._selected_logbook_chip_item_id = selected[0] if selected else None

    def _on_logbook_chip_context_menu(self, event) -> None:
        row_id = self.logbook_chip_tree.identify_row(event.y)
        if row_id:
            self.logbook_chip_tree.selection_set(row_id)
            self.logbook_chip_tree.focus(row_id)
            self._selected_logbook_chip_item_id = row_id
        if not self._selected_logbook_chip():
            return
        try:
            self._logbook_chip_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._logbook_chip_context_menu.grab_release()

    def _on_logbook_context_menu(self, event) -> None:
        row_id = self.logbook_feed_tree.identify_row(event.y)
        if row_id:
            self.logbook_feed_tree.selection_set(row_id)
            self.logbook_feed_tree.focus(row_id)
            self._selected_logbook_item_id = row_id
        feed_item = self._selected_logbook_item()
        if not feed_item:
            return
        self._sync_logbook_feed_context_menu_state(feed_item)
        try:
            self._logbook_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._logbook_context_menu.grab_release()

    def _sync_logbook_feed_context_menu_state(self, feed_item: dict | None = None) -> None:
        item = dict(feed_item or self._selected_logbook_item() or {})
        raw_event = item.get("raw_event")
        has_entry_mapping = False
        if isinstance(raw_event, dict):
            try:
                has_entry_mapping = isinstance(build_mvp_entry_draft(raw_event), dict)
            except Exception:
                has_entry_mapping = False
        try:
            state_entry = "normal" if has_entry_mapping else "disabled"
            # 0: save, 1: save+edit, 3: append existing (after separator)
            self._logbook_context_menu.entryconfigure(0, state=state_entry)
            self._logbook_context_menu.entryconfigure(1, state=state_entry)
            self._logbook_context_menu.entryconfigure(3, state=state_entry)
        except Exception:
            log_event_throttled(
                "logbook.feed_context_menu.state_sync",
                2000,
                "WARN",
                "Logbook: failed to sync feed context menu enabled states",
            )

    def _selected_logbook_item(self) -> dict | None:
        if not self._selected_logbook_item_id:
            return None
        item = self._logbook_item_to_payload.get(self._selected_logbook_item_id)
        return dict(item) if isinstance(item, dict) else None

    def _show_system_on_map(self, system_name: Any, *, status_var: tk.StringVar, source: str) -> bool:
        target = str(system_name or "").strip()
        if not target:
            status_var.set("Brak systemu do pokazania na mapie.")
            return False
        try:
            self.sub_notebook.select(self.tab_map)
        except Exception:
            log_event_throttled(
                "logbook.show_on_map.select_subtab",
                2000,
                "WARN",
                "Logbook: failed to switch to map subtab",
            )
            status_var.set("Nie udalo sie otworzyc zakladki Mapa.")
            return False
        try:
            callback = getattr(self.tab_map, "focus_system_by_name_external", None)
            if not callable(callback):
                status_var.set("Mapa nie obsluguje akcji 'Pokaz na mapie'.")
                return False
            result = callback(target, center=True)
        except Exception:
            log_event_throttled(
                "logbook.show_on_map.focus_system",
                2000,
                "WARN",
                "Logbook: map focus callback failed",
            )
            status_var.set("Nie udalo sie pokazac systemu na mapie.")
            return False
        if bool(isinstance(result, dict) and result.get("ok")):
            status_var.set(f"Pokazano na mapie: {target}")
            return True
        reason = str((result or {}).get("reason") or "").strip()
        status_var.set(
            f"Nie znaleziono systemu na mapie: {target}" + (f" ({reason})" if reason else "")
        )
        return False

    def _entry_patch_from_dialog_data(self, data: dict) -> dict:
        return {
            "title": str(data.get("title") or "").strip(),
            "body": str(data.get("content") or "").strip(),
            "location": self._build_location_from_dialog(data),
        }

    def _edit_entry_by_id(self, entry_id: str) -> bool:
        entry = self.repository.get_entry(entry_id)
        if not entry:
            return False
        data = self._open_entry_dialog(initial=entry)
        if not data:
            return False
        patch = self._entry_patch_from_dialog_data(data)
        self.repository.update_entry(entry_id, patch)
        self._selected_entry_id = entry_id
        self._refresh_entries()
        return True

    def _build_draft_from_selected_logbook_item(self) -> tuple[dict, dict] | tuple[None, None]:
        feed_item = self._selected_logbook_item()
        if not feed_item:
            self.logbook_status_var.set("Wybierz event z feedu Logbook.")
            return None, None
        raw_event = feed_item.get("raw_event")
        if not isinstance(raw_event, dict):
            self.logbook_status_var.set("Brak surowego eventu Journal dla tej pozycji.")
            return None, None
        draft = build_mvp_entry_draft(raw_event)
        if not isinstance(draft, dict):
            event_name = str(feed_item.get("event_name") or "").strip() or "unknown"
            self.logbook_status_var.set(
                f"Event {event_name} nie ma jeszcze mapowania MVP do Entry."
            )
            return None, None
        return feed_item, draft

    def _save_selected_logbook_as_entry(self, *, edit_after: bool) -> None:
        feed_item, draft = self._build_draft_from_selected_logbook_item()
        if not draft:
            return
        try:
            created = self.repository.create_entry(draft)
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        created_id = str(created.get("id"))
        self._selected_entry_id = created_id
        self._refresh_categories()
        self._refresh_entries()

        if edit_after:
            try:
                edited = self._edit_entry_by_id(created_id)
            except EntryValidationError as exc:
                messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
                return
            if edited:
                self.logbook_status_var.set("Wpis utworzony i zaktualizowany.")
            else:
                self.logbook_status_var.set("Wpis utworzony. Edycje anulowano.")
        else:
            summary = str((feed_item or {}).get("summary") or "").strip()
            self.logbook_status_var.set(f"Utworzono wpis z eventu: {summary or '-'}")

    def _pick_existing_entry_id(self) -> str | None:
        entries = self.repository.list_entries(sort="updated_desc", limit=300)
        if not entries:
            self.logbook_status_var.set("Brak wpisow do uzupelnienia.")
            return None

        dialog = tk.Toplevel(self)
        dialog.title("Wybierz wpis docelowy")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        selected_id: dict[str, str | None] = {"value": None}

        listbox = tk.Listbox(
            dialog,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            selectbackground=COLOR_FG,
            selectforeground=COLOR_BG,
            relief="flat",
            exportselection=False,
        )
        listbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))

        entry_ids: list[str] = []
        for entry in entries:
            entry_id = str(entry.get("id"))
            entry_ids.append(entry_id)
            title = str(entry.get("title") or "-")
            system = str((entry.get("location") or {}).get("system_name") or "-")
            updated = _format_ts(str(entry.get("updated_at") or ""))
            listbox.insert("end", f"{title} | {system} | {updated}")

        if entry_ids:
            listbox.selection_set(0)
            listbox.activate(0)

        buttons = tk.Frame(dialog, bg=COLOR_BG)
        buttons.grid(row=1, column=0, sticky="e", padx=10, pady=(0, 10))

        def _confirm() -> None:
            selected = listbox.curselection()
            if not selected:
                return
            index = int(selected[0])
            if 0 <= index < len(entry_ids):
                selected_id["value"] = entry_ids[index]
            dialog.destroy()

        def _cancel() -> None:
            dialog.destroy()

        tk.Button(
            buttons,
            text="Wybierz",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=_confirm,
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            buttons,
            text="Anuluj",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=_cancel,
        ).pack(side="left")

        listbox.bind("<Double-1>", lambda _e: _confirm())
        self.wait_window(dialog)
        return selected_id["value"]

    def _append_selected_logbook_to_existing_entry(self) -> None:
        _feed_item, draft = self._build_draft_from_selected_logbook_item()
        if not draft:
            return

        target_id = self._selected_entry_id or self._pick_existing_entry_id()
        if not target_id:
            return
        existing = self.repository.get_entry(target_id)
        if not existing:
            self.logbook_status_var.set("Nie znaleziono wpisu docelowego.")
            return

        event_name = str((draft.get("source") or {}).get("event_name") or "JournalEvent")
        event_time = _format_ts(str((draft.get("source") or {}).get("event_time") or ""))
        draft_location = draft.get("location") or {}
        append_lines = [
            f"[{event_time}] {event_name}",
            str(draft.get("body") or "").strip(),
        ]
        append_block = "\n".join(line for line in append_lines if line)

        current_body = str(existing.get("body") or "").rstrip()
        if current_body:
            new_body = f"{current_body}\n\n---\n{append_block}"
        else:
            new_body = append_block

        location_patch: dict[str, object] = {}
        existing_location = existing.get("location") or {}
        for key in ("system_name", "station_name", "body_name"):
            if not existing_location.get(key) and draft_location.get(key):
                location_patch[key] = draft_location.get(key)

        patch: dict[str, object] = {"body": new_body}
        if location_patch:
            patch["location"] = location_patch

        try:
            self.repository.update_entry(target_id, patch)
            self.repository.add_tags(target_id, list(draft.get("tags") or []))
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        self._selected_entry_id = target_id
        self._refresh_entries()
        self.logbook_status_var.set("Event dopisany do istniejacego wpisu.")

    def _load_saved_categories(self) -> list[str]:
        if not os.path.exists(self._category_store_path):
            return list(self.DEFAULT_CATEGORIES)
        try:
            with open(self._category_store_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, list):
                return list(self.DEFAULT_CATEGORIES)
            out = []
            seen = set()
            for item in data:
                text = str(item or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                out.append(text)
            return out or list(self.DEFAULT_CATEGORIES)
        except Exception:
            return list(self.DEFAULT_CATEGORIES)

    def _save_saved_categories(self) -> None:
        try:
            directory = os.path.dirname(os.path.abspath(self._category_store_path))
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            with open(self._category_store_path, "w", encoding="utf-8") as handle:
                json.dump(self._saved_categories, handle, ensure_ascii=False, indent=2)
        except Exception:
            self.status_var.set("Nie udalo sie zapisac listy kategorii.")

    def _load_ui_state(self) -> None:
        try:
            ui_state = config.get_ui_state(default={})
            journal_state = ui_state.get("journal") if isinstance(ui_state, dict) else {}
            if not isinstance(journal_state, dict):
                journal_state = {}

            filters = journal_state.get("filters")
            if isinstance(filters, dict):
                text = str(filters.get("text") or "").strip()
                if text:
                    self.filter_text_var.set(text)

                date_from = str(filters.get("date_from") or "").strip()
                if date_from:
                    self.filter_date_from_var.set(date_from)

                date_to = str(filters.get("date_to") or "").strip()
                if date_to:
                    self.filter_date_to_var.set(date_to)

                tag_mode = str(filters.get("tag_mode") or "").strip().upper()
                if tag_mode in {"ALL", "ANY"}:
                    self.filter_tag_mode_var.set(tag_mode)

                pinned_only = filters.get("pinned_only")
                if pinned_only is not None:
                    self.filter_pinned_only_var.set(bool(pinned_only))

                sort_label = str(filters.get("sort") or "").strip()
                valid_sorts = {"Najnowsze", "Najstarsze", "System A-Z", "Tytul A-Z"}
                if sort_label in valid_sorts:
                    self.sort_var.set(sort_label)

                raw_tags = filters.get("tags")
                if isinstance(raw_tags, list):
                    self._selected_filter_tags = {
                        str(raw_tag or "").strip().lower()
                        for raw_tag in raw_tags
                        if str(raw_tag or "").strip()
                    }

            selected_category = str(journal_state.get("selected_category") or "").strip()
            if selected_category:
                self._selected_category = selected_category

            subtab_key = str(journal_state.get("active_subtab_key") or "").strip().lower()
            if subtab_key in {"entries", "feed", "map"}:
                self._pending_subtab_key = subtab_key

            map_state = journal_state.get("map")
            if isinstance(map_state, dict):
                self._pending_map_ui_state = dict(map_state)
        except Exception:
            log_event_throttled(
                "logbook.ui_state.load",
                3000,
                "WARN",
                "Logbook: failed to load persisted UI state",
            )

    def _resolve_active_subtab_key(self) -> str:
        try:
            selected = str(self.sub_notebook.select() or "")
        except Exception:
            return str(self._pending_subtab_key or "entries")
        if selected == str(self.tab_map):
            return "map"
        if selected == str(self.tab_feed):
            return "feed"
        return "entries"

    def _restore_subtab_from_ui_state(self) -> None:
        if self._pending_subtab_key == "map":
            try:
                self.sub_notebook.select(self.tab_map)
            except Exception:
                log_event_throttled(
                    "logbook.subtab.restore.map",
                    3000,
                    "WARN",
                    "Logbook: failed to restore subtab 'map'",
                )
            return
        if self._pending_subtab_key == "feed":
            try:
                self.sub_notebook.select(self.tab_feed)
            except Exception:
                log_event_throttled(
                    "logbook.subtab.restore.feed",
                    3000,
                    "WARN",
                    "Logbook: failed to restore subtab 'feed'",
                )
            return
        try:
            self.sub_notebook.select(self.tab_entries)
        except Exception:
            log_event_throttled(
                "logbook.subtab.restore.entries",
                3000,
                "WARN",
                "Logbook: failed to restore subtab 'entries'",
            )

    def _persist_ui_state(self) -> None:
        if bool(getattr(self, "_ui_state_suppress_persist", False)):
            return
        try:
            map_state: dict[str, Any] = {}
            try:
                exporter = getattr(self.tab_map, "export_persisted_ui_state", None)
                if callable(exporter):
                    out = exporter()
                    if isinstance(out, dict):
                        map_state = dict(out)
            except Exception:
                log_event_throttled(
                    "logbook.map_ui_state.export",
                    3000,
                    "WARN",
                    "Logbook: failed to export map UI state for persistence",
                )
                map_state = {}
            config.update_ui_state(
                {
                    "journal": {
                        "active_subtab_key": self._resolve_active_subtab_key(),
                        "selected_category": str(self._selected_category or _CATEGORY_ALL),
                        "filters": {
                            "text": str(self.filter_text_var.get() or "").strip(),
                            "date_from": str(self.filter_date_from_var.get() or "").strip(),
                            "date_to": str(self.filter_date_to_var.get() or "").strip(),
                            "tag_mode": str(self.filter_tag_mode_var.get() or "ALL").upper(),
                            "tags": sorted(self._selected_filter_tags),
                            "pinned_only": bool(self.filter_pinned_only_var.get()),
                            "sort": str(self.sort_var.get() or "Najnowsze"),
                        },
                        "map": map_state,
                    }
                }
            )
        except Exception:
            log_event_throttled(
                "logbook.ui_state.persist",
                3000,
                "WARN",
                "Logbook: failed to persist UI state",
            )

    def _on_subtab_changed(self, _event=None) -> None:
        try:
            if self._resolve_active_subtab_key() == "map":
                callback = getattr(self.tab_map, "on_parent_map_subtab_activated", None)
                if callable(callback):
                    callback()
        except Exception:
            log_event_throttled(
                "logbook.subtab_changed.map_activate",
                3000,
                "WARN",
                "Logbook: map subtab activation callback failed",
            )
        self._persist_ui_state()

    def _on_filters_changed(self) -> None:
        self._sync_pinboard_button_label()
        self._persist_ui_state()
        self._refresh_entries()

    def notify_playerdb_updated(self, payload: dict | None = None) -> None:
        try:
            callback = getattr(self.tab_map, "notify_playerdb_updated", None)
            if callable(callback):
                callback(payload)
        except Exception:
            log_event_throttled(
                "logbook.playerdb_updated.notify",
                2000,
                "WARN",
                "Logbook: failed to notify map tab about playerdb update",
            )

    def _set_filter_tag_display(self) -> None:
        if not self._selected_filter_tags:
            self.filter_tag_var.set(f"Wszystkie ({self.filter_tag_mode_var.get()})")
            return
        tags = sorted(self._selected_filter_tags)
        head = ", ".join(tags[:3])
        if len(tags) > 3:
            head += ", ..."
        self.filter_tag_var.set(f"{head} ({self.filter_tag_mode_var.get()})")

    @staticmethod
    def _point_inside_widget(widget: tk.Widget, x_root: int, y_root: int) -> bool:
        try:
            left = int(widget.winfo_rootx())
            top = int(widget.winfo_rooty())
            right = left + int(widget.winfo_width())
            bottom = top + int(widget.winfo_height())
            return left <= int(x_root) <= right and top <= int(y_root) <= bottom
        except Exception:
            return False

    def _close_active_popover(self) -> None:
        popover = self._active_popover
        self._active_popover = None
        self._active_popover_anchor = None
        self._active_popover_opened_at = 0.0
        if popover is not None:
            try:
                if popover.winfo_exists():
                    popover.destroy()
            except Exception:
                log_event_throttled(
                    "logbook.popover.destroy",
                    3000,
                    "WARN",
                    "Logbook: failed to destroy active popover",
                )

    def _on_global_click_maybe_close_popover(self, event) -> None:
        popover = self._active_popover
        if popover is None:
            return
        if (time.monotonic() - float(self._active_popover_opened_at)) < 0.18:
            return
        try:
            if not popover.winfo_exists():
                self._active_popover = None
                self._active_popover_anchor = None
                return
        except Exception:
            self._active_popover = None
            self._active_popover_anchor = None
            return

        x_root = int(getattr(event, "x_root", -1))
        y_root = int(getattr(event, "y_root", -1))
        if self._point_inside_widget(popover, x_root, y_root):
            return

        anchor = self._active_popover_anchor
        if anchor is not None and self._point_inside_widget(anchor, x_root, y_root):
            return

        self._close_active_popover()

    def _open_popover(self, anchor_widget: tk.Widget, builder) -> None:
        self._close_active_popover()

        popover = tk.Frame(self, bg=COLOR_BG, bd=1, relief="solid", highlightthickness=0)
        builder(popover)
        popover.update_idletasks()
        x = int(anchor_widget.winfo_rootx() - self.winfo_rootx())
        y = int(anchor_widget.winfo_rooty() - self.winfo_rooty() + anchor_widget.winfo_height() + 2)
        popover.place(x=x, y=y)
        popover.lift()

        self._active_popover = popover
        self._active_popover_anchor = anchor_widget
        self._active_popover_opened_at = time.monotonic()
        popover.bind("<Escape>", lambda _event: self._close_active_popover())

    def _on_filter_date_from_click(self, _event=None):
        self.after_idle(lambda: self._open_date_filter_popover("from", self.entry_filter_date_from))
        return "break"

    def _on_filter_date_to_click(self, _event=None):
        self.after_idle(lambda: self._open_date_filter_popover("to", self.entry_filter_date_to))
        return "break"

    def _open_date_filter_popover(self, which: str, anchor_widget: tk.Widget) -> None:
        date_var = self.filter_date_from_var if which == "from" else self.filter_date_to_var
        current_text = str(date_var.get() or "").strip()

        today = datetime.now()
        default_date = today
        try:
            if current_text and current_text.lower() not in {"forever", "dzisiaj", "today"}:
                default_date = datetime.strptime(current_text, "%Y-%m-%d")
        except Exception:
            default_date = today

        year_var = tk.IntVar(value=int(default_date.year))
        month_var = tk.IntVar(value=int(default_date.month))
        day_var = tk.IntVar(value=int(default_date.day))

        def _builder(frame: tk.Frame) -> None:
            title = "Data Od" if which == "from" else "Data Do"
            tk.Label(
                frame,
                text=title,
                bg=COLOR_BG,
                fg=COLOR_FG,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            ).grid(row=0, column=0, columnspan=4, sticky="ew", padx=8, pady=(6, 4))

            tk.Label(frame, text="Rok", bg=COLOR_BG, fg=COLOR_SEC).grid(
                row=1, column=0, sticky="w", padx=(8, 4)
            )
            tk.Label(frame, text="Msc", bg=COLOR_BG, fg=COLOR_SEC).grid(
                row=1, column=1, sticky="w", padx=(0, 4)
            )
            tk.Label(frame, text="Dzien", bg=COLOR_BG, fg=COLOR_SEC).grid(
                row=1, column=2, sticky="w"
            )

            tk.Spinbox(
                frame,
                from_=2000,
                to=3300,
                textvariable=year_var,
                width=6,
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                insertbackground=COLOR_FG,
                relief="flat",
            ).grid(row=2, column=0, sticky="w", padx=(8, 4), pady=(0, 6))
            tk.Spinbox(
                frame,
                from_=1,
                to=12,
                textvariable=month_var,
                width=4,
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                insertbackground=COLOR_FG,
                relief="flat",
            ).grid(row=2, column=1, sticky="w", padx=(0, 4), pady=(0, 6))
            tk.Spinbox(
                frame,
                from_=1,
                to=31,
                textvariable=day_var,
                width=4,
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                insertbackground=COLOR_FG,
                relief="flat",
            ).grid(row=2, column=2, sticky="w", pady=(0, 6))

            actions = tk.Frame(frame, bg=COLOR_BG)
            actions.grid(row=3, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8))

            def _set_today() -> None:
                now = datetime.now()
                year_var.set(int(now.year))
                month_var.set(int(now.month))
                day_var.set(int(now.day))

            def _apply_date() -> None:
                try:
                    parsed = datetime(int(year_var.get()), int(month_var.get()), int(day_var.get()))
                    date_var.set(parsed.strftime("%Y-%m-%d"))
                except Exception:
                    self.status_var.set("Niepoprawna data filtra.")
                    return
                self._close_active_popover()
                self._persist_ui_state()
                self._refresh_entries()

            def _clear_or_default() -> None:
                if which == "from":
                    date_var.set("forever")
                else:
                    date_var.set(_today_date_text())
                self._close_active_popover()
                self._persist_ui_state()
                self._refresh_entries()

            tk.Button(
                actions,
                text="Dzisiaj",
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                command=_set_today,
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                actions,
                text="Domyslne",
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                command=_clear_or_default,
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                actions,
                text="Zastosuj",
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                command=_apply_date,
            ).pack(side="left")

        self._open_popover(anchor_widget, _builder)

    def _on_tags_filter_click(self, _event=None):
        self.after_idle(self._open_tags_filter_popover)
        return "break"

    def _open_tags_filter_popover(self) -> None:
        available_tags = self._collect_available_tags()
        selected = set(self._selected_filter_tags)
        for tag in list(selected):
            if tag not in available_tags:
                available_tags.append(tag)
        available_tags.sort()
        mode_var = tk.StringVar(value=str(self.filter_tag_mode_var.get() or "ALL").upper())

        def _builder(frame: tk.Frame) -> None:
            tk.Label(
                frame,
                text="Filtr tagow",
                bg=COLOR_BG,
                fg=COLOR_FG,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(6, 4))

            mode_row = tk.Frame(frame, bg=COLOR_BG)
            mode_row.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))

            tk.Label(mode_row, text="Tryb:", bg=COLOR_BG, fg=COLOR_SEC).pack(side="left", padx=(0, 6))
            tk.Radiobutton(
                mode_row,
                text="ALL",
                value="ALL",
                variable=mode_var,
                bg=COLOR_BG,
                fg=COLOR_FG,
                selectcolor=COLOR_ACCENT,
                activebackground=COLOR_BG,
                activeforeground=COLOR_FG,
            ).pack(side="left", padx=(0, 6))
            tk.Radiobutton(
                mode_row,
                text="ANY",
                value="ANY",
                variable=mode_var,
                bg=COLOR_BG,
                fg=COLOR_FG,
                selectcolor=COLOR_ACCENT,
                activebackground=COLOR_BG,
                activeforeground=COLOR_FG,
            ).pack(side="left")

            checks_frame = tk.Frame(frame, bg=COLOR_BG)
            checks_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 4))
            checks_frame.columnconfigure(0, weight=1)
            checks_frame.columnconfigure(1, weight=1)
            checks_frame.columnconfigure(2, weight=1)

            tag_vars: dict[str, tk.BooleanVar] = {}
            if available_tags:
                for idx, tag in enumerate(available_tags):
                    row = idx // 3
                    col = idx % 3
                    var = tk.BooleanVar(value=tag in selected)
                    tag_vars[tag] = var
                    tk.Checkbutton(
                        checks_frame,
                        text=tag,
                        variable=var,
                        bg=COLOR_BG,
                        fg=COLOR_FG,
                        selectcolor=COLOR_ACCENT,
                        activebackground=COLOR_BG,
                        activeforeground=COLOR_FG,
                        anchor="w",
                    ).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=(0, 2))
            else:
                tk.Label(
                    checks_frame,
                    text="Brak tagow w lokalnej bazie wpisow.",
                    bg=COLOR_BG,
                    fg=COLOR_SEC,
                    anchor="w",
                ).grid(row=0, column=0, columnspan=3, sticky="w")

            actions = tk.Frame(frame, bg=COLOR_BG)
            actions.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))

            def _select_all() -> None:
                for var in tag_vars.values():
                    var.set(True)

            def _clear_all() -> None:
                for var in tag_vars.values():
                    var.set(False)

            def _apply() -> None:
                self._selected_filter_tags = {
                    tag for tag, enabled in tag_vars.items() if bool(enabled.get())
                }
                mode = str(mode_var.get() or "ALL").upper()
                self.filter_tag_mode_var.set("ANY" if mode == "ANY" else "ALL")
                self._set_filter_tag_display()
                self._close_active_popover()
                self._persist_ui_state()
                self._refresh_entries()

            tk.Button(
                actions,
                text="Wszystkie",
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                command=_select_all,
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                actions,
                text="Wyczysc",
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                command=_clear_all,
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                actions,
                text="Zastosuj",
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                command=_apply,
            ).pack(side="left")

        self._open_popover(self.entry_filter_tags, _builder)

    def _sync_pinboard_button_label(self) -> None:
        if not hasattr(self, "btn_pinboard_toggle"):
            return
        enabled = bool(self.filter_pinned_only_var.get())
        self.btn_pinboard_toggle.configure(text=f"Pinboard: {'ON' if enabled else 'OFF'}")

    def _toggle_pinboard_filter(self) -> None:
        self.filter_pinned_only_var.set(not bool(self.filter_pinned_only_var.get()))
        self._sync_pinboard_button_label()
        self._persist_ui_state()
        self._refresh_entries()

    def _on_category_selected(self, _event=None) -> None:
        selection = self.category_list.curselection()
        if not selection:
            self._selected_category = _CATEGORY_ALL
        else:
            display = self.category_list.get(selection[0])
            self._selected_category = self._category_display_to_path.get(display, _CATEGORY_ALL)
        self._persist_ui_state()
        self._refresh_entries()

    def _refresh_categories(self) -> None:
        all_entries = self.repository.list_entries(sort="title_az")
        counts: dict[str, int] = {}
        total = 0
        for entry in all_entries:
            total += 1
            category = str(entry.get("category_path") or "").strip()
            if not category:
                continue
            counts[category] = counts.get(category, 0) + 1

        for base in self._saved_categories:
            counts.setdefault(base, 0)

        current = self._selected_category
        self.category_list.delete(0, "end")
        self._category_display_to_path.clear()

        all_display = f"{_CATEGORY_ALL} ({total})"
        self.category_list.insert("end", all_display)
        self._category_display_to_path[all_display] = _CATEGORY_ALL

        for category in sorted(counts.keys(), key=lambda x: x.lower()):
            display = f"{category} ({counts.get(category, 0)})"
            self.category_list.insert("end", display)
            self._category_display_to_path[display] = category

        target = current if current in counts or current == _CATEGORY_ALL else _CATEGORY_ALL
        self._selected_category = target
        for idx in range(self.category_list.size()):
            display = self.category_list.get(idx)
            if self._category_display_to_path.get(display) == target:
                self.category_list.selection_clear(0, "end")
                self.category_list.selection_set(idx)
                self.category_list.activate(idx)
                break

    def _build_repo_filters(self) -> dict | None:
        filters: dict[str, object] = {}
        text = self.filter_text_var.get().strip()
        if text:
            filters["text"] = text

        tags = sorted(self._selected_filter_tags)
        if tags:
            filters["tags"] = tags
            mode = str(self.filter_tag_mode_var.get() or "ALL").strip().upper()
            filters["tags_mode"] = "any" if mode == "ANY" else "all"

        date_from_text = self.filter_date_from_var.get().strip()
        date_to_text = self.filter_date_to_var.get().strip()
        try:
            from_norm = date_from_text.lower()
            to_norm = date_to_text.lower()

            if not from_norm or from_norm in {"forever", "od zawsze"}:
                date_from = None
            elif from_norm in {"today", "dzisiaj"}:
                date_from = _to_iso_date(_today_date_text(), end_of_day=False)
            else:
                date_from = _to_iso_date(date_from_text, end_of_day=False)

            if not to_norm:
                date_to = _to_iso_date(_today_date_text(), end_of_day=True)
            elif to_norm in {"today", "dzisiaj"}:
                date_to = _to_iso_date(_today_date_text(), end_of_day=True)
            elif to_norm in {"forever", "bez limitu"}:
                date_to = None
            else:
                date_to = _to_iso_date(date_to_text, end_of_day=True)
        except ValueError:
            self.status_var.set("Niepoprawny format daty. Użyj YYYY-MM-DD.")
            return None

        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to
        if bool(self.filter_pinned_only_var.get()):
            filters["is_pinned"] = True
        return filters

    def _sort_to_repo_value(self) -> str:
        mapping = {
            "Najnowsze": "updated_desc",
            "Najstarsze": "created_asc",
            "System A-Z": "system_az",
            "Tytul A-Z": "title_az",
        }
        return mapping.get(self.sort_var.get(), "updated_desc")

    def _refresh_entries(self) -> None:
        filters = self._build_repo_filters()
        if filters is None:
            return
        if self._selected_category and self._selected_category != _CATEGORY_ALL:
            filters["category_path_prefix"] = self._selected_category

        try:
            entries = self.repository.list_entries(filters=filters, sort=self._sort_to_repo_value())
        except EntryValidationError as exc:
            self.status_var.set(str(exc))
            return

        previous_selected = self._selected_entry_id
        self._entry_item_to_id.clear()
        self.entries_tree.delete(*self.entries_tree.get_children())
        self._selected_entry_id = None

        for index, entry in enumerate(entries):
            location = entry.get("location") or {}
            tags = ", ".join(entry.get("tags") or [])
            iid = self.entries_tree.insert(
                "",
                "end",
                values=(
                    entry.get("title") or "-",
                    _format_ts(str(entry.get("updated_at") or "")),
                    location.get("system_name") or "-",
                    tags or "-",
                    (entry.get("source") or {}).get("kind") or "-",
                ),
            )
            self._entry_item_to_id[iid] = str(entry.get("id"))
            if previous_selected and str(entry.get("id")) == previous_selected:
                self.entries_tree.selection_set(iid)
                self.entries_tree.focus(iid)
                self._selected_entry_id = previous_selected
            if index == 0 and self._selected_entry_id is None:
                self.entries_tree.selection_set(iid)
                self.entries_tree.focus(iid)
                self._selected_entry_id = str(entry.get("id"))

        pinned_only = bool(self.filter_pinned_only_var.get())
        if not entries:
            if pinned_only:
                self.status_var.set("Pinboard: brak przypietych wpisow.")
            else:
                self.status_var.set("Brak wpisow dla aktualnych filtrow.")
        else:
            if pinned_only:
                self.status_var.set(f"Pinboard: {len(entries)} wpisow przypietych.")
            else:
                self.status_var.set(f"Wpisow: {len(entries)}")
        self._refresh_preview()
        self._refresh_categories()

    def _on_entry_selected(self, _event=None) -> None:
        selected = self.entries_tree.selection()
        if not selected:
            self._selected_entry_id = None
        else:
            self._selected_entry_id = self._entry_item_to_id.get(selected[0])
        self._refresh_preview()

    def _selected_entry(self) -> dict | None:
        return self.repository.get_entry(self._selected_entry_id or "")

    def _collect_available_categories(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for category in list(self._saved_categories):
            normalized = str(category or "").strip().strip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)

        for entry in self.repository.list_entries(sort="title_az"):
            normalized = str(entry.get("category_path") or "").strip().strip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)

        out.sort(key=lambda value: value.lower())
        return out

    def _collect_available_tags(self) -> list[str]:
        out: list[str] = []
        for entry in self.repository.list_entries(sort="updated_desc"):
            for raw_tag in list(entry.get("tags") or []):
                normalized = str(raw_tag or "").strip().lower()
                if not normalized:
                    continue
                out.append(normalized)
        return _merge_default_tags(out)

    def _ensure_category_saved(self, category: str) -> None:
        normalized = str(category or "").strip().strip("/")
        if not normalized:
            return
        if normalized not in self._saved_categories:
            self._saved_categories.append(normalized)
            self._saved_categories.sort(key=lambda value: value.lower())
            self._save_saved_categories()

    def _open_entry_metadata_dialog(self, entry: dict) -> dict | None:
        dialog = tk.Toplevel(self)
        dialog.title("Edytuj metadane wpisu")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        current_category = str(entry.get("category_path") or "").strip().strip("/")
        categories = self._collect_available_categories()
        if current_category and current_category not in categories:
            categories.append(current_category)
            categories.sort(key=lambda value: value.lower())

        tk.Label(
            dialog,
            text="Kategoria:",
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))

        category_combo = ttk.Combobox(dialog, values=categories, state="normal")
        category_combo.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        category_combo.set(current_category)

        tags_box = tk.LabelFrame(
            dialog,
            text="Tagi (lokalne + domyslne)",
            bg=COLOR_BG,
            fg=COLOR_FG,
            relief="solid",
            borderwidth=1,
            labelanchor="nw",
        )
        tags_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))
        tags_box.columnconfigure(0, weight=1)
        tags_box.columnconfigure(1, weight=1)
        tags_box.columnconfigure(2, weight=1)

        current_tags = [
            str(raw_tag or "").strip().lower()
            for raw_tag in list(entry.get("tags") or [])
            if str(raw_tag or "").strip()
        ]
        tags = _merge_default_tags(self._collect_available_tags() + current_tags)

        tag_vars: dict[str, tk.BooleanVar] = {}
        tag_checks: dict[str, tk.Checkbutton] = {}

        def _place_tag_checkbox(tag: str) -> None:
            idx = len(tag_checks)
            row = idx // 3
            col = idx % 3
            var = tk.BooleanVar(value=tag in current_tags)
            chk = tk.Checkbutton(
                tags_box,
                text=tag,
                variable=var,
                bg=COLOR_BG,
                fg=COLOR_FG,
                selectcolor=COLOR_ACCENT,
                activebackground=COLOR_BG,
                activeforeground=COLOR_FG,
                anchor="w",
            )
            chk.grid(row=row, column=col, sticky="w", padx=(8, 8), pady=(4, 2))
            tag_vars[tag] = var
            tag_checks[tag] = chk

        empty_label = tk.Label(
            tags_box,
            text="Brak tagow w bazie. Dodaj pierwszy tag recznie.",
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
        )
        empty_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 4))

        for tag in tags:
            _place_tag_checkbox(tag)

        if tag_checks:
            empty_label.grid_remove()

        add_row = tk.Frame(dialog, bg=COLOR_BG)
        add_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))
        add_row.columnconfigure(0, weight=1)

        tk.Label(
            add_row,
            text="Nowy tag:",
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        tag_input = tk.Entry(
            add_row,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
        )
        tag_input.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        def _add_manual_tag(_event=None) -> None:
            value = str(tag_input.get() or "").strip().lower()
            if not value:
                return
            if value in tag_vars:
                tag_vars[value].set(True)
                tag_input.delete(0, "end")
                return
            _place_tag_checkbox(value)
            empty_label.grid_remove()
            tag_input.delete(0, "end")

        tk.Button(
            add_row,
            text="Dodaj tag",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=_add_manual_tag,
        ).grid(row=1, column=1, sticky="w", padx=(8, 0))
        tag_input.bind("<Return>", _add_manual_tag)

        buttons = tk.Frame(dialog, bg=COLOR_BG)
        buttons.grid(row=4, column=0, sticky="e", padx=10, pady=(0, 10))

        result: dict[str, dict] = {"value": {}}

        def _confirm() -> None:
            category = str(category_combo.get() or "").strip().strip("/")
            if not category:
                messagebox.showerror(
                    "Edycja metadanych",
                    "Kategoria nie moze byc pusta.",
                    parent=dialog,
                )
                return
            selected_tags = sorted(
                [tag for tag, enabled in tag_vars.items() if bool(enabled.get())]
            )
            result["value"] = {
                "category_path": category,
                "tags": selected_tags,
            }
            dialog.destroy()

        def _cancel() -> None:
            dialog.destroy()

        tk.Button(
            buttons,
            text="Zapisz",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=_confirm,
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            buttons,
            text="Anuluj",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=_cancel,
        ).pack(side="left")

        dialog.bind("<Escape>", lambda _event: _cancel())
        self.wait_window(dialog)
        value = result.get("value")
        return dict(value) if isinstance(value, dict) and value else None

    def _rebuild_entry_move_menu(self, entry: dict) -> None:
        if not hasattr(self, "_entry_move_menu"):
            return
        self._entry_move_menu.delete(0, "end")

        current_category = str(entry.get("category_path") or "").strip()
        categories = self._collect_available_categories()
        for category in categories:
            label = category
            if category == current_category:
                label = f"{category} (aktualna)"
            self._entry_move_menu.add_command(
                label=label,
                command=lambda target=category: self._move_selected_entry_to_category(target),
            )

        if categories:
            self._entry_move_menu.add_separator()
        self._entry_move_menu.add_command(
            label="Nowa kategoria...",
            command=self._prompt_new_category_for_selected_entry,
        )

    def _on_entry_context_menu(self, event) -> None:
        if event.widget == self.entries_tree:
            row_id = self.entries_tree.identify_row(event.y)
            if row_id:
                self.entries_tree.selection_set(row_id)
                self.entries_tree.focus(row_id)
                self._selected_entry_id = self._entry_item_to_id.get(row_id)
                self._refresh_preview()

        entry = self._selected_entry()
        if not entry:
            return

        if hasattr(self, "_entry_context_menu"):
            pin_label = "Odepnij" if bool(entry.get("is_pinned")) else "Przypnij"
            self._entry_context_menu.entryconfigure(1, label=pin_label)
            self._rebuild_entry_move_menu(entry)
            try:
                self._entry_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._entry_context_menu.grab_release()

    def _refresh_preview(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.preview_title_var.set("Brak wybranego wpisu")
            self.preview_meta_var.set("-")
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")
            self.preview_text.configure(state="disabled")
            self.btn_toggle_pin.configure(text="Przypnij")
            return

        location = entry.get("location") or {}
        source = entry.get("source") or {}
        tags = ", ".join(entry.get("tags") or [])
        meta = (
            f"Kategoria: {entry.get('category_path') or '-'}\n"
            f"Zrodlo: {source.get('kind') or '-'} | Aktualizacja: {_format_ts(str(entry.get('updated_at') or ''))}\n"
            f"System: {location.get('system_name') or '-'} | Stacja: {location.get('station_name') or '-'} | Body: {location.get('body_name') or '-'}\n"
            f"Tagi: {tags or '-'}"
        )
        self.preview_title_var.set(str(entry.get("title") or "-"))
        self.preview_meta_var.set(meta)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", str(entry.get("body") or ""))
        self.preview_text.configure(state="disabled")
        self.btn_toggle_pin.configure(text="Odepnij" if bool(entry.get("is_pinned")) else "Przypnij")

    def _resolve_runtime_state(self):
        candidate = getattr(self.app, "state", None)
        return candidate if candidate is not None else app_state

    def _emit_ppm_callout(
        self,
        raw_text: str,
        *,
        message_id: str,
        dedup_key: str,
        context: dict | None = None,
    ) -> None:
        text = str(raw_text or "").strip()
        if not text:
            return
        try:
            from logic.insight_dispatcher import emit_insight
        except Exception:
            log_event_throttled(
                "logbook.ppm_callout.import_emit_insight",
                3000,
                "WARN",
                "Logbook: failed to import insight dispatcher for PPM callout",
            )
            return
        payload = dict(context or {})
        payload["raw_text"] = text
        try:
            emit_insight(
                text,
                gui_ref=self.app,
                message_id=message_id,
                source="logbook_ppm",
                event_type="UI_CONTEXT_ACTION",
                context=payload,
                priority="P2_NORMAL",
                dedup_key=str(dedup_key or "").strip() or None,
                cooldown_scope="entity",
                cooldown_seconds=8.0,
            )
        except Exception:
            log_event_throttled(
                "logbook.ppm_callout.emit",
                3000,
                "WARN",
                f"Logbook: failed to emit PPM callout ({message_id})",
            )
            return

    def _get_smart_context(self) -> tuple[str, str, str]:
        state = self._resolve_runtime_state()
        system = str(getattr(state, "current_system", "") or "")
        station = str(getattr(state, "current_station", "") or "")
        body = str(getattr(state, "current_body", "") or "")
        target_body = station or body
        lat = getattr(state, "latitude", None)
        lon = getattr(state, "longitude", None)
        coords = ""
        if lat is not None and lon is not None:
            coords = f"Lat: {lat}, Lon: {lon}"
        return system, target_body, coords

    def _default_category_for_new_entry(self) -> str:
        if self._selected_category and self._selected_category != _CATEGORY_ALL:
            return self._selected_category
        if self._saved_categories:
            return self._saved_categories[0]
        return _CATEGORY_FALLBACK

    # Map (F21 PPM) callbacks
    def map_get_available_entry_categories(self) -> list[str]:
        categories = [str(v).strip() for v in self._collect_available_categories() if str(v).strip()]
        if not categories:
            categories = [self._default_category_for_new_entry()]
        return categories

    def map_create_entry_for_system(
        self,
        system_name: str,
        *,
        category_path: str | None = None,
        edit_after: bool = False,
    ) -> dict:
        system = str(system_name or "").strip()
        if not system:
            return {"ok": False, "reason": "system_missing"}

        category = str(category_path or "").strip() or self._default_category_for_new_entry()
        payload = {
            "category_path": category,
            "title": f"Mapa: {system}",
            "body": "",
            "location": {
                "system_name": system,
                "station_name": None,
                "body_name": None,
                "coords_lat": None,
                "coords_lon": None,
            },
            "source": {"kind": "map_ppm"},
        }
        try:
            created = self.repository.create_entry(payload)
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return {"ok": False, "reason": "validation_error"}

        created_id = str(created.get("id") or "").strip()
        self._selected_entry_id = created_id or self._selected_entry_id
        self._refresh_categories()
        self._refresh_entries()

        edited = False
        if bool(edit_after) and created_id:
            try:
                edited = bool(self._edit_entry_by_id(created_id))
            except EntryValidationError as exc:
                messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
                return {"ok": False, "reason": "edit_validation_error", "entry_id": created_id}

        self.status_var.set("Wpis z mapy zapisany." if not edit_after else ("Wpis z mapy utworzony i zaktualizowany." if edited else "Wpis z mapy utworzony. Edycje anulowano."))
        return {
            "ok": True,
            "entry_id": created_id,
            "system_name": system,
            "category_path": category,
            "edited": bool(edited),
        }

    def _open_entry_dialog(self, *, initial: dict | None = None):
        if initial:
            system = (initial.get("location") or {}).get("system_name") or ""
            body = (initial.get("location") or {}).get("body_name") or ""
            lat = (initial.get("location") or {}).get("coords_lat")
            lon = (initial.get("location") or {}).get("coords_lon")
            coords = f"Lat: {lat}, Lon: {lon}" if lat is not None and lon is not None else ""
        else:
            system, body, coords = self._get_smart_context()

        dialog = AddEntryDialog(self, system=system, body=body, coords=coords)
        if initial:
            dialog.entry_title.delete(0, "end")
            dialog.entry_title.insert(0, str(initial.get("title") or ""))
            dialog.text_content.delete("1.0", "end")
            dialog.text_content.insert("1.0", str(initial.get("body") or ""))
        self.wait_window(dialog)
        return getattr(dialog, "result_data", None)

    def _build_location_from_dialog(self, data: dict) -> dict:
        body_text = str(data.get("body") or "").strip()
        station_name = _maybe_station_name(body_text)
        lat, lon = _parse_lat_lon(str(data.get("coords") or ""))
        return {
            "system_name": str(data.get("system") or "").strip() or None,
            "station_name": station_name,
            "body_name": body_text or None,
            "coords_lat": lat,
            "coords_lon": lon,
        }

    def _prompt_text(self, title: str, prompt: str, *, initial: str = "") -> str | None:
        value = simpledialog.askstring(title, prompt, initialvalue=initial, parent=self)
        if value is None:
            return None
        return str(value).strip()

    def _choose_template_kind(self) -> str | None:
        choice = messagebox.askyesnocancel(
            "Nowy wpis z szablonu",
            (
                "Wybierz szablon:\n\n"
                "Tak  -> Mining Hotspot\n"
                "Nie  -> Trade Route\n"
                "Anuluj -> przerwij"
            ),
            parent=self,
        )
        if choice is None:
            return None
        return "mining_hotspot" if choice else "trade_route"

    def _collect_template_fields(self, template_id: str) -> dict | None:
        state = self._resolve_runtime_state()
        system_default = str(getattr(state, "current_system", "") or "")
        station_default = str(getattr(state, "current_station", "") or "")
        body_default = str(getattr(state, "current_body", "") or "")

        if template_id == "mining_hotspot":
            commodity = self._prompt_text(
                "Mining Hotspot",
                "Commodity (np. Platinum):",
            )
            if commodity is None:
                return None
            body_name = self._prompt_text(
                "Mining Hotspot",
                "Body/Ring:",
                initial=body_default,
            )
            if body_name is None:
                return None
            system_name = self._prompt_text(
                "Mining Hotspot",
                "System:",
                initial=system_default,
            )
            if system_name is None:
                return None
            ring_type = self._prompt_text(
                "Mining Hotspot",
                "Ring type (opcjonalnie):",
            )
            if ring_type is None:
                return None
            hotspot_strength = self._prompt_text(
                "Mining Hotspot",
                "Hotspot strength (opcjonalnie):",
            )
            if hotspot_strength is None:
                return None
            res_nearby = self._prompt_text(
                "Mining Hotspot",
                "RES nearby (opcjonalnie):",
            )
            if res_nearby is None:
                return None
            notes = self._prompt_text(
                "Mining Hotspot",
                "Notatki (opcjonalnie):",
            )
            if notes is None:
                return None
            return {
                "commodity": commodity,
                "body_name": body_name,
                "system_name": system_name,
                "ring_type": ring_type,
                "hotspot_strength": hotspot_strength,
                "res_nearby": res_nearby,
                "notes": notes,
            }

        if template_id == "trade_route":
            from_system = self._prompt_text(
                "Trade Route",
                "From system (opcjonalnie):",
                initial=system_default,
            )
            if from_system is None:
                return None
            from_station = self._prompt_text(
                "Trade Route",
                "From station:",
                initial=station_default,
            )
            if from_station is None:
                return None
            to_system = self._prompt_text(
                "Trade Route",
                "To system (opcjonalnie):",
            )
            if to_system is None:
                return None
            to_station = self._prompt_text(
                "Trade Route",
                "To station:",
            )
            if to_station is None:
                return None
            profit_per_t = self._prompt_text(
                "Trade Route",
                "Profit per ton (cr/t, opcjonalnie):",
            )
            if profit_per_t is None:
                return None
            pad_size = self._prompt_text(
                "Trade Route",
                "Pad size (S/M/L, opcjonalnie):",
                initial="L",
            )
            if pad_size is None:
                return None
            distance_ls = self._prompt_text(
                "Trade Route",
                "Distance LS (opcjonalnie):",
            )
            if distance_ls is None:
                return None
            permit_required = messagebox.askyesnocancel(
                "Trade Route",
                "Czy trasa wymaga permitu?\n\nTak = wymagany, Nie = niewymagany",
                parent=self,
            )
            if permit_required is None:
                return None
            notes = self._prompt_text(
                "Trade Route",
                "Notatki (opcjonalnie):",
            )
            if notes is None:
                return None
            return {
                "from_system": from_system,
                "from_station": from_station,
                "to_system": to_system,
                "to_station": to_station,
                "profit_per_t": profit_per_t,
                "pad_size": pad_size,
                "distance_ls": distance_ls,
                "permit_required": permit_required,
                "notes": notes,
            }
        return None

    def _add_entry_from_template(self) -> None:
        template_id = self._choose_template_kind()
        if not template_id:
            self.status_var.set("Tworzenie wpisu z szablonu anulowane.")
            return
        fields = self._collect_template_fields(template_id)
        if fields is None:
            self.status_var.set("Tworzenie wpisu z szablonu anulowane.")
            return
        try:
            payload = build_template_entry(template_id, fields)
            created = self.repository.create_entry(payload)
        except EntryTemplateError as exc:
            messagebox.showerror("Szablon wpisu", str(exc), parent=self)
            return
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        self._selected_entry_id = str(created.get("id"))
        self.status_var.set(f"Wpis z szablonu zapisany: {created.get('title') or '-'}")
        self._refresh_categories()
        self._refresh_entries()

    def _add_entry(self) -> None:
        data = self._open_entry_dialog()
        if not data:
            return
        category_path = self._default_category_for_new_entry()
        payload = {
            "category_path": category_path,
            "title": str(data.get("title") or "").strip(),
            "body": str(data.get("content") or "").strip(),
            "location": self._build_location_from_dialog(data),
            "source": {"kind": "manual"},
        }
        try:
            created = self.repository.create_entry(payload)
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        self._selected_entry_id = str(created.get("id"))
        self.status_var.set("Wpis zapisany.")
        self._refresh_categories()
        self._refresh_entries()

    def _edit_selected_entry(self) -> None:
        entry = self.repository.get_entry(self._selected_entry_id or "")
        if not entry:
            self.status_var.set("Wybierz wpis do edycji.")
            return
        data = self._open_entry_dialog(initial=entry)
        if not data:
            return

        patch = {
            "title": str(data.get("title") or "").strip(),
            "body": str(data.get("content") or "").strip(),
            "location": self._build_location_from_dialog(data),
        }
        try:
            self.repository.update_entry(str(entry.get("id")), patch)
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        self.status_var.set("Wpis zaktualizowany.")
        self._refresh_entries()

    def _delete_selected_entry(self) -> None:
        entry = self.repository.get_entry(self._selected_entry_id or "")
        if not entry:
            self.status_var.set("Wybierz wpis do usuniecia.")
            return
        if not messagebox.askyesno(
            "Usun wpis",
            f"Czy na pewno usunac wpis:\n{entry.get('title') or '-'} ?",
            parent=self,
        ):
            return
        self.repository.delete_entry(str(entry.get("id")))
        self._selected_entry_id = None
        self.status_var.set("Wpis usuniety.")
        self._refresh_categories()
        self._refresh_entries()

    def _add_category(self) -> None:
        value = simpledialog.askstring("Nowa kategoria", "Podaj nazwe/sciezke kategorii:", parent=self)
        if value is None:
            return
        category = str(value or "").strip().strip("/")
        if not category:
            self.status_var.set("Pusta nazwa kategorii - anulowano.")
            return
        if (
            self._selected_category
            and self._selected_category != _CATEGORY_ALL
            and "/" not in category
        ):
            category = f"{self._selected_category}/{category}"

        self._ensure_category_saved(category)
        self._selected_category = category
        self.status_var.set("Kategoria dodana. Dodaj wpis, aby pojawila sie w bazie.")
        self._refresh_categories()
        self._refresh_entries()

    def _move_selected_entry_to_category(self, category_path: str) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return

        target_category = str(category_path or "").strip().strip("/")
        if not target_category:
            self.status_var.set("Docelowa kategoria jest pusta.")
            return
        if target_category == str(entry.get("category_path") or "").strip():
            self.status_var.set("Wpis jest juz w tej kategorii.")
            return

        try:
            self.repository.update_entry(str(entry.get("id")), {"category_path": target_category})
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        self._ensure_category_saved(target_category)
        self._selected_entry_id = str(entry.get("id"))
        self.status_var.set(f"Przeniesiono wpis do kategorii: {target_category}")
        self._refresh_categories()
        self._refresh_entries()

    def _prompt_new_category_for_selected_entry(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return

        initial = str(entry.get("category_path") or "").strip()
        value = simpledialog.askstring(
            "Przenies wpis",
            "Podaj nazwe/sciezke kategorii docelowej:",
            initialvalue=initial,
            parent=self,
        )
        if value is None:
            return
        target_category = str(value or "").strip().strip("/")
        if not target_category:
            self.status_var.set("Pusta nazwa kategorii - anulowano.")
            return
        self._move_selected_entry_to_category(target_category)

    def _edit_selected_entry_metadata(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return

        metadata = self._open_entry_metadata_dialog(entry)
        if not metadata:
            return

        patch = {
            "category_path": str(metadata.get("category_path") or "").strip().strip("/"),
            "tags": list(metadata.get("tags") or []),
        }
        if not patch["category_path"]:
            self.status_var.set("Kategoria nie moze byc pusta.")
            return

        try:
            self.repository.update_entry(str(entry.get("id")), patch)
        except EntryValidationError as exc:
            messagebox.showerror("Walidacja wpisu", str(exc), parent=self)
            return

        self._ensure_category_saved(str(patch["category_path"]))
        self._selected_entry_id = str(entry.get("id"))
        self.status_var.set("Metadane wpisu zaktualizowane.")
        self._refresh_categories()
        self._refresh_entries()

    def _set_target_from_selected_entry(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return

        resolved_target = resolve_entry_nav_target_typed(entry)
        if not resolved_target:
            self.status_var.set("Brak celu nawigacji w metadanych wpisu.")
            return
        target_kind, target = resolved_target

        try:
            app_state.set_route_intent(target, source="journal.entries")
        except Exception:
            log_event_throttled(
                "logbook.entry.set_route_intent",
                2000,
                "WARN",
                "Logbook: failed to set route intent from selected entry",
            )
            self.status_var.set("Nie udalo sie ustawic celu nawigacji.")
            return

        if pyperclip is not None:
            try:
                pyperclip.copy(target)
            except Exception:
                log_event_throttled(
                    "logbook.entry.copy_target",
                    2000,
                    "WARN",
                    "Logbook: failed to copy entry navigation target to clipboard",
                )
        self.status_var.set(f"Ustawiono cel [{target_kind}]: {target}")
        self._emit_ppm_callout(
            f"Ustawiono cel nawigacji: {target}.",
            message_id="MSG.PPM_SET_TARGET",
            dedup_key=f"ppm_set_target:{target}",
            context={"target": target},
        )

    def _show_selected_entry_on_map(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return
        location = entry.get("location") or {}
        system_name = str((location or {}).get("system_name") or "").strip()
        if not system_name:
            self.status_var.set("Brak systemu w metadanych wpisu.")
            return
        self._show_system_on_map(system_name, status_var=self.status_var, source="entry")

    def _set_target_from_selected_logbook_event(self) -> None:
        feed_item = self._selected_logbook_item()
        if not feed_item:
            self.logbook_status_var.set("Wybierz event z feedu Logbook.")
            return
        target = str(resolve_logbook_nav_target(feed_item) or "").strip()
        if not target:
            self.logbook_status_var.set("Brak celu nawigacji w wybranym evencie.")
            return
        try:
            app_state.set_route_intent(target, source="journal.logbook.event")
        except Exception:
            log_event_throttled(
                "logbook.feed_event.set_route_intent",
                2000,
                "WARN",
                "Logbook: failed to set route intent from logbook event",
            )
            self.logbook_status_var.set("Nie udalo sie ustawic celu z eventu.")
            return
        self.logbook_status_var.set(f"Ustawiono cel z eventu: {target}")

    def _show_selected_logbook_event_on_map(self) -> None:
        feed_item = self._selected_logbook_item()
        if not feed_item:
            self.logbook_status_var.set("Wybierz event z feedu Logbook.")
            return
        resolved = resolve_logbook_nav_target_typed(feed_item)
        system_name = str(feed_item.get("system_name") or "").strip()
        if not system_name and resolved:
            kind, target = resolved
            if str(kind).upper() == "SYSTEM":
                system_name = str(target or "").strip()
        if not system_name:
            self.logbook_status_var.set("Brak systemu w wybranym evencie.")
            return
        self._show_system_on_map(system_name, status_var=self.logbook_status_var, source="feed_event")

    def _set_target_from_selected_logbook_chip(self) -> None:
        chip = self._selected_logbook_chip()
        if not chip:
            self.logbook_status_var.set("Wybierz chip SYSTEM/STATION.")
            return
        target = str(resolve_chip_nav_target(chip) or "").strip()
        if not target:
            self.logbook_status_var.set("Ten chip nie moze ustawic celu nawigacji.")
            return
        try:
            app_state.set_route_intent(target, source="journal.logbook.chip")
        except Exception:
            log_event_throttled(
                "logbook.chip.set_route_intent",
                2000,
                "WARN",
                "Logbook: failed to set route intent from chip",
            )
            self.logbook_status_var.set("Nie udalo sie ustawic celu z chipa.")
            return
        self.logbook_status_var.set(f"Ustawiono cel z chipa: {target}")

    def _copy_selected_logbook_chip(self) -> None:
        chip = self._selected_logbook_chip()
        if not chip:
            self.logbook_status_var.set("Wybierz chip do skopiowania.")
            return
        target = str(resolve_chip_nav_target(chip) or "").strip()
        if not target:
            self.logbook_status_var.set("Ten chip nie ma wartosci nawigacyjnej.")
            return
        if pyperclip is not None:
            try:
                pyperclip.copy(target)
            except Exception:
                log_event_throttled(
                    "logbook.chip.copy",
                    2000,
                    "WARN",
                    "Logbook: failed to copy chip target to clipboard",
                )
        self.logbook_status_var.set(f"Skopiowano chip: {target}")

    def _show_selected_logbook_chip_on_map(self) -> None:
        chip = self._selected_logbook_chip()
        if not chip:
            self.logbook_status_var.set("Wybierz chip SYSTEM/STATION.")
            return
        kind = str((chip or {}).get("kind") or "").strip().upper()
        system_name = ""
        if kind == "SYSTEM":
            system_name = str((chip or {}).get("value") or "").strip()
        else:
            feed_item = self._selected_logbook_item()
            system_name = str((feed_item or {}).get("system_name") or "").strip()
        if not system_name:
            self.logbook_status_var.set("Ten chip nie wskazuje systemu na mapie.")
            return
        self._show_system_on_map(system_name, status_var=self.logbook_status_var, source="chip")

    def _toggle_pin_selected_entry(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return
        pinned = bool(entry.get("is_pinned"))
        self.repository.pin_entry(str(entry.get("id")), not pinned)
        self.status_var.set("Zmieniono status przypiecia.")
        if pinned:
            text = "Odpięłam wpis."
        else:
            text = "Przypięłam wpis."
        self._emit_ppm_callout(
            text,
            message_id="MSG.PPM_PIN_ACTION",
            dedup_key=f"ppm_pin:{entry.get('id')}",
            context={"entry_id": str(entry.get("id") or "")},
        )
        self._refresh_entries()

    def _copy_selected_system(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.status_var.set("Wybierz wpis.")
            return
        system_name = str((entry.get("location") or {}).get("system_name") or "").strip()
        if not system_name:
            self.status_var.set("Brak systemu w metadanych wpisu.")
            return
        if pyperclip is not None:
            try:
                pyperclip.copy(system_name)
            except Exception:
                log_event_throttled(
                    "logbook.entry.copy_system",
                    2000,
                    "WARN",
                    "Logbook: failed to copy entry system to clipboard",
                )
        self.status_var.set(f"Skopiowano system: {system_name}")
        self._emit_ppm_callout(
            f"Skopiowano system: {system_name}.",
            message_id="MSG.PPM_COPY_SYSTEM",
            dedup_key=f"ppm_copy_system:{system_name}",
            context={"system": system_name},
        )
