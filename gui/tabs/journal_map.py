from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from app.state import app_state
from logic.personal_map_data_provider import MapDataProvider

COLOR_BG = "#0b0c10"
COLOR_FG = "#ff7100"
COLOR_SEC = "#c5c6c7"
COLOR_ACCENT = "#1f2833"
COLOR_GRID = "#222a35"
COLOR_NODE = "#ff7100"
COLOR_EDGE = "#4b5563"
COLOR_HILITE = "#ffd166"
COLOR_SELECTED_RING = "#ffffff"
COLOR_SELECTED_RING_SHADOW = "#111827"
COLOR_CURRENT_RING = "#22c55e"
COLOR_STATION_LAYER = "#6ee7b7"
COLOR_TRADE_LAYER = "#60a5fa"
COLOR_CASHIN_LAYER = "#f472b6"


@dataclass
class _MapNode:
    key: str
    system_name: str
    x: float
    y: float
    z: float | None = None
    system_address: int | None = None
    system_id64: int | None = None
    source: str = "playerdb"
    confidence: str = "observed"
    freshness_ts: str = ""
    first_seen_ts: str = ""
    last_seen_ts: str = ""


@dataclass
class _MapEdge:
    key: str
    from_key: str
    to_key: str


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_iso_ts(value: Any) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _format_age_short(value: Any) -> str:
    dt = _parse_iso_ts(value)
    if dt is None:
        return "-"
    hours = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    if hours < 1.0:
        minutes = int(round(hours * 60.0))
        return f"{minutes}m"
    if hours < 24.0:
        return f"{hours:.1f}h"
    days = hours / 24.0
    if days < 7.0:
        return f"{days:.1f}d"
    return f"{int(round(days))}d"


def _max_age_for_freshness_filter(value: Any) -> timedelta | None:
    text = _as_text(value).lower()
    if not text or text in {"all", "any", "*"}:
        return None
    if "6h" in text:
        return timedelta(hours=6)
    if "24h" in text:
        return timedelta(hours=24)
    if "7d" in text or "7 d" in text:
        return timedelta(days=7)
    return None


