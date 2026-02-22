from __future__ import annotations

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


@dataclass
class _MapNode:
    key: str
    system_name: str
    x: float
    y: float
    source: str = "playerdb"
    confidence: str = "observed"
    freshness_ts: str = ""
    last_seen_ts: str = ""


@dataclass
class _MapEdge:
    key: str
    from_key: str
    to_key: str


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
        self._min_scale = 0.25
        self._max_scale = 4.0

        # Pan state
        self._pan_active = False
        self._pan_last_x = 0
        self._pan_last_y = 0

        # Render state (F20-2 shell with placeholder/simple dataset support)
        self._nodes: dict[str, _MapNode] = {}
        self._edges: list[_MapEdge] = []
        self._selected_node_key: str | None = None
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
            cursor="fleur",
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
        self.trade_highlight_btn = tk.Button(
            trade_ctl,
            text="Highlight",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            state="disabled",
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

    def _on_filter_changed(self) -> None:
        self.reload_from_playerdb()

    def set_graph_data(self, *, nodes: list[dict[str, Any]] | None = None, edges: list[dict[str, Any]] | None = None) -> None:
        self._nodes.clear()
        self._edges.clear()
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
                    source=str(row.get("source") or "playerdb"),
                    confidence=str(row.get("confidence") or "observed"),
                    freshness_ts=str(row.get("freshness_ts") or ""),
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
        nodes_count = len(self._nodes)
        edges_count = len(self._edges)
        self.system_details_var.set(
            f"Travel layer: {nodes_count} systemow | {edges_count} krawedzi | "
            f"time={self.time_range_var.get()} | freshness={self.freshness_var.get()}"
        )
        self.station_details_var.set(
            "Drilldown stacji i snapshoty rynku zostana dopiete w F20-4."
        )

    def reload_from_playerdb(self) -> dict[str, Any]:
        if not bool(self.layer_travel_var.get()):
            self.set_graph_data(nodes=[], edges=[])
            self._travel_nodes_meta = {"count": 0, "disabled": True}
            self._travel_edges_meta = {"count": 0, "disabled": True}
            self._refresh_system_panel_stub()
            self.map_status_var.set("Mapa: warstwa Travel jest wylaczona.")
            return {"ok": True, "travel_enabled": False, "nodes": 0, "edges": 0}

        time_range = str(self.time_range_var.get() or "30d")
        source_filter = self._source_filter_mode()
        nodes_rows, nodes_meta = self.data_provider.get_system_nodes(time_range=time_range, source_filter=source_filter)
        edges_rows, edges_meta = self.data_provider.get_edges(time_range=time_range)

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

        self.set_graph_data(nodes=laid_out_nodes, edges=edges_final)
        self._refresh_system_panel_stub()

        count_nodes = len(self._nodes)
        count_edges = len(self._edges)
        status_reason = ""
        if edges_mode == "sequential_fallback":
            status_reason = " | krawedzie: fallback sekwencyjny (brak ingestu jumps)"
        self.map_status_var.set(
            f"Mapa Travel: {count_nodes} systemow / {count_edges} krawedzi | "
            f"time={time_range} | source={source_filter}{status_reason}"
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

    def _on_canvas_drag(self, event) -> None:
        if not self._pan_active:
            return
        x = int(getattr(event, "x", 0))
        y = int(getattr(event, "y", 0))
        dx = x - self._pan_last_x
        dy = y - self._pan_last_y
        self._pan_last_x = x
        self._pan_last_y = y
        self.view_offset_x += dx
        self.view_offset_y += dy
        self._redraw_scene()

    def _on_canvas_release(self, _event=None) -> None:
        self._pan_active = False

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
                text="Personal Galaxy Map (MVP shell)\nBrak danych do renderu.\nF20-3 doda warstwe Travel (nodes + jumps).",
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
            outline = COLOR_HILITE if node.key == self._selected_node_key else COLOR_NODE
            node_tags = ("map_node", f"node:{node.key}")
            self.map_canvas.create_oval(
                sx - r,
                sy - r,
                sx + r,
                sy + r,
                outline=outline,
                fill=COLOR_NODE,
                tags=node_tags,
            )
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


class _WheelShim:
    def __init__(self, event: Any, *, delta: int) -> None:
        self.x = getattr(event, "x", 0)
        self.y = getattr(event, "y", 0)
        self.delta = int(delta)