class JournalMapTab(tk.Frame):
    """
    F20-2 shell zakladki mapy osadzonej w `Dziennik`.
    Zakres:
    - 3 panele (filtry / canvas / szczegoly)
    - canvas pan+zoom (dziala tez na pustych danych)
    - placeholder/stub przyciskow i paneli pod dalsze tickety F20-3..F20-6
    """

    def __init__(self, parent, app=None, data_provider: MapDataProvider | None = None, *args, **kwargs):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)
        self.app = app
        self.data_provider = data_provider or MapDataProvider()

        # View transform (world -> screen)
        self.view_scale: float = 1.0
        self.view_offset_x: float = 0.0
        self.view_offset_y: float = 0.0
        self._min_scale = 0.10
        self._max_scale = 6.0

        # Pan state
        self._pan_active = False
        self._pan_last_x = 0
        self._pan_last_y = 0

        # Render state (F20-2 shell with placeholder/simple dataset support)
        self._nodes: dict[str, _MapNode] = {}
        self._edges: list[_MapEdge] = []
        self._selected_node_key: str | None = None
        self._station_rows_by_iid: dict[str, dict[str, Any]] = {}
        self._node_layer_flags: dict[str, dict[str, Any]] = {}
        self._trade_highlight_node_keys: set[str] = set()
        self._trade_compare_rows: list[dict[str, Any]] = []
        self._travel_nodes_meta: dict[str, Any] = {}
        self._travel_edges_meta: dict[str, Any] = {}
        self._pending_after_ids: list[str] = []

        # Filters (UI shell)
        self.layer_travel_var = tk.BooleanVar(value=True)
        self.layer_stations_var = tk.BooleanVar(value=True)
        self.layer_trade_var = tk.BooleanVar(value=False)
        self.layer_cashin_var = tk.BooleanVar(value=False)
        self.time_range_var = tk.StringVar(value="30d")
        self.freshness_var = tk.StringVar(value="any")
        self.source_include_enriched_var = tk.BooleanVar(value=False)
        self.trade_compare_commodity_var = tk.StringVar(value="")
        self.map_status_var = tk.StringVar(value="Mapa gotowa (shell). Brak danych do renderu.")

        self._build_ui()
        self._bind_canvas()
        self._schedule_after(50, self.reset_view)
        self._schedule_after(90, self.reload_from_playerdb)

    def _schedule_after(self, delay_ms: int, callback) -> str:
        after_id = self.after(int(delay_ms), callback)
        try:
            self._pending_after_ids.append(str(after_id))
        except Exception:
            pass
        return str(after_id)

    def _cancel_pending_after_jobs(self) -> None:
        pending = list(getattr(self, "_pending_after_ids", []) or [])
        self._pending_after_ids = []
        for after_id in pending:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass

    def destroy(self) -> None:
        self._cancel_pending_after_jobs()
        super().destroy()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        # Left panel (filters)
        self.left_frame = tk.Frame(self, bg=COLOR_BG, width=300)
        self.left_frame.grid(row=0, column=0, sticky="nsw", padx=(10, 6), pady=(10, 6))
        self.left_frame.grid_propagate(False)
        self.left_frame.columnconfigure(0, weight=1)

        tk.Label(
            self.left_frame,
            text="Personal Galaxy Map",
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        layers_box = tk.LabelFrame(
            self.left_frame,
            text="Warstwy",
            bg=COLOR_BG,
            fg=COLOR_FG,
            bd=1,
            relief="groove",
            labelanchor="nw",
        )
        layers_box.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        for idx, (label, var) in enumerate(
            (
                ("Travel", self.layer_travel_var),
                ("Stations", self.layer_stations_var),
                ("Trade", self.layer_trade_var),
                ("Cash-In", self.layer_cashin_var),
            )
        ):
            chk = tk.Checkbutton(
                layers_box,
                text=label,
                variable=var,
                command=self._on_filter_changed,
                bg=COLOR_BG,
                fg=COLOR_FG,
                selectcolor=COLOR_ACCENT,
                activebackground=COLOR_BG,
                activeforeground=COLOR_FG,
            )
            chk.grid(row=idx // 2, column=idx % 2, sticky="w", padx=8, pady=4)

        filters_box = tk.LabelFrame(
            self.left_frame,
            text="Filtry",
            bg=COLOR_BG,
            fg=COLOR_FG,
            bd=1,
            relief="groove",
            labelanchor="nw",
        )
        filters_box.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        filters_box.columnconfigure(1, weight=1)

        tk.Label(filters_box, text="Zakres czasu:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 4)
        )
        time_combo = ttk.Combobox(
            filters_box,
            values=("7d", "30d", "all"),
            state="readonly",
            textvariable=self.time_range_var,
            width=10,
        )
        time_combo.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(6, 4))
        time_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filter_changed())

        tk.Label(filters_box, text="Freshness:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        freshness_combo = ttk.Combobox(
            filters_box,
            values=("<=6h", "<=24h", "<=7d", "any"),
            state="readonly",
            textvariable=self.freshness_var,
            width=10,
        )
        freshness_combo.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=4)
        freshness_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filter_changed())

        include_enriched_chk = tk.Checkbutton(
            filters_box,
            text="include enriched",
            variable=self.source_include_enriched_var,
            command=self._on_filter_changed,
            bg=COLOR_BG,
            fg=COLOR_FG,
            selectcolor=COLOR_ACCENT,
            activebackground=COLOR_BG,
            activeforeground=COLOR_FG,
        )
        include_enriched_chk.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 6))

        btn_box = tk.Frame(self.left_frame, bg=COLOR_BG)
        btn_box.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        btn_box.columnconfigure(0, weight=1)
        btn_box.columnconfigure(1, weight=1)

        self.btn_center_current = tk.Button(
            btn_box,
            text="Center on current system",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self.center_on_current_system,
        )
        self.btn_center_current.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_reset_zoom = tk.Button(
            btn_box,
            text="Reset zoom",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self.reset_view,
        )
        self.btn_reset_zoom.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.btn_export_placeholder = tk.Button(
            self.left_frame,
            text="Export view (png) [later]",
            bg=COLOR_ACCENT,
            fg=COLOR_SEC,
            relief="flat",
            state="disabled",
        )
        self.btn_export_placeholder.grid(row=4, column=0, sticky="ew")

        # Center panel (canvas)
        self.center_frame = tk.Frame(self, bg=COLOR_BG)
        self.center_frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=(10, 6))
        self.center_frame.columnconfigure(0, weight=1)
        self.center_frame.rowconfigure(0, weight=1)

        self.map_canvas = tk.Canvas(
            self.center_frame,
            bg=COLOR_BG,
            highlightthickness=1,
            highlightbackground=COLOR_ACCENT,
            relief="flat",
            cursor="arrow",
        )
        self.map_canvas.grid(row=0, column=0, sticky="nsew")

        # Right panel (details)
        self.right_frame = tk.Frame(self, bg=COLOR_BG, width=380)
        self.right_frame.grid(row=0, column=2, sticky="nse", padx=(6, 10), pady=(10, 6))
        self.right_frame.grid_propagate(False)
        self.right_frame.columnconfigure(0, weight=1)
        self.right_frame.rowconfigure(3, weight=1)
        self.right_frame.rowconfigure(6, weight=1)
        self.right_frame.rowconfigure(10, weight=1)

        tk.Label(
            self.right_frame,
            text="System details",
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.system_details_var = tk.StringVar(value="Brak wybranego systemu.")
        tk.Label(
            self.right_frame,
            textvariable=self.system_details_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
            wraplength=360,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 4))

        self.system_stations_tree = ttk.Treeview(
            self.right_frame,
            columns=("station", "type", "services"),
            show="headings",
            style="Treeview",
            height=6,
        )
        self.system_stations_tree.heading("station", text="Stacja")
        self.system_stations_tree.heading("type", text="Typ")
        self.system_stations_tree.heading("services", text="Uslugi")
        self.system_stations_tree.column("station", width=180, anchor="w")
        self.system_stations_tree.column("type", width=90, anchor="w")
        self.system_stations_tree.column("services", width=90, anchor="w")
        self.system_stations_tree.grid(row=2, column=0, sticky="nsew")
        self.system_stations_tree.bind("<<TreeviewSelect>>", self._on_station_tree_selected)

        tk.Label(
            self.right_frame,
            text="Station details",
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.station_details_var = tk.StringVar(value="Brak wybranej stacji.")
        tk.Label(
            self.right_frame,
            textvariable=self.station_details_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
            wraplength=360,
        ).grid(row=5, column=0, sticky="ew", pady=(2, 4))

        self.station_market_tree = ttk.Treeview(
            self.right_frame,
            columns=("ts", "items", "freshness"),
            show="headings",
            style="Treeview",
            height=5,
        )
        self.station_market_tree.heading("ts", text="Snapshot")
        self.station_market_tree.heading("items", text="Towary")
        self.station_market_tree.heading("freshness", text="Freshness")
        self.station_market_tree.column("ts", width=170, anchor="w")
        self.station_market_tree.column("items", width=70, anchor="e")
        self.station_market_tree.column("freshness", width=110, anchor="w")
        self.station_market_tree.grid(row=6, column=0, sticky="nsew")

        tk.Label(
            self.right_frame,
            text="Trade compare",
            bg=COLOR_BG,
            fg=COLOR_FG,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=7, column=0, sticky="w", pady=(8, 0))
        trade_ctl = tk.Frame(self.right_frame, bg=COLOR_BG)
        trade_ctl.grid(row=8, column=0, sticky="ew", pady=(2, 4))
        trade_ctl.columnconfigure(0, weight=1)
        self.trade_commodity_combo = ttk.Combobox(
            trade_ctl,
            textvariable=self.trade_compare_commodity_var,
            values=(),
            width=18,
        )
        self.trade_commodity_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.trade_commodity_combo.bind("<<ComboboxSelected>>", self._on_trade_commodity_changed)
        self.trade_commodity_combo.bind("<Return>", self._on_trade_commodity_changed)
        self.trade_highlight_btn = tk.Button(
            trade_ctl,
            text="Highlight",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            state="disabled",
            command=self._on_trade_highlight_clicked,
        )
        self.trade_highlight_btn.grid(row=0, column=1, sticky="e")

        self.trade_compare_tree = ttk.Treeview(
            self.right_frame,
            columns=("mode", "system", "station", "price", "age"),
            show="headings",
            style="Treeview",
            height=6,
        )
        for col, title, width, anchor in (
            ("mode", "Tryb", 50, "w"),
            ("system", "System", 120, "w"),
            ("station", "Stacja", 100, "w"),
            ("price", "Cena", 60, "e"),
            ("age", "Age", 50, "w"),
        ):
            self.trade_compare_tree.heading(col, text=title)
            self.trade_compare_tree.column(col, width=width, anchor=anchor)
        self.trade_compare_tree.grid(row=10, column=0, sticky="nsew")

        # Bottom status
        status = tk.Label(
            self,
            textvariable=self.map_status_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
        )
        status.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))

    def _bind_canvas(self) -> None:
        self.map_canvas.bind("<Configure>", self._on_canvas_configure)
        self.map_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.map_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.map_canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        # Linux compatibility (no-op on Windows if never fired)
        self.map_canvas.bind("<Button-4>", lambda e: self._on_canvas_mousewheel(_WheelShim(e, delta=120)))
        self.map_canvas.bind("<Button-5>", lambda e: self._on_canvas_mousewheel(_WheelShim(e, delta=-120)))
        self.map_canvas.tag_bind("map_node", "<ButtonPress-1>", self._on_canvas_node_click)
        self.map_canvas.tag_bind("map_node", "<Double-Button-1>", self._on_canvas_node_double_click)

    def _set_map_cursor(self, cursor_name: str) -> None:
        try:
            self.map_canvas.configure(cursor=str(cursor_name))
        except Exception:
            pass

    def _on_filter_changed(self) -> None:
        self.reload_from_playerdb()

    def set_graph_data(self, *, nodes: list[dict[str, Any]] | None = None, edges: list[dict[str, Any]] | None = None) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._selected_node_key = None
        for row in nodes or []:
            key = str(row.get("key") or row.get("system_address") or row.get("system_name") or "").strip()
            if not key:
                continue
            x = row.get("x")
            y = row.get("y")
            if x is None or y is None:
                continue
            try:
                node = _MapNode(
                    key=key,
                    system_name=str(row.get("system_name") or key),
                    x=float(x),
                    y=float(y),
                    z=self._safe_float(row.get("z")),
                    system_address=int(row["system_address"]) if row.get("system_address") is not None else None,
                    system_id64=int(row["system_id64"]) if row.get("system_id64") is not None else None,
                    source=str(row.get("source") or "playerdb"),
                    confidence=str(row.get("confidence") or "observed"),
                    freshness_ts=str(row.get("freshness_ts") or ""),
                    first_seen_ts=str(row.get("first_seen_ts") or ""),
                    last_seen_ts=str(row.get("last_seen_ts") or ""),
                )
            except Exception:
                continue
            self._nodes[key] = node
        for row in edges or []:
            from_key = str(row.get("from_key") or row.get("from") or "").strip()
            to_key = str(row.get("to_key") or row.get("to") or "").strip()
            key = str(row.get("key") or f"{from_key}->{to_key}")
            if not from_key or not to_key:
                continue
            self._edges.append(_MapEdge(key=key, from_key=from_key, to_key=to_key))
        self._redraw_scene()

    def _source_filter_mode(self) -> str:
        return "include_enriched" if bool(self.source_include_enriched_var.get()) else "observed_only"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _passes_freshness_filter(self, value: Any) -> bool:
        max_age = _max_age_for_freshness_filter(self.freshness_var.get())
        if max_age is None:
            return True
        dt = _parse_iso_ts(value)
        if dt is None:
            return False
        age = datetime.now(timezone.utc) - dt
        return age <= max_age

    def _filter_rows_by_freshness(
        self,
        rows: list[dict[str, Any]],
        *,
        ts_keys: tuple[str, ...] = ("freshness_ts", "last_seen_ts", "services_freshness_ts", "snapshot_ts"),
    ) -> list[dict[str, Any]]:
        max_age = _max_age_for_freshness_filter(self.freshness_var.get())
        if max_age is None:
            return [dict(r) for r in rows if isinstance(r, dict)]
        out: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            candidate_ts = ""
            for key in ts_keys:
                candidate_ts = _as_text(row.get(key))
                if candidate_ts:
                    break
            if self._passes_freshness_filter(candidate_ts):
                out.append(dict(row))
        return out

    def _node_key_from_row(self, row: dict[str, Any]) -> str:
        return _as_text(row.get("key") or row.get("system_address") or row.get("system_name"))

    def _compute_layer_flags_for_nodes(self, nodes_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        flags_by_key: dict[str, dict[str, Any]] = {}
        if not nodes_rows:
            return flags_by_key
        # MVP / F20-5: N+1 queries are acceptable for map prototype. We cache results per reload.
        for row in nodes_rows:
            if not isinstance(row, dict):
                continue
            key = self._node_key_from_row(row)
            if not key:
                continue
            system_address = row.get("system_address")
            system_name = _as_text(row.get("system_name"))
            try:
                station_rows, _meta = self.data_provider.get_stations_for_system(
                    system_address=int(system_address) if system_address is not None else None,
                    system_name=system_name or None,
                    limit=200,
                )
            except Exception:
                flags_by_key[key] = {
                    "has_station": False,
                    "has_market": False,
                    "has_cashin": False,
                    "stations_count": 0,
                    "error": True,
                }
                continue
            filtered = self._filter_rows_by_freshness(
                station_rows,
                ts_keys=("freshness_ts", "services_freshness_ts", "last_seen_ts"),
            )
            has_station = len(filtered) > 0
            has_market = any(bool((dict(r).get("services") or {}).get("has_market")) for r in filtered)
            has_cashin = any(
                bool((dict(r).get("services") or {}).get("has_uc"))
                or bool((dict(r).get("services") or {}).get("has_vista"))
                for r in filtered
            )
            flags_by_key[key] = {
                "has_station": bool(has_station),
                "has_market": bool(has_market),
                "has_cashin": bool(has_cashin),
                "stations_count": len(filtered),
                "error": False,
            }
        return flags_by_key

    def _travel_layout_from_system_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Travel-path layout (MVP default): sequence by last_seen/first_seen, rendered as readable serpentine path.
        ordered = sorted(
            [dict(r) for r in rows if isinstance(r, dict)],
            key=lambda r: (
                str(r.get("last_seen_ts") or r.get("first_seen_ts") or ""),
                str(r.get("system_name") or "").casefold(),
            ),
        )
        out: list[dict[str, Any]] = []
        step_x = 18.0
        step_y = 14.0
        row_len = 8
        for idx, row in enumerate(ordered):
            grid_row = idx // row_len
            grid_col = idx % row_len
            if grid_row % 2 == 1:
                grid_col = (row_len - 1) - grid_col
            wx = grid_col * step_x
            wy = grid_row * step_y
            # light jitter-free curve feel for sequential travel readability
            wy += math.sin(idx * 0.55) * 2.0
            item = dict(row)
            item["x"] = wx
            item["y"] = wy
            out.append(item)
        return out

    def _build_fallback_sequential_edges(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        ordered = sorted(
            [dict(r) for r in nodes if isinstance(r, dict)],
            key=lambda r: (
                str(r.get("last_seen_ts") or r.get("first_seen_ts") or ""),
                str(r.get("system_name") or "").casefold(),
            ),
        )
        prev_key: str | None = None
        for row in ordered:
            key = str(row.get("key") or row.get("system_address") or row.get("system_name") or "").strip()
            if not key:
                continue
            if prev_key and prev_key != key:
                out.append({"key": f"{prev_key}->{key}", "from_key": prev_key, "to_key": key, "source": "playerdb_sequential"})
            prev_key = key
        return out

    def _refresh_system_panel_stub(self) -> None:
        # F20-3 still keeps drilldown for next ticket, but provides useful summary.
        self.system_stations_tree.delete(*self.system_stations_tree.get_children())
        self.station_market_tree.delete(*self.station_market_tree.get_children())
        self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
        self._station_rows_by_iid.clear()
        self._trade_highlight_node_keys.clear()
        self._trade_compare_rows = []
        nodes_count = len(self._nodes)
        edges_count = len(self._edges)
        self.system_details_var.set(
            f"Travel layer: {nodes_count} systemow | {edges_count} krawedzi | "
            f"time={self.time_range_var.get()} | freshness={self.freshness_var.get()}"
        )
        self.station_details_var.set(
            "Wybierz system na mapie, aby zobaczyc stacje i snapshoty rynku."
        )
        self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
        self.trade_compare_tree.insert(
            "",
            "end",
            values=(
                "INFO",
                "-",
                "-",
                "-",
                f"warstwy: T={int(bool(self.layer_travel_var.get()))}/S={int(bool(self.layer_stations_var.get()))}/Tr={int(bool(self.layer_trade_var.get()))}/C={int(bool(self.layer_cashin_var.get()))}",
            ),
        )
        self._sync_trade_highlight_button_state()

    def reload_from_playerdb(self) -> dict[str, Any]:
        if not bool(self.layer_travel_var.get()):
            self.set_graph_data(nodes=[], edges=[])
            self._node_layer_flags = {}
            self._travel_nodes_meta = {"count": 0, "disabled": True}
            self._travel_edges_meta = {"count": 0, "disabled": True}
            self._refresh_system_panel_stub()
            self.map_status_var.set("Mapa: warstwa Travel jest wylaczona. Wlacz Travel, aby zobaczyc systemy.")
            return {"ok": True, "travel_enabled": False, "nodes": 0, "edges": 0}

        time_range = str(self.time_range_var.get() or "30d")
        source_filter = self._source_filter_mode()
        nodes_rows, nodes_meta = self.data_provider.get_system_nodes(time_range=time_range, source_filter=source_filter)
        edges_rows, edges_meta = self.data_provider.get_edges(time_range=time_range)
        nodes_rows = self._filter_rows_by_freshness(nodes_rows, ts_keys=("freshness_ts", "last_seen_ts", "first_seen_ts"))

        # F20-3 default renderer = travel-path layout; coords-view intentionally deferred.
        laid_out_nodes = self._travel_layout_from_system_rows(nodes_rows)
        if edges_rows:
            edges_final = edges_rows
            edges_mode = "provider"
        else:
            edges_final = self._build_fallback_sequential_edges(laid_out_nodes)
            edges_mode = "sequential_fallback"

        self._travel_nodes_meta = dict(nodes_meta or {})
        self._travel_edges_meta = dict(edges_meta or {})
        self._travel_edges_meta["render_mode"] = edges_mode
        self._node_layer_flags = self._compute_layer_flags_for_nodes(laid_out_nodes)

        self.set_graph_data(nodes=laid_out_nodes, edges=edges_final)
        self._refresh_system_panel_stub()
        self._refresh_trade_commodity_values()
        self._refresh_trade_compare_if_needed()

        count_nodes = len(self._nodes)
        count_edges = len(self._edges)
        status_reason = ""
        if edges_mode == "sequential_fallback":
            status_reason = " | krawedzie: fallback sekwencyjny (brak ingestu jumps)"
        layer_state = (
            f" | layers T={int(bool(self.layer_travel_var.get()))}"
            f"/S={int(bool(self.layer_stations_var.get()))}"
            f"/Tr={int(bool(self.layer_trade_var.get()))}"
            f"/C={int(bool(self.layer_cashin_var.get()))}"
        )
        if count_nodes <= 0:
            status_reason += " | brak danych po filtrach (time/freshness/source)"
        self.map_status_var.set(
            f"Mapa Travel: {count_nodes} systemow / {count_edges} krawedzi | "
            f"time={time_range} | freshness={self.freshness_var.get()} | source={source_filter}{status_reason}{layer_state}"
        )
        return {
            "ok": True,
            "travel_enabled": True,
            "nodes": count_nodes,
            "edges": count_edges,
            "edges_mode": edges_mode,
            "nodes_meta": dict(nodes_meta or {}),
            "edges_meta": dict(edges_meta or {}),
        }

    def _refresh_trade_commodity_values(self) -> None:
        try:
            values, _meta = self.data_provider.get_known_commodities(
                time_range=str(self.time_range_var.get() or "all"),
                freshness_filter=str(self.freshness_var.get() or "any"),
                limit=300,
            )
        except Exception:
            values = []
        current = _as_text(self.trade_compare_commodity_var.get())
        merged: list[str] = []
        seen_cf: set[str] = set()
        for item in [current, *list(values or [])]:
            text = _as_text(item)
            if not text:
                continue
            key = text.casefold()
            if key in seen_cf:
                continue
            seen_cf.add(key)
            merged.append(text)
        try:
            self.trade_commodity_combo["values"] = tuple(merged)
        except Exception:
            pass
        self._sync_trade_highlight_button_state()

    def _sync_trade_highlight_button_state(self) -> None:
        commodity = _as_text(self.trade_compare_commodity_var.get())
        state = "normal" if commodity else "disabled"
        try:
            self.trade_highlight_btn.configure(state=state)
        except Exception:
            pass

    def _on_trade_commodity_changed(self, _event=None):
        self._sync_trade_highlight_button_state()
        return None

    def _refresh_trade_compare_if_needed(self) -> None:
        commodity = _as_text(self.trade_compare_commodity_var.get())
        if not commodity:
            self._trade_highlight_node_keys.clear()
            self._trade_compare_rows = []
            self._redraw_scene()
            return
        self._run_trade_compare(commodity)

    def _on_trade_highlight_clicked(self) -> None:
        commodity = _as_text(self.trade_compare_commodity_var.get())
        if not commodity:
            self._sync_trade_highlight_button_state()
            return
        self._run_trade_compare(commodity)

    def _node_keys_for_system_name(self, system_name: Any) -> list[str]:
        target = _as_text(system_name).casefold()
        if not target:
            return []
        return [key for key, node in (self._nodes or {}).items() if _as_text(node.system_name).casefold() == target]

    def _run_trade_compare(self, commodity: str) -> dict[str, Any]:
        commodity_name = _as_text(commodity)
        self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
        self._trade_highlight_node_keys.clear()
        self._trade_compare_rows = []
        self._sync_trade_highlight_button_state()
        if not commodity_name:
            self.trade_compare_tree.insert("", "end", values=("INFO", "-", "-", "-", "wybierz towar"))
            self._redraw_scene()
            return {"ok": False, "reason": "missing_commodity"}

        time_range = str(self.time_range_var.get() or "all")
        freshness_filter = str(self.freshness_var.get() or "any")
        try:
            sell_rows, sell_meta = self.data_provider.get_top_prices(
                commodity_name,
                "sell",
                time_range=time_range,
                freshness_filter=freshness_filter,
                limit=5,
            )
            buy_rows, buy_meta = self.data_provider.get_top_prices(
                commodity_name,
                "buy",
                time_range=time_range,
                freshness_filter=freshness_filter,
                limit=5,
            )
        except Exception as exc:
            self.trade_compare_tree.insert("", "end", values=("ERR", "-", "-", "-", type(exc).__name__))
            self._redraw_scene()
            return {"ok": False, "reason": "provider_error"}

        rows_inserted = 0
        for mode_label, rows in (("SELL", sell_rows), ("BUY", buy_rows)):
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                self._trade_compare_rows.append(dict(row))
                system_name = _as_text(row.get("system_name")) or "-"
                station_name = _as_text(row.get("station_name")) or "-"
                price = int(row.get("price") or 0)
                age = _format_age_short(row.get("freshness_ts"))
                conf = _as_text(row.get("confidence")) or "observed"
                self.trade_compare_tree.insert(
                    "",
                    "end",
                    values=(mode_label, system_name, station_name, f"{price}", f"{age} | {conf}"),
                )
                for key in self._node_keys_for_system_name(system_name):
                    self._trade_highlight_node_keys.add(key)
                rows_inserted += 1

        if rows_inserted <= 0:
            self.trade_compare_tree.insert(
                "",
                "end",
                values=("INFO", "-", "-", "-", "brak danych po filtrach"),
            )
        self._redraw_scene()

        trade_layer_on = bool(self.layer_trade_var.get())
        suffix = "" if trade_layer_on else " (warstwa Trade wylaczona - highlight ukryty)"
        self.map_status_var.set(
            f"Mapa: Trade compare '{commodity_name}' | sell={len(sell_rows)} buy={len(buy_rows)} | "
            f"nodes_hilite={len(self._trade_highlight_node_keys)}{suffix}"
        )
        return {
            "ok": True,
            "commodity": commodity_name,
            "sell_count": len(sell_rows),
            "buy_count": len(buy_rows),
            "rows_inserted": rows_inserted,
            "highlight_nodes": len(self._trade_highlight_node_keys),
            "sell_meta": dict(sell_meta or {}),
            "buy_meta": dict(buy_meta or {}),
        }

    def _canvas_current_node_key(self) -> str | None:
        try:
            current = self.map_canvas.find_withtag("current")
            if not current:
                return None
            tags = self.map_canvas.gettags(current[0]) or ()
        except Exception:
            return None
        for tag in tags:
            text = str(tag)
            if text.startswith("node:"):
                key = text.split(":", 1)[1].strip()
                if key:
                    return key
        return None

    def _on_canvas_node_click(self, event=None):
        key = self._canvas_current_node_key()
        if not key:
            return None
        self._pan_active = False
        self._set_map_cursor("arrow")
        self.select_system_node(key)
        return "break"

    def _on_canvas_node_double_click(self, event=None):
        key = self._canvas_current_node_key()
        if not key:
            return None
        self._pan_active = False
        self._set_map_cursor("arrow")
        self.select_system_node(key)
        node = self._nodes.get(key)
        if node is not None:
            self._center_world_point(node.x, node.y)
            self._redraw_scene()
            self.map_status_var.set(f"Mapa: wycentrowano na systemie {node.system_name}.")
        return "break"

    def _services_label(self, row: dict[str, Any]) -> str:
        services = dict(row.get("services") or {})
        tokens: list[str] = []
        if bool(services.get("has_uc")):
            tokens.append("UC")
        if bool(services.get("has_vista")):
            tokens.append("Vista")
        if bool(services.get("has_market")):
            tokens.append("Mkt")
        return ",".join(tokens) if tokens else "-"

    def select_system_node(self, node_key: str) -> dict[str, Any]:
        key = _as_text(node_key)
        node = self._nodes.get(key)
        if node is None:
            return {"ok": False, "reason": "node_not_found", "node_key": key}

        self._selected_node_key = key
        self._redraw_scene()

        stations_rows, stations_meta = self.data_provider.get_stations_for_system(
            system_address=node.system_address,
            system_name=node.system_name,
        )
        stations_rows = self._filter_rows_by_freshness(
            stations_rows,
            ts_keys=("freshness_ts", "services_freshness_ts", "last_seen_ts"),
        )
        self._populate_system_details(node=node, stations_rows=stations_rows, stations_meta=stations_meta)
        if bool(self.layer_stations_var.get()):
            self._populate_station_list(stations_rows)
        else:
            self._populate_station_list([])
            self.station_details_var.set("Warstwa Stations jest wylaczona. Wlacz, aby zobaczyc stacje i snapshoty rynku.")

        # Auto-select first station for quick drilldown UX.
        children = self.system_stations_tree.get_children()
        if children:
            first_iid = str(children[0])
            try:
                self.system_stations_tree.selection_set(first_iid)
                self.system_stations_tree.focus(first_iid)
            except Exception:
                pass
            self._select_station_by_iid(first_iid)
        else:
            self.station_market_tree.delete(*self.station_market_tree.get_children())
            if bool(self.layer_stations_var.get()):
                self.station_details_var.set("Brak znanych stacji w playerdb dla wybranego systemu (po filtrach).")

        self.map_status_var.set(
            f"Mapa: wybrano system {node.system_name} | stacje={len(stations_rows)} | source=playerdb"
        )
        return {
            "ok": True,
            "node_key": key,
            "system_name": node.system_name,
            "stations_count": len(stations_rows),
            "stations_meta": dict(stations_meta or {}),
        }

    def _populate_system_details(
        self,
        *,
        node: _MapNode,
        stations_rows: list[dict[str, Any]],
        stations_meta: dict[str, Any] | None = None,
    ) -> None:
        lines = [
            f"System: {node.system_name}",
            f"Adres systemu: {node.system_address if node.system_address is not None else '-'}",
            f"SystemId64: {node.system_id64 if node.system_id64 is not None else '-'}",
            f"Coords: x={node.x:.1f}, y={node.y:.1f}, z={node.z:.1f}" if node.z is not None else f"Coords: x={node.x:.1f}, y={node.y:.1f}",
            f"Source: {node.source or 'playerdb'} | Confidence: {node.confidence or 'observed'}",
            f"Seen: first={node.first_seen_ts or '-'} | last={node.last_seen_ts or '-'}",
            f"Stacje (playerdb): {len(stations_rows)}",
        ]
        meta = dict(stations_meta or {})
        if meta:
            lines.append(
                f"Query: system_address={meta.get('system_address') if meta.get('system_address') is not None else '-'}"
            )
        self.system_details_var.set("\n".join(lines))

    def _populate_system_stations_list_item(self, idx: int, row: dict[str, Any]) -> str:
        iid = f"st:{idx}"
        self._station_rows_by_iid[iid] = dict(row)
        self.system_stations_tree.insert(
            "",
            "end",
            iid=iid,
            values=(
                _as_text(row.get("station_name")) or "-",
                _as_text(row.get("station_type")) or "-",
                self._services_label(row),
            ),
        )
        return iid

    def _populate_station_list(self, stations_rows: list[dict[str, Any]]) -> None:
        self.system_stations_tree.delete(*self.system_stations_tree.get_children())
        self.station_market_tree.delete(*self.station_market_tree.get_children())
        self._station_rows_by_iid.clear()
        for idx, row in enumerate(stations_rows or []):
            if not isinstance(row, dict):
                continue
            self._populate_system_stations_list_item(idx, row)

    def _station_details_text(self, row: dict[str, Any]) -> str:
        services = self._services_label(row)
        dist_ls = row.get("distance_ls")
        dist_text = f"{float(dist_ls):.0f} ls" if dist_ls is not None else "-"
        return "\n".join(
            [
                f"Stacja: {_as_text(row.get('station_name')) or '-'}",
                f"Typ: {_as_text(row.get('station_type')) or '-'}",
                f"MarketID: {row.get('market_id') if row.get('market_id') is not None else '-'}",
                f"Distance LS: {dist_text} ({_as_text(row.get('distance_ls_confidence')) or 'unknown'})",
                f"Uslugi: {services}",
                f"Freshness: {_as_text(row.get('freshness_ts')) or '-'} | {_as_text(row.get('confidence')) or 'observed'}",
            ]
        )

    def _populate_station_market_snapshots(self, station_row: dict[str, Any]) -> dict[str, Any]:
        self.station_market_tree.delete(*self.station_market_tree.get_children())
        market_id = station_row.get("market_id")
        if market_id is None:
            self.station_details_var.set(self._station_details_text(station_row))
            return {"ok": True, "market_id": None, "snapshots": 0, "reason": "no_market_id"}

        try:
            snapshots, meta = self.data_provider.get_market_last_seen(int(market_id), limit=5)
        except Exception as exc:
            self.station_details_var.set(self._station_details_text(station_row))
            self.station_market_tree.insert("", "end", values=("-", "-", f"ERR: {type(exc).__name__}"))
            return {"ok": False, "market_id": market_id, "reason": "provider_error"}

        for idx, snap in enumerate(snapshots or []):
            if not self._passes_freshness_filter(snap.get("freshness_ts") or snap.get("snapshot_ts")):
                continue
            ts = _as_text(snap.get("snapshot_ts")) or "-"
            items_count = int(snap.get("commodities_count") or len(list(snap.get("items") or [])) or 0)
            freshness_label = _format_age_short(snap.get("freshness_ts"))
            conf = _as_text(snap.get("confidence")) or "observed"
            self.station_market_tree.insert(
                "",
                "end",
                iid=f"mk:{idx}",
                values=(ts, str(items_count), f"{freshness_label} | {conf}"),
            )

        shown_rows = len(self.station_market_tree.get_children())
        self.station_details_var.set(
            self._station_details_text(station_row)
            + f"\nSnapshoty rynku: {shown_rows}/{len(snapshots)} (freshness={self.freshness_var.get()})"
        )
        return {"ok": True, "market_id": int(market_id), "snapshots": shown_rows, "meta": dict(meta or {})}

    def _on_station_tree_selected(self, _event=None) -> None:
        selection = self.system_stations_tree.selection() or ()
        if not selection:
            return
        self._select_station_by_iid(str(selection[0]))

    def _select_station_by_iid(self, iid: str) -> dict[str, Any]:
        row = self._station_rows_by_iid.get(str(iid))
        if not isinstance(row, dict):
            return {"ok": False, "reason": "station_row_not_found", "iid": str(iid)}
        result = self._populate_station_market_snapshots(row)
        return {"ok": True, "iid": str(iid), "station_name": _as_text(row.get("station_name")), **result}

    def reset_view(self) -> None:
        self.view_scale = 1.0
        self._center_world_point(0.0, 0.0)
        self._redraw_scene()
        self.map_status_var.set("Mapa: zresetowano zoom i pozycje.")

    def center_on_current_system(self) -> None:
        current_name = str(getattr(app_state, "current_system", "") or "").strip()
        current_star_pos = getattr(app_state, "current_star_pos", None)
        if isinstance(current_star_pos, (list, tuple)) and len(current_star_pos) >= 3:
            try:
                wx = float(current_star_pos[0])
                wy = float(current_star_pos[2])  # x/z -> 2D
                self._center_world_point(wx, wy)
                self._redraw_scene()
                self.map_status_var.set(f"Mapa: wycentrowano na aktualnym systemie ({current_name or 'current'}).")
                return
            except Exception:
                pass
        # fallback shell behavior
        self._center_world_point(0.0, 0.0)
        self._redraw_scene()
        self.map_status_var.set("Mapa: brak wspolrzednych aktualnego systemu (playerdb/current StarPos).")

    def _on_canvas_configure(self, _event=None) -> None:
        # If offsets are zero (first layout), center origin.
        if abs(self.view_offset_x) < 1e-6 and abs(self.view_offset_y) < 1e-6:
            self._center_world_point(0.0, 0.0)
        self._redraw_scene()

    def _on_canvas_press(self, event) -> None:
        self._pan_active = True
        self._pan_last_x = int(getattr(event, "x", 0))
        self._pan_last_y = int(getattr(event, "y", 0))
        self._set_map_cursor("arrow")

    def _on_canvas_drag(self, event) -> None:
        if not self._pan_active:
            return
        x = int(getattr(event, "x", 0))
        y = int(getattr(event, "y", 0))
        dx = x - self._pan_last_x
        dy = y - self._pan_last_y
        self._pan_last_x = x
        self._pan_last_y = y
        self._set_map_cursor("fleur")
        self.view_offset_x += dx
        self.view_offset_y += dy
        self._redraw_scene()

    def _on_canvas_release(self, _event=None) -> None:
        self._pan_active = False
        self._set_map_cursor("arrow")

    def _on_canvas_mousewheel(self, event) -> None:
        canvas = self.map_canvas
        try:
            px = float(getattr(event, "x", canvas.winfo_width() / 2.0))
            py = float(getattr(event, "y", canvas.winfo_height() / 2.0))
            delta = float(getattr(event, "delta", 0))
        except Exception:
            return

        if delta == 0:
            return
        factor = 1.1 if delta > 0 else (1.0 / 1.1)
        old_scale = float(self.view_scale)
        new_scale = max(self._min_scale, min(self._max_scale, old_scale * factor))
        if abs(new_scale - old_scale) < 1e-12:
            return

        # Zoom to cursor: keep the world point under cursor fixed.
        wx, wy = self.screen_to_world(px, py)
        self.view_scale = new_scale
        self.view_offset_x = px - wx * self.view_scale
        self.view_offset_y = py - wy * self.view_scale
        self._redraw_scene()

    def _center_world_point(self, wx: float, wy: float) -> None:
        c = self.map_canvas
        w = max(1, int(c.winfo_width() or 1))
        h = max(1, int(c.winfo_height() or 1))
        self.view_offset_x = (w / 2.0) - (float(wx) * self.view_scale)
        self.view_offset_y = (h / 2.0) - (float(wy) * self.view_scale)

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return (
            float(wx) * float(self.view_scale) + float(self.view_offset_x),
            float(wy) * float(self.view_scale) + float(self.view_offset_y),
        )

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        scale = float(self.view_scale) if abs(float(self.view_scale)) > 1e-12 else 1.0
        return (
            (float(sx) - float(self.view_offset_x)) / scale,
            (float(sy) - float(self.view_offset_y)) / scale,
        )

    def _redraw_scene(self) -> None:
        c = self.map_canvas
        c.delete("all")
        w = max(1, int(c.winfo_width() or 1))
        h = max(1, int(c.winfo_height() or 1))

        self._draw_grid(w, h)
        self._draw_origin_axes(w, h)
        self._draw_edges()
        self._draw_nodes()

        if not self._nodes:
            c.create_text(
                w / 2,
                h / 2,
                text=(
                    "Personal Galaxy Map\nBrak danych do renderu.\n"
                    "Sprawdz filtry time/freshness/source lub wlacz warstwe Travel."
                ),
                fill=COLOR_SEC,
                justify="center",
                font=("Segoe UI", 11),
            )

        # View HUD
        hud = f"scale={self.view_scale:.2f}  offset=({int(self.view_offset_x)},{int(self.view_offset_y)})  nodes={len(self._nodes)}  edges={len(self._edges)}"
        c.create_text(10, 10, text=hud, anchor="nw", fill=COLOR_FG, font=("Consolas", 9))

    def _draw_grid(self, w: int, h: int) -> None:
        # World-space grid step adapted to zoom to keep visual spacing usable.
        px_step_target = 80.0
        world_step = max(1.0, px_step_target / max(self.view_scale, 1e-6))
        # Round to 1/2/5 * 10^n
        mag = 10 ** math.floor(math.log10(world_step)) if world_step > 0 else 1
        norm = world_step / mag
        if norm <= 1:
            grid_step = 1 * mag
        elif norm <= 2:
            grid_step = 2 * mag
        elif norm <= 5:
            grid_step = 5 * mag
        else:
            grid_step = 10 * mag

        left_wx, top_wy = self.screen_to_world(0, 0)
        right_wx, bottom_wy = self.screen_to_world(w, h)
        min_x = min(left_wx, right_wx)
        max_x = max(left_wx, right_wx)
        min_y = min(top_wy, bottom_wy)
        max_y = max(top_wy, bottom_wy)

        start_x = math.floor(min_x / grid_step) * grid_step
        start_y = math.floor(min_y / grid_step) * grid_step

        x = start_x
        while x <= max_x:
            sx1, sy1 = self.world_to_screen(x, min_y)
            sx2, sy2 = self.world_to_screen(x, max_y)
            self.map_canvas.create_line(sx1, sy1, sx2, sy2, fill=COLOR_GRID)
            x += grid_step

        y = start_y
        while y <= max_y:
            sx1, sy1 = self.world_to_screen(min_x, y)
            sx2, sy2 = self.world_to_screen(max_x, y)
            self.map_canvas.create_line(sx1, sy1, sx2, sy2, fill=COLOR_GRID)
            y += grid_step

    def _draw_origin_axes(self, w: int, h: int) -> None:
        sx0, sy0 = self.world_to_screen(0.0, 0.0)
        self.map_canvas.create_line(0, sy0, w, sy0, fill="#2f3946", dash=(2, 4))
        self.map_canvas.create_line(sx0, 0, sx0, h, fill="#2f3946", dash=(2, 4))
        self.map_canvas.create_oval(sx0 - 3, sy0 - 3, sx0 + 3, sy0 + 3, outline=COLOR_HILITE, fill=COLOR_HILITE)

    def _draw_edges(self) -> None:
        for edge in self._edges:
            a = self._nodes.get(edge.from_key)
            b = self._nodes.get(edge.to_key)
            if a is None or b is None:
                continue
            x1, y1 = self.world_to_screen(a.x, a.y)
            x2, y2 = self.world_to_screen(b.x, b.y)
            self.map_canvas.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=COLOR_EDGE,
                width=1.0,
                tags=("map_edge", f"edge:{edge.key}"),
            )

    def _draw_nodes(self) -> None:
        show_labels = self.view_scale >= 0.8
        for node in self._nodes.values():
            sx, sy = self.world_to_screen(node.x, node.y)
            r = 4 if self.view_scale < 1.2 else 5
            node_tags = ("map_node", f"node:{node.key}")
            self.map_canvas.create_oval(
                sx - r,
                sy - r,
                sx + r,
                sy + r,
                outline=COLOR_NODE,
                fill=COLOR_NODE,
                tags=node_tags,
            )
            self._draw_node_layer_badges(node, sx, sy, r)
            self._draw_trade_compare_highlight(node, sx, sy, r)
            self._draw_node_state_rings(node, sx, sy, r)
            if show_labels:
                self.map_canvas.create_text(
                    sx + 8,
                    sy - 8,
                    text=node.system_name,
                    anchor="sw",
                    fill=COLOR_SEC,
                    font=("Segoe UI", 8),
                    tags=node_tags,
                )

    def _is_current_system_node(self, node: _MapNode) -> bool:
        current_name = _as_text(getattr(app_state, "current_system", ""))
        if not current_name:
            return False
        return current_name.casefold() == _as_text(node.system_name).casefold()

    def _draw_node_state_rings(self, node: _MapNode, sx: float, sy: float, r: int) -> None:
        c = self.map_canvas
        node_tag = f"node:{node.key}"
        is_selected = bool(node.key == self._selected_node_key)
        is_current = bool(self._is_current_system_node(node))

        # Current position ring (outer, green) so it can coexist with selected ring.
        if is_current:
            rr = r + 10
            c.create_oval(
                sx - rr,
                sy - rr,
                sx + rr,
                sy + rr,
                outline=COLOR_CURRENT_RING,
                width=2.0,
                tags=("node_state_ring", "node_current_ring", node_tag),
            )

        # Selected ring with contrast (dark shadow + white ring) for readability on bright overlays.
        if is_selected:
            rr_shadow = r + 8
            c.create_oval(
                sx - rr_shadow,
                sy - rr_shadow,
                sx + rr_shadow,
                sy + rr_shadow,
                outline=COLOR_SELECTED_RING_SHADOW,
                width=3.0,
                tags=("node_state_ring", "node_selected_ring_shadow", node_tag),
            )
            rr = r + 7
            c.create_oval(
                sx - rr,
                sy - rr,
                sx + rr,
                sy + rr,
                outline=COLOR_SELECTED_RING,
                width=2.0,
                tags=("node_state_ring", "node_selected_ring", node_tag),
            )

    def _draw_node_layer_badges(self, node: _MapNode, sx: float, sy: float, r: int) -> None:
        flags = dict(self._node_layer_flags.get(node.key) or {})
        if not flags:
            return
        c = self.map_canvas
        # Stations layer: outer ring (known stations in system).
        if bool(self.layer_stations_var.get()) and bool(flags.get("has_station")):
            rr = r + 3
            c.create_oval(
                sx - rr,
                sy - rr,
                sx + rr,
                sy + rr,
                outline=COLOR_STATION_LAYER,
                width=1.0,
                tags=("layer_stations", f"node:{node.key}"),
            )
        # Trade layer: small square badge (known market service in system).
        if bool(self.layer_trade_var.get()) and bool(flags.get("has_market")):
            s = 3
            c.create_rectangle(
                sx + r + 1,
                sy - r - 1,
                sx + r + 1 + (s * 2),
                sy - r - 1 + (s * 2),
                outline=COLOR_TRADE_LAYER,
                fill=COLOR_TRADE_LAYER,
                tags=("layer_trade", f"node:{node.key}"),
            )
        # Cash-In layer: diamond badge (known UC/Vista sell service in system).
        if bool(self.layer_cashin_var.get()) and bool(flags.get("has_cashin")):
            d = 4
            pts = [
                sx,
                sy + r + 2,
                sx + d,
                sy + r + 2 + d,
                sx,
                sy + r + 2 + (d * 2),
                sx - d,
                sy + r + 2 + d,
            ]
            c.create_polygon(
                *pts,
                outline=COLOR_CASHIN_LAYER,
                fill=COLOR_CASHIN_LAYER,
                tags=("layer_cashin", f"node:{node.key}"),
            )

    def _draw_trade_compare_highlight(self, node: _MapNode, sx: float, sy: float, r: int) -> None:
        if not bool(self.layer_trade_var.get()):
            return
        if node.key not in (self._trade_highlight_node_keys or set()):
            return
        rr = r + 7
        self.map_canvas.create_oval(
            sx - rr,
            sy - rr,
            sx + rr,
            sy + rr,
            outline=COLOR_TRADE_LAYER,
            width=2.0,
            tags=("layer_trade_highlight", f"node:{node.key}"),
        )


class _WheelShim:
    def __init__(self, event: Any, *, delta: int) -> None:
        self.x = getattr(event, "x", 0)
        self.y = getattr(event, "y", 0)
        self.delta = int(delta)
