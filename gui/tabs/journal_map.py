from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from app.route_manager import route_manager
from app.state import app_state
from gui import common
from gui.window_focus import bring_window_to_front
from logic.personal_map_data_provider import MapDataProvider
from logic.utils.renata_log import log_event_throttled

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
COLOR_EXOBIO_LAYER = "#2dd4bf"
COLOR_EXPLORATION_LAYER = "#facc15"
COLOR_INCIDENT_LAYER = "#ef4444"
COLOR_COMBAT_LAYER = "#fb7185"
COLOR_STAR_NEUTRON = "#7dd3fc"
COLOR_STAR_BLACK_HOLE = "#a78bfa"

TIME_RANGE_VALUES = ("all", "365d", "180d", "90d", "30d", "7d", "3d", "1d")
TIME_RANGE_ALLOWED = set(TIME_RANGE_VALUES) | {"forever"}
TIME_RANGE_SLIDER_VALUES = ("forever", "365d", "180d", "90d", "30d", "7d", "3d", "1d")
FRESHNESS_VALUES = ("<=6h", "<=24h", "<=7d", "any")
FRESHNESS_SLIDER_VALUES = ("any", "<=7d", "<=24h", "<=6h")


def _log_map_soft_failure(key: str, msg: str, **fields: Any) -> None:
    try:
        log_event_throttled(
            f"journal_map:{key}",
            5000,
            "GUI",
            msg,
            **fields,
        )
    except Exception:
        return


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
    primary_star_type: str = ""
    is_neutron: int = 0
    is_black_hole: int = 0


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


def _time_range_slider_index_for_value(value: Any) -> int:
    text = _as_text(value).lower()
    if text == "all":
        text = "forever"
    try:
        return int(TIME_RANGE_SLIDER_VALUES.index(text))
    except Exception:
        return int(TIME_RANGE_SLIDER_VALUES.index("30d"))


def _time_range_value_for_slider_index(value: Any) -> str:
    try:
        idx = int(round(float(value)))
    except Exception:
        idx = 0
    idx = max(0, min(len(TIME_RANGE_SLIDER_VALUES) - 1, idx))
    return str(TIME_RANGE_SLIDER_VALUES[idx])


def _freshness_slider_index_for_value(value: Any) -> int:
    text = _as_text(value).lower()
    try:
        return int(FRESHNESS_SLIDER_VALUES.index(text))
    except Exception:
        return int(FRESHNESS_SLIDER_VALUES.index("any"))


def _freshness_value_for_slider_index(value: Any) -> str:
    try:
        idx = int(round(float(value)))
    except Exception:
        idx = 0
    idx = max(0, min(len(FRESHNESS_SLIDER_VALUES) - 1, idx))
    return str(FRESHNESS_SLIDER_VALUES[idx])


class JournalMapTab(tk.Frame):
    """
    F20-2 shell zakladki mapy osadzonej w `Dziennik`.
    Zakres:
    - 3 panele (filtry / canvas / szczegoly)
    - canvas pan+zoom (dziala tez na pustych danych)
    - placeholder/stub przyciskow i paneli pod dalsze tickety F20-3..F20-6
    """

    def __init__(
        self,
        parent,
        app=None,
        data_provider: MapDataProvider | None = None,
        logbook_owner=None,
        *args,
        **kwargs,
    ):
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)
        self.app = app
        self.data_provider = data_provider or MapDataProvider()
        self.logbook_owner = logbook_owner

        # View transform (world -> screen)
        self.view_scale: float = 1.0
        self.view_offset_x: float = 0.0
        self.view_offset_y: float = 0.0
        self._min_scale = 0.10
        self._max_scale = 200.0

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
        self._trade_compare_rows_by_iid: dict[str, dict[str, Any]] = {}
        self._trade_compare_tree_last_reflow_width: int = 0
        self._trade_selected_commodities: list[str] = []
        self._travel_nodes_meta: dict[str, Any] = {}
        self._travel_edges_meta: dict[str, Any] = {}
        self._pending_after_ids: list[str] = []
        self._map_ppm_node_key: str | None = None
        self._tooltip_visible = False
        self._tooltip_node_key: str | None = None
        self._tooltip_text_cache = ""
        self._tooltip_last_pos: tuple[int, int] | None = None
        self._star_legend_popup = None
        self._star_legend_hide_after_id: str | None = None
        self._star_legend_pinned = False
        self._startup_autocenter_pending = True
        self._startup_autocenter_done = False
        self._startup_autocenter_user_blocked = False
        self._startup_autocenter_recenter_pending = False
        self._trade_picker_window = None
        self._trade_picker_search_var = None
        self._trade_picker_tree = None
        self._trade_picker_tree_vsb = None
        self._trade_picker_tree_hsb = None
        self._trade_picker_station_only_var = None
        self._trade_picker_station_only_chk = None
        self._trade_picker_station_filter_status_var = None
        self._trade_picker_available: list[str] = []
        self._trade_picker_selected: set[str] = set()
        self._auto_refresh_dirty = False
        self._auto_refresh_debounce_ms = 650
        self._auto_refresh_after_id: str | None = None
        self._auto_refresh_last_update: dict[str, Any] = {}
        self._filter_reload_debounce_ms = 90
        self._filter_reload_after_id: str | None = None
        self._prefetched_system_stations: dict[str, dict[str, Any]] = {}

        # Filters (UI shell)
        self.layer_travel_var = tk.BooleanVar(value=True)
        self.layer_stations_var = tk.BooleanVar(value=True)
        self.layer_trade_var = tk.BooleanVar(value=False)
        self.layer_cashin_var = tk.BooleanVar(value=False)
        self.layer_exobio_var = tk.BooleanVar(value=False)
        self.layer_exploration_var = tk.BooleanVar(value=False)
        self.layer_incidents_var = tk.BooleanVar(value=False)
        self.layer_combat_var = tk.BooleanVar(value=False)
        self.time_range_var = tk.StringVar(value="30d")
        self.freshness_var = tk.StringVar(value="any")
        self.time_range_slider_var = tk.IntVar(value=_time_range_slider_index_for_value("30d"))
        self.freshness_slider_var = tk.IntVar(value=_freshness_slider_index_for_value("any"))
        self.time_range_label_var = tk.StringVar(value="30d")
        self.freshness_label_var = tk.StringVar(value="any")
        self.last_session_only_var = tk.BooleanVar(value=False)
        self._map_session_started_utc = datetime.now(timezone.utc)
        self._time_filter_sync_suppress = False
        self.source_include_enriched_var = tk.BooleanVar(value=False)
        self.render_mode_var = tk.StringVar(value="Trasa")
        self.trade_compare_commodity_var = tk.StringVar(value="")
        self.trade_selected_summary_var = tk.StringVar(value="Brak wybranych towarow.")
        self.map_status_var = tk.StringVar(value="Mapa gotowa (shell). Brak danych do renderu.")
        self.legend_collapsed_var = tk.BooleanVar(value=False)
        self.legend_toggle_text_var = tk.StringVar(value="Ukryj")
        self.legend_text_var = tk.StringVar(value="")
        self._action_layers_meta: dict[str, Any] = {}

        self._build_ui()
        self._build_map_context_menu()
        self._bind_canvas()
        self._schedule_after(50, self.reset_view)
        self._schedule_after(90, self.reload_from_playerdb)

    def export_persisted_ui_state(self) -> dict[str, Any]:
        return {
            "layers": {
                "travel": bool(self.layer_travel_var.get()),
                "stations": bool(self.layer_stations_var.get()),
                "trade": bool(self.layer_trade_var.get()),
                "cash_in": bool(self.layer_cashin_var.get()),
                "exobio": bool(self.layer_exobio_var.get()),
                "exploration": bool(self.layer_exploration_var.get()),
                "incidents": bool(self.layer_incidents_var.get()),
                "combat": bool(self.layer_combat_var.get()),
            },
            "filters": {
                "time_range": _as_text(self.time_range_var.get()) or "30d",
                "freshness": _as_text(self.freshness_var.get()) or "any",
                "last_session_only": bool(self.last_session_only_var.get()),
                "source_include_enriched": bool(self.source_include_enriched_var.get()),
                "render_mode": _as_text(self.render_mode_var.get()) or "Trasa",
            },
            "legend": {
                "collapsed": bool(self.legend_collapsed_var.get()),
            },
        }

    def apply_persisted_ui_state(self, state: dict[str, Any] | None) -> None:
        if not isinstance(state, dict):
            return

        layers = state.get("layers")
        if isinstance(layers, dict):
            for key, var in (
                ("travel", self.layer_travel_var),
                ("stations", self.layer_stations_var),
                ("trade", self.layer_trade_var),
                ("cash_in", self.layer_cashin_var),
                ("exobio", self.layer_exobio_var),
                ("exploration", self.layer_exploration_var),
                ("incidents", self.layer_incidents_var),
                ("combat", self.layer_combat_var),
            ):
                if key in layers:
                    try:
                        var.set(bool(layers.get(key)))
                    except Exception as exc:
                        _log_map_soft_failure(
                            "apply_state_layer_var",
                            "apply persisted map layer state failed",
                            layer=key,
                            error=f"{type(exc).__name__}: {exc}",
                        )

        filters = state.get("filters")
        if isinstance(filters, dict):
            time_range = _as_text(filters.get("time_range")).lower()
            if time_range == "forever":
                time_range = "all"
            if time_range in TIME_RANGE_ALLOWED:
                self.time_range_var.set(time_range)
            freshness = _as_text(filters.get("freshness"))
            if freshness in {"<=6h", "<=24h", "<=7d", "any"}:
                self.freshness_var.set(freshness)
            if "last_session_only" in filters:
                try:
                    self.last_session_only_var.set(bool(filters.get("last_session_only")))
                except Exception as exc:
                    _log_map_soft_failure(
                        "apply_state_last_session",
                        "apply persisted last-session filter failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            if "source_include_enriched" in filters:
                try:
                    self.source_include_enriched_var.set(bool(filters.get("source_include_enriched")))
                except Exception as exc:
                    _log_map_soft_failure(
                        "apply_state_source_filter",
                        "apply persisted map source filter failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            render_mode = _as_text(filters.get("render_mode"))
            if render_mode in {"Trasa", "Mapa"}:
                try:
                    self.render_mode_var.set(render_mode)
                except Exception as exc:
                    _log_map_soft_failure(
                        "apply_state_render_mode",
                        "apply persisted map render mode failed",
                        value=render_mode,
                        error=f"{type(exc).__name__}: {exc}",
                    )
        self._sync_time_filter_controls_from_vars()
        self._sync_time_filter_controls_enabled()

        legend = state.get("legend")
        if isinstance(legend, dict) and "collapsed" in legend:
            collapsed = bool(legend.get("collapsed"))
            try:
                self.legend_collapsed_var.set(collapsed)
                if collapsed:
                    self.legend_body_host.grid_remove()
                    self.legend_toggle_text_var.set("Pokaz")
                else:
                    self.legend_body_host.grid()
                    self.legend_toggle_text_var.set("Ukryj")
            except Exception as exc:
                _log_map_soft_failure(
                    "apply_state_legend",
                    "apply persisted map legend state failed",
                    collapsed=collapsed,
                    error=f"{type(exc).__name__}: {exc}",
                )

        self._refresh_legend()

    def _effective_time_range_filter(self) -> str:
        if bool(self.last_session_only_var.get()):
            return "all"
        value = _as_text(self.time_range_var.get()).lower()
        if not value:
            return "30d"
        return "all" if value == "forever" else value

    def _effective_freshness_filter(self) -> str:
        if bool(self.last_session_only_var.get()):
            return "any"
        value = _as_text(self.freshness_var.get()).lower()
        return value or "any"

    def _sync_time_filter_controls_from_vars(self) -> None:
        self._time_filter_sync_suppress = True
        time_value = _as_text(self.time_range_var.get()).lower()
        if time_value == "all":
            time_value = "forever"
        freshness_value = _as_text(self.freshness_var.get()).lower()
        if not freshness_value:
            freshness_value = "any"
        try:
            try:
                self.time_range_slider_var.set(_time_range_slider_index_for_value(time_value))
            except Exception:
                pass
            try:
                self.freshness_slider_var.set(_freshness_slider_index_for_value(freshness_value))
            except Exception:
                pass
            self.time_range_label_var.set(time_value or "30d")
            self.freshness_label_var.set(freshness_value or "any")
        finally:
            self._time_filter_sync_suppress = False

    def _sync_time_filter_controls_enabled(self) -> None:
        disabled = bool(self.last_session_only_var.get())
        state = "disabled" if disabled else "normal"
        for widget_name in ("time_range_slider", "freshness_slider"):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            try:
                widget.configure(state=state)
            except Exception:
                continue

    def _on_time_range_slider_changed(self, _value=None) -> None:
        if bool(self._time_filter_sync_suppress):
            return
        value = _time_range_value_for_slider_index(self.time_range_slider_var.get())
        self.time_range_var.set("all" if value == "forever" else value)
        self.time_range_label_var.set(value)
        self._on_filter_changed()

    def _on_freshness_slider_changed(self, _value=None) -> None:
        if bool(self._time_filter_sync_suppress):
            return
        value = _freshness_value_for_slider_index(self.freshness_slider_var.get())
        self.freshness_var.set(value)
        self.freshness_label_var.set(value)
        self._on_filter_changed()

    def _on_last_session_toggled(self) -> None:
        self._sync_time_filter_controls_enabled()
        self._on_filter_changed()

    def _passes_last_session_filter(self, value: Any) -> bool:
        dt = _parse_iso_ts(value)
        if dt is None:
            return False
        return dt >= self._map_session_started_utc

    def _schedule_after(self, delay_ms: int, callback) -> str:
        after_id = self.after(int(delay_ms), callback)
        try:
            self._pending_after_ids.append(str(after_id))
        except Exception as exc:
            _log_map_soft_failure(
                "schedule_after_track",
                "track pending after id failed",
                delay_ms=int(delay_ms),
                error=f"{type(exc).__name__}: {exc}",
            )
        return str(after_id)

    def _cancel_pending_after_jobs(self) -> None:
        pending = list(getattr(self, "_pending_after_ids", []) or [])
        self._pending_after_ids = []
        for after_id in pending:
            try:
                self.after_cancel(after_id)
            except Exception as exc:
                _log_map_soft_failure(
                    "cancel_pending_after",
                    "cancel pending after job failed",
                    after_id=str(after_id),
                    error=f"{type(exc).__name__}: {exc}",
                )

    def destroy(self) -> None:
        try:
            self._cancel_filter_reload_debounce()
        except Exception as exc:
            _log_map_soft_failure(
                "destroy_cancel_filter_reload",
                "cancel filter reload debounce on destroy failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        try:
            self._cancel_auto_refresh_debounce()
        except Exception as exc:
            _log_map_soft_failure(
                "destroy_cancel_auto_refresh",
                "cancel auto refresh on destroy failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        try:
            self._hide_star_legend_popup(force=True)
        except Exception as exc:
            _log_map_soft_failure(
                "destroy_hide_star_legend_popup",
                "hide star legend popup on destroy failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        self._cancel_pending_after_jobs()
        try:
            self._trade_picker_close()
        except Exception as exc:
            _log_map_soft_failure(
                "destroy_close_trade_picker",
                "close trade picker on destroy failed",
                error=f"{type(exc).__name__}: {exc}",
            )
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
        self.left_frame.rowconfigure(5, weight=1)

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
                ("Exobio", self.layer_exobio_var),
                ("Exploration", self.layer_exploration_var),
                ("Incidents", self.layer_incidents_var),
                ("Combat", self.layer_combat_var),
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
        tk.Label(filters_box, textvariable=self.time_range_label_var, bg=COLOR_BG, fg=COLOR_SEC).grid(
            row=0, column=1, sticky="e", padx=(4, 8), pady=(6, 4)
        )
        self.time_range_slider = tk.Scale(
            filters_box,
            from_=0,
            to=len(TIME_RANGE_SLIDER_VALUES) - 1,
            orient="horizontal",
            showvalue=False,
            variable=self.time_range_slider_var,
            command=self._on_time_range_slider_changed,
            bg=COLOR_BG,
            fg=COLOR_FG,
            troughcolor=COLOR_ACCENT,
            highlightthickness=0,
            activebackground=COLOR_FG,
        )
        self.time_range_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))

        tk.Label(filters_box, text="Freshness:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 4)
        )
        tk.Label(filters_box, textvariable=self.freshness_label_var, bg=COLOR_BG, fg=COLOR_SEC).grid(
            row=2, column=1, sticky="e", padx=(4, 8), pady=(0, 4)
        )
        self.freshness_slider = tk.Scale(
            filters_box,
            from_=0,
            to=len(FRESHNESS_SLIDER_VALUES) - 1,
            orient="horizontal",
            showvalue=False,
            variable=self.freshness_slider_var,
            command=self._on_freshness_slider_changed,
            bg=COLOR_BG,
            fg=COLOR_FG,
            troughcolor=COLOR_ACCENT,
            highlightthickness=0,
            activebackground=COLOR_FG,
        )
        self.freshness_slider.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))

        last_session_chk = tk.Checkbutton(
            filters_box,
            text="Ostatnia sesja",
            variable=self.last_session_only_var,
            command=self._on_last_session_toggled,
            bg=COLOR_BG,
            fg=COLOR_FG,
            selectcolor=COLOR_ACCENT,
            activebackground=COLOR_BG,
            activeforeground=COLOR_FG,
        )
        last_session_chk.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

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
        include_enriched_chk.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        tk.Label(filters_box, text="Tryb renderowania:", bg=COLOR_BG, fg=COLOR_FG).grid(
            row=6, column=0, sticky="w", padx=8, pady=(4, 6)
        )
        render_mode_combo = ttk.Combobox(
            filters_box,
            values=("Trasa", "Mapa"),
            state="readonly",
            textvariable=self.render_mode_var,
            width=10,
        )
        render_mode_combo.grid(row=6, column=1, sticky="ew", padx=(4, 8), pady=(4, 6))
        render_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filter_changed())
        self._sync_time_filter_controls_from_vars()
        self._sync_time_filter_controls_enabled()

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

        legend_box = tk.LabelFrame(
            self.left_frame,
            text="Legenda",
            bg=COLOR_BG,
            fg=COLOR_FG,
            bd=1,
            relief="groove",
            labelanchor="nw",
        )
        legend_box.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        legend_box.columnconfigure(0, weight=1)
        legend_box.rowconfigure(1, weight=1)

        legend_head = tk.Frame(legend_box, bg=COLOR_BG)
        legend_head.grid(row=0, column=0, sticky="ew")
        legend_head.columnconfigure(0, weight=1)
        self.legend_star_info_btn = tk.Button(
            legend_head,
            text="Gwiazdy",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            width=8,
            command=self._toggle_star_legend_popup,
        )
        self.legend_star_info_btn.grid(row=0, column=1, sticky="e", padx=(6, 0), pady=(4, 2))
        self.legend_toggle_btn = tk.Button(
            legend_head,
            textvariable=self.legend_toggle_text_var,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._toggle_legend,
            width=10,
        )
        self.legend_toggle_btn.grid(row=0, column=2, sticky="e", padx=6, pady=(4, 2))

        self.legend_body_host = tk.Frame(legend_box, bg=COLOR_BG)
        self.legend_body_host.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.legend_body_host.columnconfigure(0, weight=1)
        self.legend_body_host.rowconfigure(0, weight=1)

        self.legend_body_canvas = tk.Canvas(
            self.legend_body_host,
            bg=COLOR_BG,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.legend_body_canvas.grid(row=0, column=0, sticky="nsew")
        self.legend_body_scrollbar = ttk.Scrollbar(
            self.legend_body_host,
            orient="vertical",
            command=self.legend_body_canvas.yview,
        )
        self.legend_body_scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.legend_body_canvas.configure(yscrollcommand=self.legend_body_scrollbar.set)

        self.legend_body_frame = tk.Frame(self.legend_body_canvas, bg=COLOR_BG)
        self.legend_body_frame.columnconfigure(0, weight=1)
        self._legend_body_window_id = self.legend_body_canvas.create_window(
            (0, 0),
            window=self.legend_body_frame,
            anchor="nw",
        )
        self.legend_body_frame.bind("<Configure>", self._on_legend_body_frame_configure)
        self.legend_body_canvas.bind("<Configure>", self._on_legend_canvas_configure)
        self._bind_legend_mousewheel_recursive(self.legend_body_host)

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
        self.trade_pick_btn = tk.Button(
            trade_ctl,
            text="Wybierz towary...",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._open_trade_commodity_picker,
        )
        self.trade_pick_btn.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.trade_highlight_btn = tk.Button(
            trade_ctl,
            text="Odswiez",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            state="disabled",
            command=self._on_trade_highlight_clicked,
        )
        self.trade_highlight_btn.grid(row=0, column=1, sticky="e")
        self.trade_clear_btn = tk.Button(
            trade_ctl,
            text="Wyczysc compare",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            state="disabled",
            command=self._on_trade_compare_clear_clicked,
        )
        self.trade_clear_btn.grid(row=0, column=2, sticky="e", padx=(6, 0))

        tk.Label(
            self.right_frame,
            textvariable=self.trade_selected_summary_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
            wraplength=360,
        ).grid(row=9, column=0, sticky="ew", pady=(0, 4))

        # Legacy MVP combobox kept as hidden compatibility path (F20 tests / fallback single commodity).
        self.trade_commodity_combo = ttk.Combobox(
            trade_ctl,
            textvariable=self.trade_compare_commodity_var,
            values=(),
            width=18,
        )
        self.trade_commodity_combo.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.trade_commodity_combo.bind("<<ComboboxSelected>>", self._on_trade_commodity_changed)
        self.trade_commodity_combo.bind("<Return>", self._on_trade_commodity_changed)
        self.trade_commodity_combo.grid_remove()

        self.trade_compare_tree = ttk.Treeview(
            self.right_frame,
            columns=("mode", "commodity", "price", "age"),
            show="headings",
            style="Treeview",
            height=6,
        )
        for col, title, width, anchor in (
            ("mode", "Tryb", 58, "w"),
            ("commodity", "Towar", 150, "w"),
            ("price", "Cena", 76, "e"),
            ("age", "Age", 82, "w"),
        ):
            self.trade_compare_tree.heading(col, text=title)
            self.trade_compare_tree.column(
                col,
                width=width,
                anchor=anchor,
                stretch=(col in {"commodity"}),
            )
        self.trade_compare_tree.grid(row=10, column=0, sticky="nsew")
        self.trade_compare_tree.bind("<<TreeviewSelect>>", self._on_trade_compare_row_selected)
        self.trade_compare_tree.bind("<Configure>", self._on_trade_compare_tree_configure, add="+")

        # Bottom status
        status = tk.Label(
            self,
            textvariable=self.map_status_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
        )
        status.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        self._refresh_legend()

    def _bind_canvas(self) -> None:
        self.map_canvas.bind("<Configure>", self._on_canvas_configure)
        self.map_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.map_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.map_canvas.bind("<Leave>", self._on_canvas_leave)
        self.map_canvas.bind("<Motion>", self._on_canvas_node_motion, add="+")
        self.map_canvas.bind("<Button-3>", self._on_canvas_context_menu)
        self.map_canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        # Linux compatibility (no-op on Windows if never fired)
        self.map_canvas.bind("<Button-4>", lambda e: self._on_canvas_mousewheel(_WheelShim(e, delta=120)))
        self.map_canvas.bind("<Button-5>", lambda e: self._on_canvas_mousewheel(_WheelShim(e, delta=-120)))
        self.map_canvas.tag_bind("map_node", "<ButtonPress-1>", self._on_canvas_node_click)
        self.map_canvas.tag_bind("map_node", "<Double-Button-1>", self._on_canvas_node_double_click)
        self.map_canvas.tag_bind("map_node", "<Motion>", self._on_canvas_node_motion)
        self.map_canvas.tag_bind("map_node", "<Leave>", self._on_canvas_node_leave)
        self.map_canvas.tag_bind("map_star_marker", "<ButtonPress-1>", self._on_canvas_node_click)
        self.map_canvas.tag_bind("map_star_marker", "<Double-Button-1>", self._on_canvas_node_double_click)
        self.map_canvas.tag_bind("map_star_marker", "<Motion>", self._on_canvas_node_motion)
        self.map_canvas.tag_bind("map_star_marker", "<Leave>", self._on_canvas_node_leave)
        self.map_canvas.tag_bind("map_node_label", "<ButtonPress-1>", self._on_canvas_node_click)
        self.map_canvas.tag_bind("map_node_label", "<Double-Button-1>", self._on_canvas_node_double_click)
        self.map_canvas.tag_bind("map_node_label", "<Motion>", self._on_canvas_node_motion)
        self.map_canvas.tag_bind("map_node_label", "<Leave>", self._on_canvas_node_leave)

    def _build_map_context_menu(self) -> None:
        self._map_context_menu = tk.Menu(self, tearoff=0, bg=COLOR_BG, fg=COLOR_FG, activebackground=COLOR_ACCENT)
        self._map_context_menu_set_target = tk.Menu(
            self._map_context_menu, tearoff=0, bg=COLOR_BG, fg=COLOR_FG, activebackground=COLOR_ACCENT
        )
        self._map_context_menu_add_entry = tk.Menu(
            self._map_context_menu, tearoff=0, bg=COLOR_BG, fg=COLOR_FG, activebackground=COLOR_ACCENT
        )
        self._map_context_menu.add_cascade(label="Ustaw cel", menu=self._map_context_menu_set_target)
        self._map_context_menu_set_target.add_command(
            label="Trasa zwykla",
            command=lambda: self._map_ppm_action_set_route(neutron=False),
        )
        self._map_context_menu_set_target.add_command(
            label="Trasa neutronowa",
            command=lambda: self._map_ppm_action_set_route(neutron=True),
        )
        self._map_context_menu.add_command(label="Kopiuj cel", command=self._map_ppm_action_copy_target)
        self._map_context_menu.add_separator()
        self._map_context_menu.add_cascade(label="Dodaj wpis", menu=self._map_context_menu_add_entry)
        self._map_context_menu.add_command(
            label="Dodaj wpis i edytuj",
            command=lambda: self._map_ppm_action_add_entry(edit_after=True),
        )
        self._map_context_menu.add_separator()
        self._map_context_menu.add_command(label="Wycentruj na tym systemie", command=self._map_ppm_action_center_on_node)
        self._map_context_menu.add_command(
            label="Pokaz tylko ten system w panelu",
            command=self._map_ppm_action_focus_panel,
        )

    def _resolve_map_ppm_node_key(self, event=None) -> str | None:
        key = self._canvas_current_node_key()
        if key:
            return key
        if event is None:
            return None
        try:
            x = int(getattr(event, "x", 0))
            y = int(getattr(event, "y", 0))
            item_ids = self.map_canvas.find_overlapping(x - 1, y - 1, x + 1, y + 1)
        except Exception:
            return None
        for item_id in reversed(tuple(item_ids or ())):
            try:
                tags = self.map_canvas.gettags(item_id) or ()
            except Exception:
                continue
            for tag in tags:
                text = str(tag)
                if text.startswith("node:"):
                    return text.split(":", 1)[1].strip() or None
        return None

    def _map_ppm_target_node(self) -> _MapNode | None:
        key = _as_text(self._map_ppm_node_key)
        if not key:
            return None
        return self._nodes.get(key)

    def _map_ppm_available_categories(self) -> list[str]:
        owner = getattr(self, "logbook_owner", None)
        getter = getattr(owner, "map_get_available_entry_categories", None)
        if callable(getter):
            try:
                rows = [str(v).strip() for v in list(getter() or []) if str(v).strip()]
                if rows:
                    return rows
            except Exception as exc:
                _log_map_soft_failure(
                    "ppm_available_categories",
                    "load map PPM available entry categories failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
        return []

    def _map_ppm_rebuild_add_entry_menu(self) -> None:
        menu = self._map_context_menu_add_entry
        try:
            menu.delete(0, "end")
        except Exception:
            return
        categories = self._map_ppm_available_categories()
        if not categories:
            menu.add_command(
                label="Brak kategorii",
                state="disabled",
            )
            menu.add_command(
                label="Dodaj do domyslnej kategorii",
                command=lambda: self._map_ppm_action_add_entry(edit_after=False, category_path=None),
            )
            return
        for category in categories:
            menu.add_command(
                label=category,
                command=lambda c=category: self._map_ppm_action_add_entry(edit_after=False, category_path=c),
            )

    def _map_ppm_set_menu_states(self) -> None:
        node = self._map_ppm_target_node()
        has_node = node is not None
        has_app = self.app is not None
        has_owner = self.logbook_owner is not None
        neutron_tab = getattr(getattr(self.app, "tab_spansh", None), "tab_neutron", None) if has_app else None
        neutron_busy_other = bool(route_manager.is_busy()) and str(route_manager.current_mode() or "").strip().lower() not in {"", "neutron"}
        neutron_ready = bool(has_node and neutron_tab is not None and not neutron_busy_other)

        self._map_context_menu.entryconfigure("Ustaw cel", state=("normal" if has_node else "disabled"))
        self._map_context_menu_set_target.entryconfigure("Trasa zwykla", state=("normal" if has_node else "disabled"))
        self._map_context_menu_set_target.entryconfigure("Trasa neutronowa", state=("normal" if neutron_ready else "disabled"))
        self._map_context_menu.entryconfigure("Kopiuj cel", state=("normal" if has_node else "disabled"))
        self._map_context_menu.entryconfigure("Dodaj wpis", state=("normal" if (has_node and has_owner) else "disabled"))
        self._map_context_menu.entryconfigure("Dodaj wpis i edytuj", state=("normal" if (has_node and has_owner) else "disabled"))
        self._map_context_menu.entryconfigure("Wycentruj na tym systemie", state=("normal" if has_node else "disabled"))
        self._map_context_menu.entryconfigure("Pokaz tylko ten system w panelu", state=("normal" if has_node else "disabled"))

    def _on_canvas_context_menu(self, event) -> str | None:
        key = self._resolve_map_ppm_node_key(event)
        if not key:
            self.map_status_var.set("Mapa: PPM jest dostepne po kliknieciu na system (node).")
            return None
        self._hide_map_tooltip()
        self._map_ppm_node_key = key
        self._pan_active = False
        self._set_map_cursor("arrow")
        self._map_ppm_rebuild_add_entry_menu()
        self._map_ppm_set_menu_states()
        try:
            self._map_context_menu.tk_popup(int(getattr(event, "x_root", 0)), int(getattr(event, "y_root", 0)))
        finally:
            try:
                self._map_context_menu.grab_release()
            except Exception as exc:
                _log_map_soft_failure(
                    "ppm_grab_release",
                    "map context menu grab_release failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
        return "break"

    def _map_ppm_action_focus_panel(self) -> dict[str, Any]:
        node = self._map_ppm_target_node()
        if node is None:
            self.map_status_var.set("Mapa: brak wybranego node do akcji PPM.")
            return {"ok": False, "reason": "node_missing"}
        result = self.select_system_node(node.key)
        if bool(result.get("ok")):
            self.map_status_var.set(f"Mapa: fokus panelu ustawiony na system {node.system_name}.")
        return result

    def _map_ppm_action_center_on_node(self) -> dict[str, Any]:
        node = self._map_ppm_target_node()
        if node is None:
            self.map_status_var.set("Mapa: brak wybranego node do wycentrowania.")
            return {"ok": False, "reason": "node_missing"}
        self._center_world_point(node.x, node.y)
        self._redraw_scene()
        self.map_status_var.set(f"Mapa: wycentrowano na systemie {node.system_name}.")
        return {"ok": True, "system_name": node.system_name}

    def _map_ppm_action_copy_target(self) -> dict[str, Any]:
        node = self._map_ppm_target_node()
        if node is None:
            self.map_status_var.set("Mapa: brak celu do skopiowania.")
            return {"ok": False, "reason": "node_missing"}
        copied = bool(common.copy_text_to_clipboard(node.system_name, context="map.ppm.system"))
        if copied:
            self.map_status_var.set(f"Mapa: skopiowano cel systemu: {node.system_name}.")
            return {"ok": True, "copied": True, "system_name": node.system_name}
        self.map_status_var.set(f"Mapa: nie udalo sie skopiowac celu: {node.system_name}.")
        return {"ok": False, "reason": "clipboard_failed", "system_name": node.system_name}

    def _map_ppm_action_set_route(self, *, neutron: bool) -> dict[str, Any]:
        node = self._map_ppm_target_node()
        if node is None:
            self.map_status_var.set("Mapa: brak celu do ustawienia trasy.")
            return {"ok": False, "reason": "node_missing"}
        target = str(node.system_name or "").strip()
        if not target:
            self.map_status_var.set("Mapa: wybrany node nie ma poprawnej nazwy systemu.")
            return {"ok": False, "reason": "target_missing"}
        if neutron:
            return self._map_ppm_action_set_neutron_route(target)
        app_state.set_route_intent(target, source="journal.map.ppm.intent", route_profile="SAFE")
        copied = bool(common.copy_text_to_clipboard(target, context="journal.map.ppm.intent.system"))
        self.map_status_var.set(
            f"Mapa: ustawiono cel trasy (zwykla): {target}." + (" Skopiowano cel." if copied else "")
        )
        if self.app is not None and hasattr(self.app, "show_status"):
            try:
                self.app.show_status(f"Mapa: ustawiono cel trasy -> {target}.")
            except Exception as exc:
                _log_map_soft_failure(
                    "ppm_set_route_show_status",
                    "show_status after map route intent failed",
                    target=target,
                    error=f"{type(exc).__name__}: {exc}",
                )
        return {"ok": True, "target": target, "route": "normal", "copied": copied}

    def _map_ppm_action_set_neutron_route(self, target: str) -> dict[str, Any]:
        neutron_tab = getattr(getattr(self.app, "tab_spansh", None), "tab_neutron", None)
        if neutron_tab is None:
            self.map_status_var.set("Mapa: planner neutronowy jest niedostępny.")
            return {"ok": False, "reason": "neutron_tab_unavailable"}
        if bool(route_manager.is_busy()):
            mode_now = str(route_manager.current_mode() or "").strip().lower()
            if mode_now and mode_now != "neutron":
                self.map_status_var.set("Mapa: planner jest zajęty innym trybem. Spróbuj za chwilę.")
                return {"ok": False, "reason": "planner_busy_other_mode"}
        current_system = str(getattr(app_state, "current_system", "") or "").strip()
        try:
            if current_system and hasattr(neutron_tab, "var_start"):
                neutron_tab.var_start.set(current_system)
            if hasattr(neutron_tab, "var_cel"):
                neutron_tab.var_cel.set(target)
            setattr(neutron_tab, "_route_ready_source_override_once", "map.spansh.neutron")
            neutron_tab.run_neutron()
        except Exception:
            self.map_status_var.set("Mapa: nie udalo sie uruchomic trasy neutronowej.")
            return {"ok": False, "reason": "neutron_start_failed"}
        copied = bool(common.copy_text_to_clipboard(target, context="journal.map.ppm.neutron.target"))
        self.map_status_var.set(
            "Mapa: uruchomiono planner trasy neutronowej."
            + (f" Skopiowano cel: {target}." if copied else "")
        )
        return {"ok": True, "route": "neutron", "target": target, "copied": copied}

    def _map_ppm_action_add_entry(self, *, edit_after: bool, category_path: str | None = None) -> dict[str, Any]:
        node = self._map_ppm_target_node()
        if node is None:
            self.map_status_var.set("Mapa: brak systemu do utworzenia wpisu.")
            return {"ok": False, "reason": "node_missing"}
        owner = getattr(self, "logbook_owner", None)
        creator = getattr(owner, "map_create_entry_for_system", None)
        if not callable(creator):
            self.map_status_var.set("Mapa: logbook owner nie obsluguje tworzenia wpisu z mapy.")
            return {"ok": False, "reason": "entry_owner_unavailable"}
        try:
            result = creator(
                node.system_name,
                category_path=category_path,
                edit_after=bool(edit_after),
            )
        except Exception:
            self.map_status_var.set("Mapa: nie udalo sie utworzyc wpisu z mapy.")
            return {"ok": False, "reason": "entry_create_failed"}
        if isinstance(result, dict) and bool(result.get("ok")):
            msg = "Mapa: dodano wpis i otwarto edycje." if edit_after else "Mapa: dodano wpis."
            if result.get("category_path"):
                msg += f" Kategoria: {result.get('category_path')}."
            self.map_status_var.set(msg)
            return dict(result)
        self.map_status_var.set("Mapa: tworzenie wpisu anulowane lub nieudane.")
        return {"ok": False, "reason": "entry_create_rejected"}

    def _set_map_cursor(self, cursor_name: str) -> None:
        try:
            self.map_canvas.configure(cursor=str(cursor_name))
        except Exception as exc:
            _log_map_soft_failure(
                "set_cursor",
                "map canvas cursor configure failed",
                cursor=str(cursor_name),
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _star_type_token(value: Any) -> str:
        raw = _as_text(value).casefold()
        return "".join(ch for ch in raw if ch.isalnum())

    def _star_color_for_node(self, node: _MapNode) -> str:
        if int(getattr(node, "is_black_hole", 0) or 0):
            return COLOR_STAR_BLACK_HOLE
        if int(getattr(node, "is_neutron", 0) or 0):
            return COLOR_STAR_NEUTRON
        token = self._star_type_token(getattr(node, "primary_star_type", ""))
        if not token:
            return COLOR_NODE
        base = token[0]
        by_class = {
            "o": "#8bc5ff",
            "b": "#a4d1ff",
            "a": "#d5e7ff",
            "f": "#fff1b8",
            "g": "#ffd18a",
            "k": "#ffb56a",
            "m": "#ff8d67",
            "l": "#f4a261",
            "t": "#d9b3ff",
            "y": "#b9a1ff",
            "d": "#bde0fe",
        }
        return str(by_class.get(base, COLOR_NODE))

    def _star_label_for_node(self, node: _MapNode) -> str:
        star_type = _as_text(getattr(node, "primary_star_type", ""))
        if int(getattr(node, "is_black_hole", 0) or 0):
            return star_type or "Black Hole"
        if int(getattr(node, "is_neutron", 0) or 0):
            return star_type or "Neutron Star"
        return star_type or "-"

    def _tooltip_active_badges_for_node(self, node_key: str) -> list[str]:
        flags = dict((self._node_layer_flags or {}).get(str(node_key)) or {})
        out: list[str] = []
        if bool(self.layer_stations_var.get()) and bool(flags.get("has_station")):
            out.append("Stations")
        if bool(self.layer_trade_var.get()) and bool(flags.get("has_market")):
            out.append("Trade")
        if bool(self.layer_cashin_var.get()) and bool(flags.get("has_cashin")):
            out.append("Cash-In")
        if bool(self.layer_exobio_var.get()) and bool(flags.get("has_exobio")):
            out.append("Exobio")
        if bool(self.layer_exploration_var.get()) and bool(flags.get("has_exploration")):
            out.append("Exploration")
        if bool(self.layer_incidents_var.get()) and bool(flags.get("has_incident")):
            out.append("Incidents")
        if bool(self.layer_combat_var.get()) and bool(flags.get("has_combat")):
            out.append("Combat")
        return out

    def _tooltip_text_for_node(self, node: _MapNode) -> str:
        flags = dict((self._node_layer_flags or {}).get(node.key) or {})
        last_seen = _as_text(node.last_seen_ts or node.first_seen_ts)
        age = _format_age_short(last_seen)
        stations_count = int(flags.get("stations_count") or 0)
        badges = self._tooltip_active_badges_for_node(node.key)
        badges_text = ", ".join(badges) if badges else "-"
        return "\n".join(
            [
                f"System: {node.system_name}",
                f"Gwiazda: {self._star_label_for_node(node)}",
                f"Last seen: {age} ({last_seen or '-'})",
                f"Stacje: {stations_count}",
                f"Warstwy: {badges_text}",
            ]
        )

    def _show_map_tooltip(self, node: _MapNode, *, sx: int, sy: int) -> None:
        text = self._tooltip_text_for_node(node)
        c = self.map_canvas
        # Keep tooltip inside canvas viewport.
        x = int(sx) + 14
        y = int(sy) + 14
        cw = max(1, int(c.winfo_width() or 1))
        ch = max(1, int(c.winfo_height() or 1))
        if x > cw - 260:
            x = max(8, int(sx) - 250)
        if y > ch - 90:
            y = max(8, int(sy) - 74)

        c.delete("map_tooltip")
        text_id = c.create_text(
            x + 8,
            y + 6,
            text=text,
            anchor="nw",
            fill=COLOR_SEC,
            font=("Segoe UI", 8),
            tags=("map_tooltip", "map_tooltip_text"),
        )
        bbox = c.bbox(text_id)
        if bbox:
            x1, y1, x2, y2 = bbox
            c.create_rectangle(
                x1 - 6,
                y1 - 4,
                x2 + 6,
                y2 + 4,
                fill=COLOR_BG,
                outline=COLOR_ACCENT,
                width=1,
                tags=("map_tooltip", "map_tooltip_bg"),
            )
            c.tag_raise(text_id)
        self._tooltip_visible = True
        self._tooltip_node_key = str(node.key)
        self._tooltip_text_cache = text
        self._tooltip_last_pos = (int(sx), int(sy))

    def _hide_map_tooltip(self) -> None:
        try:
            self.map_canvas.delete("map_tooltip")
        except Exception as exc:
            _log_map_soft_failure(
                "tooltip_hide_delete",
                "delete map tooltip canvas tags failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        self._tooltip_visible = False
        self._tooltip_node_key = None
        self._tooltip_text_cache = ""
        self._tooltip_last_pos = None

    def _on_canvas_node_motion(self, event=None):
        if self._pan_active:
            self._hide_map_tooltip()
            return None
        sx = int(getattr(event, "x", 0))
        sy = int(getattr(event, "y", 0))
        key = self._node_key_from_canvas_current_item()
        if not key:
            # Fallback for thin glyphs/special markers where "current" may miss
            # the intended node hit area on some render paths.
            key = self._node_key_near_canvas_point(sx, sy, near_px=7)
        if not key:
            self._hide_map_tooltip()
            return None
        node = (self._nodes or {}).get(str(key))
        if node is None:
            self._hide_map_tooltip()
            return None
        text = self._tooltip_text_for_node(node)
        if (
            self._tooltip_visible
            and self._tooltip_node_key == str(node.key)
            and self._tooltip_text_cache == text
            and self._tooltip_last_pos is not None
            and abs(int(self._tooltip_last_pos[0]) - sx) < 3
            and abs(int(self._tooltip_last_pos[1]) - sy) < 3
        ):
            return None
        self._show_map_tooltip(node, sx=sx, sy=sy)
        return None

    def _on_canvas_node_leave(self, _event=None):
        self._hide_map_tooltip()
        return None

    def _on_star_legend_hover_enter(self, _event=None) -> None:
        if bool(getattr(self, "_star_legend_pinned", False)):
            return
        hide_id = getattr(self, "_star_legend_hide_after_id", None)
        if hide_id:
            try:
                self.after_cancel(hide_id)
            except Exception:
                pass
            self._star_legend_hide_after_id = None
        self._show_star_legend_popup()

    def _on_star_legend_hover_leave(self, _event=None) -> None:
        if bool(getattr(self, "_star_legend_pinned", False)):
            return
        try:
            self._star_legend_hide_after_id = str(self.after(120, self._hide_star_legend_popup))
        except Exception:
            self._hide_star_legend_popup()

    def _toggle_star_legend_popup(self) -> None:
        popup = getattr(self, "_star_legend_popup", None)
        if popup is not None:
            self._star_legend_pinned = False
            self._hide_star_legend_popup(force=True)
            return
        self._star_legend_pinned = True
        self._show_star_legend_popup()

    def _show_star_legend_popup(self) -> None:
        btn = getattr(self, "legend_star_info_btn", None)
        if btn is None:
            return
        popup = getattr(self, "_star_legend_popup", None)
        if popup is not None:
            try:
                popup.deiconify()
            except Exception:
                pass
            return
        try:
            popup = tk.Toplevel(self)
            popup.overrideredirect(True)
            popup.transient(self.winfo_toplevel())
            # Focus-safe: legend popup should never request topmost/foreground.
            try:
                popup.attributes("-topmost", False)
            except Exception:
                pass
            popup.configure(bg=COLOR_BG)
            frame = tk.Frame(popup, bg=COLOR_BG, bd=1, relief="solid")
            frame.pack(fill="both", expand=True)
            frame.columnconfigure(1, weight=1)
            title = tk.Label(frame, text="Legenda gwiazd", bg=COLOR_BG, fg=COLOR_FG, font=("Segoe UI", 9, "bold"))
            title.grid(row=0, column=0, sticky="w", padx=8, pady=(6, 4))
            close_btn = tk.Button(
                frame,
                text="x",
                command=self._toggle_star_legend_popup,
                bg=COLOR_ACCENT,
                fg=COLOR_FG,
                relief="flat",
                width=2,
            )
            close_btn.grid(row=0, column=1, sticky="e", padx=(0, 6), pady=(4, 2))
            legend_rows = [
                (COLOR_STAR_NEUTRON, "Neutron Star"),
                (COLOR_STAR_BLACK_HOLE, "Black Hole"),
                ("#8bc5ff", "Klasy O/B/A"),
                ("#fff1b8", "Klasy F/G"),
                ("#ff8d67", "Klasy K/M/L"),
                ("#d9b3ff", "Klasy T/Y"),
                ("#bde0fe", "Biale karly"),
            ]
            for idx, (color, label) in enumerate(legend_rows, start=1):
                swatch = tk.Canvas(frame, width=12, height=12, bg=COLOR_BG, highlightthickness=0)
                swatch.grid(row=idx, column=0, sticky="w", padx=(8, 6), pady=2)
                swatch.create_rectangle(1, 1, 11, 11, outline=color, fill=color)
                tk.Label(frame, text=label, bg=COLOR_BG, fg=COLOR_SEC, anchor="w").grid(
                    row=idx, column=1, sticky="w", padx=(0, 8), pady=2
                )
            popup.bind("<Escape>", lambda _e: self._toggle_star_legend_popup())
            x = int(btn.winfo_rootx())
            y = int(btn.winfo_rooty() + btn.winfo_height() + 2)
            popup.geometry(f"+{x}+{y}")
            self._star_legend_popup = popup
            try:
                self.legend_star_info_btn.configure(relief="sunken")
            except Exception:
                pass
        except Exception as exc:
            _log_map_soft_failure(
                "legend_star_popup_show",
                "show star legend popup failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _hide_star_legend_popup(self, *_args, force: bool = False) -> None:
        hide_id = getattr(self, "_star_legend_hide_after_id", None)
        if hide_id:
            try:
                self.after_cancel(hide_id)
            except Exception:
                pass
            self._star_legend_hide_after_id = None
        popup = getattr(self, "_star_legend_popup", None)
        if popup is None:
            return
        try:
            popup.destroy()
        except Exception:
            if not force:
                raise
        finally:
            self._star_legend_popup = None
            self._star_legend_pinned = False
            try:
                self.legend_star_info_btn.configure(relief="flat")
            except Exception:
                pass

    def _on_legend_body_frame_configure(self, _event=None) -> None:
        self._sync_legend_scrollregion()

    def _on_legend_canvas_configure(self, event=None) -> None:
        try:
            width = int(getattr(event, "width", 0) or self.legend_body_canvas.winfo_width() or 0)
            if width > 0:
                self.legend_body_canvas.itemconfigure(self._legend_body_window_id, width=width)
        except Exception:
            pass
        self._sync_legend_scrollregion()

    def _on_legend_mousewheel_up(self, event=None):
        return self._on_legend_mousewheel(_WheelShim(event, delta=120))

    def _on_legend_mousewheel_down(self, event=None):
        return self._on_legend_mousewheel(_WheelShim(event, delta=-120))

    def _on_legend_mousewheel(self, event) -> str | None:
        canvas = getattr(self, "legend_body_canvas", None)
        if canvas is None:
            return None
        try:
            top, bottom = canvas.yview()
            # No scroll range, but consume wheel so map zoom/pan under the panel is not triggered.
            if (bottom - top) >= 0.9999:
                return "break"
            delta = float(getattr(event, "delta", 0))
            if delta == 0:
                return "break"
            step = max(1, int(abs(delta) / 120.0))
            units = -step if delta > 0 else step
            canvas.yview_scroll(units, "units")
            return "break"
        except Exception:
            return None

    def _bind_legend_mousewheel_recursive(self, widget: Any) -> None:
        if widget is None:
            return
        try:
            if not bool(getattr(widget, "_renata_legend_wheel_bound", False)):
                widget.bind("<MouseWheel>", self._on_legend_mousewheel)
                widget.bind("<Button-4>", self._on_legend_mousewheel_up)
                widget.bind("<Button-5>", self._on_legend_mousewheel_down)
                setattr(widget, "_renata_legend_wheel_bound", True)
        except Exception:
            pass
        try:
            for child in list(widget.winfo_children()):
                self._bind_legend_mousewheel_recursive(child)
        except Exception:
            return

    def _sync_legend_scrollregion(self) -> None:
        try:
            self.legend_body_canvas.update_idletasks()
            bbox = self.legend_body_canvas.bbox("all")
            if bbox:
                self.legend_body_canvas.configure(scrollregion=bbox)
        except Exception:
            pass

    def _toggle_legend(self) -> None:
        collapsed = not bool(self.legend_collapsed_var.get())
        self.legend_collapsed_var.set(collapsed)
        try:
            if collapsed:
                self.legend_body_host.grid_remove()
                self.legend_toggle_text_var.set("Pokaz")
            else:
                self.legend_body_host.grid()
                self.legend_toggle_text_var.set("Ukryj")
        except Exception as exc:
            _log_map_soft_failure(
                "toggle_legend",
                "toggle legend widgets failed",
                collapsed=bool(collapsed),
                error=f"{type(exc).__name__}: {exc}",
            )
        self._refresh_legend()
        self._notify_owner_ui_state_changed()

    def _refresh_legend(self) -> None:
        lines: list[str] = []
        self._legend_clear_visual_rows()
        if bool(self.legend_collapsed_var.get()):
            self.legend_text_var.set("")
            self._sync_legend_scrollregion()
            return

        row_idx = 0
        row_idx = self._legend_add_section_title("Znaczniki", row=row_idx)
        row_idx = self._legend_add_icon_row("selected", "Biala otoczka = wybrany system", row=row_idx)
        row_idx = self._legend_add_icon_row("current", "Zielona otoczka = aktualny system gracza", row=row_idx)
        lines.extend(
            [
                "Znaczniki:",
                "Biala otoczka = wybrany system",
                "Zielona otoczka = aktualny system gracza",
            ]
        )

        active_items: list[tuple[str, str]] = []
        if bool(self.layer_stations_var.get()):
            active_items.append(("stations", "Znane stacje w systemie"))
        if bool(self.layer_trade_var.get()):
            active_items.append(("trade", "Znany rynek (Trade)"))
        if bool(self.layer_cashin_var.get()):
            active_items.append(("cashin", "Znane UC/Vista na stacjach (Cash-In)"))
        if bool(self.layer_exploration_var.get()):
            active_items.append(("exploration", "Historia eksploracji (cash-in UC)"))
        if bool(self.layer_exobio_var.get()):
            active_items.append(("exobio", "Historia exobio (cash-in Vista)"))
        if bool(self.layer_incidents_var.get()):
            if bool((self._action_layers_meta or {}).get("supports_incidents")):
                active_items.append(("incidents", "Incydenty"))
            else:
                active_items.append(("incidents_off", "Incidents: brak danych w playerdb (future)"))
        if bool(self.layer_combat_var.get()):
            if bool((self._action_layers_meta or {}).get("supports_combat")):
                active_items.append(("combat", "Combat"))
            else:
                active_items.append(("combat_off", "Combat: brak danych w playerdb (future)"))

        if active_items:
            lines.append("")
            lines.append("Aktywne warstwy:")
            row_idx = self._legend_add_section_title("Aktywne warstwy", row=row_idx, top_pad=6)
            for key, label in active_items:
                row_idx = self._legend_add_icon_row(key, label, row=row_idx)
                lines.append(label)
        self.legend_text_var.set("\n".join(lines))
        self._sync_legend_scrollregion()
        self._bind_legend_mousewheel_recursive(self.legend_body_frame)

    def _legend_clear_visual_rows(self) -> None:
        for child in list(self.legend_body_frame.winfo_children()):
            try:
                child.destroy()
            except Exception:
                continue

    def _legend_add_section_title(self, text: str, *, row: int, top_pad: int = 2) -> int:
        lbl = tk.Label(
            self.legend_body_frame,
            text=str(text),
            bg=COLOR_BG,
            fg=COLOR_FG,
            anchor="w",
            justify="left",
            font=("Segoe UI", 9, "bold"),
        )
        lbl.grid(row=row, column=0, sticky="ew", pady=(top_pad, 2))
        return row + 1

    def _legend_add_icon_row(self, icon_key: str, text: str, *, row: int) -> int:
        row_frame = tk.Frame(self.legend_body_frame, bg=COLOR_BG)
        row_frame.grid(row=row, column=0, sticky="ew", pady=1)
        row_frame.columnconfigure(1, weight=1)
        icon = tk.Canvas(row_frame, width=20, height=14, bg=COLOR_BG, highlightthickness=0)
        icon.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._draw_legend_icon(icon, icon_key)
        fg = COLOR_SEC if not icon_key.endswith("_off") else "#9ca3af"
        tk.Label(
            row_frame,
            text=str(text),
            bg=COLOR_BG,
            fg=fg,
            anchor="w",
            justify="left",
            wraplength=248,
        ).grid(row=0, column=1, sticky="ew")
        return row + 1

    def _draw_legend_icon(self, canvas: tk.Canvas, icon_key: str) -> None:
        canvas.delete("all")
        cx, cy = 8, 7
        r = 3
        # Base star glyph
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=COLOR_NODE, fill=COLOR_NODE)
        if icon_key == "selected":
            rr = r + 3
            canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=COLOR_SELECTED_RING, width=1.6)
            return
        if icon_key == "current":
            rr = r + 3
            canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=COLOR_CURRENT_RING, width=1.6)
            return
        if icon_key == "stations":
            rr = r + 2
            canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=COLOR_STATION_LAYER, width=1.2)
            return
        if icon_key == "trade":
            s = 2.6
            canvas.create_rectangle(
                cx + r + 1,
                cy - r - 1,
                cx + r + 1 + (s * 2),
                cy - r - 1 + (s * 2),
                outline=COLOR_TRADE_LAYER,
                fill=COLOR_TRADE_LAYER,
            )
            return
        if icon_key == "cashin":
            d = 3
            canvas.create_polygon(
                cx,
                cy + r + 1,
                cx + d,
                cy + r + 1 + d,
                cx,
                cy + r + 1 + (d * 2),
                cx - d,
                cy + r + 1 + d,
                outline=COLOR_CASHIN_LAYER,
                fill=COLOR_CASHIN_LAYER,
            )
            return
        if icon_key == "exploration":
            rr = 2.4
            canvas.create_oval(
                cx - rr,
                cy + r + 2 - rr,
                cx + rr,
                cy + r + 2 + rr,
                outline=COLOR_EXPLORATION_LAYER,
                fill=COLOR_EXPLORATION_LAYER,
            )
            return
        if icon_key == "exobio":
            rr = 2.4
            canvas.create_oval(
                cx - rr,
                cy + r + 2 - rr,
                cx + rr,
                cy + r + 2 + rr,
                outline=COLOR_EXOBIO_LAYER,
                fill=COLOR_EXOBIO_LAYER,
            )
            return
        if icon_key == "incidents":
            rr = 2.4
            canvas.create_oval(
                cx - rr,
                cy + r + 2 - rr,
                cx + rr,
                cy + r + 2 + rr,
                outline=COLOR_INCIDENT_LAYER,
                fill=COLOR_INCIDENT_LAYER,
            )
            return
        if icon_key == "combat":
            rr = 2.4
            canvas.create_oval(
                cx - rr,
                cy + r + 2 - rr,
                cx + rr,
                cy + r + 2 + rr,
                outline=COLOR_COMBAT_LAYER,
                fill=COLOR_COMBAT_LAYER,
            )
            return

    def _on_filter_changed(self) -> None:
        # Invalidate tooltip immediately so stale badges/text are not shown
        # while filter/layer reload is pending or fails early.
        self._hide_map_tooltip()
        self._notify_owner_ui_state_changed()
        self._schedule_filter_reload_debounce()

    def _notify_owner_ui_state_changed(self) -> None:
        owner = getattr(self, "logbook_owner", None)
        if owner is None:
            return
        callback = getattr(owner, "_persist_ui_state", None)
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                _log_map_soft_failure(
                    "notify_owner_ui_state",
                    "owner ui state persist callback failed",
                    error=f"{type(exc).__name__}: {exc}",
                )

    def _is_map_subtab_active(self) -> bool:
        owner = getattr(self, "logbook_owner", None)
        resolver = getattr(owner, "_resolve_active_subtab_key", None)
        if callable(resolver):
            try:
                return str(resolver() or "") == "map"
            except Exception:
                return True
        return True

    def _is_journal_main_tab_active(self) -> bool:
        app_obj = getattr(self, "app", None)
        resolver = getattr(app_obj, "_resolve_active_main_tab_key", None)
        if callable(resolver):
            try:
                key = str(resolver() or "").strip().lower()
                if key:
                    return key == "journal"
            except Exception:
                return True
        return True

    def _is_map_runtime_visible_for_auto_refresh(self) -> bool:
        # Runtime-visible means both:
        # - Logbook subtab "Mapa" is selected,
        # - top-level main tab is "Dziennik" (when resolver is available).
        # Main-tab bridge (RenataApp -> LogbookTab -> map activation callback) handles deferred resume.
        return bool(self._is_map_subtab_active()) and bool(self._is_journal_main_tab_active())

    def _cancel_auto_refresh_debounce(self) -> None:
        after_id = getattr(self, "_auto_refresh_after_id", None)
        self._auto_refresh_after_id = None
        if not after_id:
            return
        try:
            self.after_cancel(after_id)
        except Exception as exc:
            _log_map_soft_failure(
                "cancel_auto_refresh_debounce",
                "cancel auto refresh debounce failed",
                after_id=str(after_id),
                error=f"{type(exc).__name__}: {exc}",
            )

    def _cancel_filter_reload_debounce(self) -> None:
        after_id = getattr(self, "_filter_reload_after_id", None)
        self._filter_reload_after_id = None
        if not after_id:
            return
        try:
            self.after_cancel(after_id)
        except Exception as exc:
            _log_map_soft_failure(
                "cancel_filter_reload_debounce",
                "cancel filter reload debounce failed",
                after_id=str(after_id),
                error=f"{type(exc).__name__}: {exc}",
            )

    def _schedule_filter_reload_debounce(self, *, delay_ms: int | None = None) -> None:
        self._cancel_filter_reload_debounce()
        delay = int(delay_ms if delay_ms is not None else self._filter_reload_debounce_ms)
        try:
            self._filter_reload_after_id = str(self.after(delay, self._run_debounced_filter_reload))
        except Exception:
            self._filter_reload_after_id = None

    def _run_debounced_filter_reload(self) -> None:
        self._filter_reload_after_id = None
        self.reload_from_playerdb()

    def _schedule_auto_refresh_debounce(self, *, delay_ms: int | None = None) -> None:
        self._cancel_auto_refresh_debounce()
        delay = int(delay_ms if delay_ms is not None else self._auto_refresh_debounce_ms)
        try:
            self._auto_refresh_after_id = str(self.after(delay, self._run_debounced_auto_refresh))
        except Exception:
            self._auto_refresh_after_id = None

    def notify_playerdb_updated(self, payload: dict | None = None) -> dict[str, Any]:
        data = dict(payload or {}) if isinstance(payload, dict) else {}
        source = _as_text(data.get("source")) or "unknown"
        event_name = _as_text(data.get("event_name")) or "unknown"
        self._auto_refresh_last_update = {"source": source, "event_name": event_name}
        self._auto_refresh_dirty = True
        if self._is_map_runtime_visible_for_auto_refresh():
            self._schedule_auto_refresh_debounce()
            return {"ok": True, "scheduled": True, "deferred": False, "source": source, "event_name": event_name}
        return {"ok": True, "scheduled": False, "deferred": True, "source": source, "event_name": event_name}

    def on_parent_map_subtab_activated(self) -> None:
        if bool(self._auto_refresh_dirty):
            self._schedule_auto_refresh_debounce(delay_ms=120)

    def _run_debounced_auto_refresh(self) -> None:
        self._auto_refresh_after_id = None
        if not bool(self._auto_refresh_dirty):
            return
        if not self._is_map_runtime_visible_for_auto_refresh():
            return

        selected_key = str(self._selected_node_key or "").strip() or None
        selected_system_name = ""
        if selected_key:
            prev_node = self._nodes.get(selected_key)
            if prev_node is not None:
                selected_system_name = _as_text(getattr(prev_node, "system_name", ""))
        self._auto_refresh_dirty = False
        result = self.reload_from_playerdb()

        reselected = False
        compare_refreshed = False
        reselect_key: str | None = None
        if selected_key and selected_key in self._nodes:
            reselect_key = selected_key
        elif selected_system_name:
            reselect_key = self._find_node_key_by_system_name(selected_system_name)
        if reselect_key:
            try:
                sel_result = self.select_system_node(reselect_key)
                reselected = bool(isinstance(sel_result, dict) and sel_result.get("ok"))
                compare_refreshed = reselected
            except Exception as exc:
                _log_map_soft_failure(
                    "auto_refresh_reselect",
                    "reselect node after auto refresh failed",
                    node_key=str(reselect_key),
                    error=f"{type(exc).__name__}: {exc}",
                )
                reselected = False
                compare_refreshed = False

        if not compare_refreshed:
            try:
                self._refresh_trade_compare_if_needed()
            except Exception as exc:
                _log_map_soft_failure(
                    "auto_refresh_trade_compare",
                    "refresh trade compare after auto refresh failed",
                    error=f"{type(exc).__name__}: {exc}",
                )

        info = dict(self._auto_refresh_last_update or {})
        event_name = _as_text(info.get("event_name")) or "playerdb"
        source = _as_text(info.get("source")) or "playerdb"
        if isinstance(result, dict) and bool(result.get("ok")):
            parts = ["Mapa: auto-refresh po update playerdb"]
            if event_name:
                parts.append(f"{event_name}/{source}")
            if reselected:
                parts.append("zachowano selekcje")
            elif selected_key:
                self._selected_node_key = None
                parts.append("utracono selekcje (system poza filtrami)")
            try:
                self.map_status_var.set(" | ".join(parts))
            except Exception as exc:
                _log_map_soft_failure(
                    "auto_refresh_status",
                    "set auto refresh map status failed",
                    error=f"{type(exc).__name__}: {exc}",
                )

    def _find_node_key_by_system_name(self, system_name: str) -> str | None:
        target = _as_text(system_name)
        if not target:
            return None
        target_cf = target.casefold()
        for key, node in (self._nodes or {}).items():
            node_name = _as_text(getattr(node, "system_name", ""))
            if node_name and node_name.casefold() == target_cf:
                return str(key)
        return None

    def set_graph_data(self, *, nodes: list[dict[str, Any]] | None = None, edges: list[dict[str, Any]] | None = None) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._selected_node_key = None
        for row in nodes or []:
            key = self._node_key_from_row(row)
            if not key:
                continue
            x = self._safe_float(row.get("x"))
            y = self._safe_float(row.get("y"))
            if x is None or y is None:
                continue
            try:
                node = _MapNode(
                    key=key,
                    system_name=str(row.get("system_name") or key),
                    x=x,
                    y=y,
                    z=self._safe_float(row.get("z")),
                    system_address=int(row["system_address"]) if row.get("system_address") is not None else None,
                    system_id64=int(row["system_id64"]) if row.get("system_id64") is not None else None,
                    source=str(row.get("source") or "playerdb"),
                    confidence=str(row.get("confidence") or "observed"),
                    freshness_ts=str(row.get("freshness_ts") or ""),
                    first_seen_ts=str(row.get("first_seen_ts") or ""),
                    last_seen_ts=str(row.get("last_seen_ts") or ""),
                    primary_star_type=str(row.get("primary_star_type") or ""),
                    is_neutron=int(bool(row.get("is_neutron"))) if row.get("is_neutron") is not None else 0,
                    is_black_hole=int(bool(row.get("is_black_hole"))) if row.get("is_black_hole") is not None else 0,
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
        if bool(self.last_session_only_var.get()):
            return self._passes_last_session_filter(value)
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
        if bool(self.last_session_only_var.get()):
            out: list[dict[str, Any]] = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                candidate_ts = ""
                for key in ts_keys:
                    candidate_ts = _as_text(row.get(key))
                    if candidate_ts:
                        break
                if self._passes_last_session_filter(candidate_ts):
                    out.append(dict(row))
            return out
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

    def _prepare_renderable_nodes(self, rows: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], int]:
        out: list[dict[str, Any]] = []
        dropped = 0
        for row in rows or []:
            if not isinstance(row, dict):
                dropped += 1
                continue
            key = self._node_key_from_row(row)
            x = self._safe_float(row.get("x"))
            y = self._safe_float(row.get("y"))
            if not key or x is None or y is None:
                dropped += 1
                continue
            item = dict(row)
            item["key"] = key
            item["x"] = x
            item["y"] = y
            out.append(item)
        return out, dropped

    def _clear_prefetched_system_stations(self) -> None:
        self._prefetched_system_stations = {}

    def _prime_prefetched_system_stations(self, nodes_rows: list[dict[str, Any]]) -> None:
        self._clear_prefetched_system_stations()
        if not nodes_rows:
            return
        getter = getattr(self.data_provider, "get_stations_for_systems", None)
        if not callable(getter):
            return
        try:
            cached, _meta = getter(
                systems=nodes_rows,
                limit_per_system=200,
            )
        except Exception as exc:
            _log_map_soft_failure(
                "prime_prefetched_system_stations",
                "batch stations prefetch for map drilldown failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        if isinstance(cached, dict):
            self._prefetched_system_stations = dict(cached)

    def _prefetched_stations_for_node(self, node: _MapNode) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
        cache = dict(getattr(self, "_prefetched_system_stations", {}) or {})
        if not cache:
            return None
        lookup_keys: list[str] = []
        if getattr(node, "system_address", None) is not None:
            try:
                lookup_keys.append(f"addr:{int(node.system_address)}")
            except Exception:
                pass
        system_name = _as_text(getattr(node, "system_name", ""))
        if system_name:
            lookup_keys.append(f"name:{system_name.casefold()}")
        for lookup_key in lookup_keys:
            item = cache.get(lookup_key)
            if not isinstance(item, dict):
                continue
            rows = [dict(r) for r in list(item.get("rows") or []) if isinstance(r, dict)]
            meta = dict(item.get("meta") or {})
            if rows or meta:
                return rows, meta
        return None

    def _compute_layer_flags_for_nodes(self, nodes_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        flags_by_key: dict[str, dict[str, Any]] = {}
        if not nodes_rows:
            self._action_layers_meta = {}
            return flags_by_key
        action_flags_by_system_cf: dict[str, dict[str, Any]] = {}
        self._action_layers_meta = {}
        system_names = [
            _as_text(dict(r).get("system_name"))
            for r in (nodes_rows or [])
            if isinstance(r, dict) and _as_text(dict(r).get("system_name"))
        ]
        getter = getattr(self.data_provider, "get_system_action_flags", None)
        if callable(getter):
            try:
                action_flags_by_system_cf, action_meta = getter(
                    system_names=system_names,
                    time_range=self._effective_time_range_filter(),
                    freshness_filter=self._effective_freshness_filter(),
                    limit=max(100, len(system_names) * 2),
                )
                if not isinstance(action_flags_by_system_cf, dict):
                    action_flags_by_system_cf = {}
                self._action_layers_meta = dict(action_meta or {})
            except Exception:
                action_flags_by_system_cf = {}
                self._action_layers_meta = {"error": True}

        station_flags_batch: dict[str, dict[str, Any]] = {}
        station_flags_batch_error = False
        batch_getter = getattr(self.data_provider, "get_station_layer_flags_for_systems", None)
        if callable(batch_getter):
            try:
                station_flags_batch, _batch_meta = batch_getter(
                    systems=nodes_rows,
                    freshness_filter=self._effective_freshness_filter(),
                    limit_per_system=200,
                )
                if not isinstance(station_flags_batch, dict):
                    station_flags_batch = {}
            except Exception:
                station_flags_batch = {}
                station_flags_batch_error = True

        for row in nodes_rows:
            if not isinstance(row, dict):
                continue
            key = self._node_key_from_row(row)
            if not key:
                continue
            system_address = row.get("system_address")
            system_name = _as_text(row.get("system_name"))
            lookup_keys: list[str] = []
            if system_address is not None:
                try:
                    lookup_keys.append(f"addr:{int(system_address)}")
                except Exception:
                    pass
            if system_name:
                lookup_keys.append(f"name:{system_name.casefold()}")

            station_flags = None
            for lookup_key in lookup_keys:
                candidate = station_flags_batch.get(lookup_key)
                if isinstance(candidate, dict):
                    station_flags = candidate
                    break

            if station_flags is not None:
                stations_count = int(station_flags.get("stations_count") or 0)
                has_station = stations_count > 0
                has_market = bool(station_flags.get("has_market"))
                has_cashin = bool(station_flags.get("has_cashin"))
                station_error = bool(station_flags_batch_error)
            else:
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
                stations_count = len(filtered)
                has_station = stations_count > 0
                has_market = any(bool((dict(r).get("services") or {}).get("has_market")) for r in filtered)
                has_cashin = any(
                    bool((dict(r).get("services") or {}).get("has_uc"))
                    or bool((dict(r).get("services") or {}).get("has_vista"))
                    for r in filtered
                )
                station_error = False
            activity = dict(action_flags_by_system_cf.get(system_name.casefold()) or {})
            flags_by_key[key] = {
                "has_station": bool(has_station),
                "has_market": bool(has_market),
                "has_cashin": bool(has_cashin),
                "has_exobio": bool(activity.get("has_exobio")),
                "has_exploration": bool(activity.get("has_exploration")),
                "has_incident": bool(activity.get("has_incident")),
                "has_combat": bool(activity.get("has_combat")),
                "stations_count": int(stations_count),
                "action_freshness_ts": _as_text(activity.get("last_action_ts")),
                "error": bool(station_error),
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

    def _coords_layout_from_system_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Mapa (coords) layout: rzutuje rzeczywiste wspolrzedne galaktyczne (StarPos x, z) na 2D.

        Konwencja ED:
          x = galaktyczny wschod/zachod, z = galaktyczny N/S (ku rdzeniowi), y = wysokosc (ignorujemy).
        Rzut top-down: x -> canvas_x, z -> canvas_y (z invertowane, zeby N byl u gory).
        Tryb Mapa pokazuje tylko systemy z realnymi koordynatami (x/z), bez fallback-strip.
        """
        SCALE_TARGET = 160.0  # docelowe jednostki canvas (podobny zakres co travel layout)

        with_coords = [
            dict(r) for r in rows
            if isinstance(r, dict) and r.get("x") is not None and r.get("z") is not None
        ]
        if not with_coords:
            return []

        xs = [float(r["x"]) for r in with_coords]
        zs = [float(r["z"]) for r in with_coords]
        min_x, max_x = min(xs), max(xs)
        min_z, max_z = min(zs), max(zs)
        range_x = max(max_x - min_x, 1.0)
        range_z = max(max_z - min_z, 1.0)

        # Uniform scale - dłuższa oś dopasowana do SCALE_TARGET
        scale = SCALE_TARGET / max(range_x, range_z)

        out: list[dict[str, Any]] = []
        for row in with_coords:
            item = dict(row)
            item["x"] = (float(row["x"]) - min_x) * scale
            # Invertujemy z - galaktyczna polnoc jest u gory (mniejsze canvas_y)
            item["y"] = (max_z - float(row["z"])) * scale
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
        self._trade_compare_rows_by_iid.clear()
        nodes_count = len(self._nodes)
        edges_count = len(self._edges)
        self.system_details_var.set(
            f"Travel layer: {nodes_count} systemow | {edges_count} krawedzi | "
            f"time={'last_session' if bool(self.last_session_only_var.get()) else _as_text(self.time_range_var.get())} "
            f"| freshness={'session' if bool(self.last_session_only_var.get()) else _as_text(self.freshness_var.get())}"
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
                (
                    f"warstwy: T={int(bool(self.layer_travel_var.get()))}"
                    f"/S={int(bool(self.layer_stations_var.get()))}"
                    f"/Tr={int(bool(self.layer_trade_var.get()))}"
                    f"/C={int(bool(self.layer_cashin_var.get()))}"
                    f"/Ex={int(bool(self.layer_exobio_var.get()))}"
                    f"/Xp={int(bool(self.layer_exploration_var.get()))}"
                    f"/I={int(bool(self.layer_incidents_var.get()))}"
                    f"/Cb={int(bool(self.layer_combat_var.get()))}"
                ),
            ),
        )
        self._sync_trade_highlight_button_state()

    def reload_from_playerdb(self) -> dict[str, Any]:
        self._sync_time_filter_controls_from_vars()
        self._sync_time_filter_controls_enabled()
        if not bool(self.layer_travel_var.get()):
            self.set_graph_data(nodes=[], edges=[])
            self._node_layer_flags = {}
            self._clear_prefetched_system_stations()
            self._travel_nodes_meta = {"count": 0, "disabled": True}
            self._travel_edges_meta = {"count": 0, "disabled": True}
            self._action_layers_meta = {}
            self._refresh_system_panel_stub()
            self._refresh_legend()
            self.map_status_var.set("Mapa: warstwa Travel jest wylaczona. Wlacz Travel, aby zobaczyc systemy.")
            return {"ok": True, "travel_enabled": False, "nodes": 0, "edges": 0}

        time_range = self._effective_time_range_filter()
        freshness_filter = self._effective_freshness_filter()
        source_filter = self._source_filter_mode()
        nodes_rows, nodes_meta = self.data_provider.get_system_nodes(time_range=time_range, source_filter=source_filter)
        edges_rows, edges_meta = self.data_provider.get_edges(time_range=time_range)
        nodes_rows = self._filter_rows_by_freshness(nodes_rows, ts_keys=("freshness_ts", "last_seen_ts", "first_seen_ts"))

        render_mode = _as_text(self.render_mode_var.get() or "Trasa")
        hidden_without_coords = 0
        if render_mode == "Mapa":
            hidden_without_coords = sum(
                1
                for r in nodes_rows
                if isinstance(r, dict) and (r.get("x") is None or r.get("z") is None)
            )
        if render_mode == "Mapa":
            laid_out_nodes = self._coords_layout_from_system_rows(nodes_rows)
        else:
            laid_out_nodes = self._travel_layout_from_system_rows(nodes_rows)
        render_nodes, dropped_nodes = self._prepare_renderable_nodes(laid_out_nodes)
        if edges_rows:
            edges_final = edges_rows
            edges_mode = "provider"
        else:
            edges_final = self._build_fallback_sequential_edges(render_nodes)
            edges_mode = "sequential_fallback"

        self._travel_nodes_meta = dict(nodes_meta or {})
        self._travel_edges_meta = dict(edges_meta or {})
        self._travel_edges_meta["render_mode"] = edges_mode
        self._node_layer_flags = self._compute_layer_flags_for_nodes(render_nodes)
        self._prime_prefetched_system_stations(render_nodes)

        self.set_graph_data(nodes=render_nodes, edges=edges_final)
        startup_center = self._try_startup_autocenter()
        self._refresh_system_panel_stub()
        self._refresh_trade_commodity_values()
        self._refresh_trade_compare_if_needed()

        count_nodes = len(self._nodes)
        count_edges = len(self._edges)
        status_reason = ""
        if edges_mode == "sequential_fallback":
            status_reason = " | krawedzie: fallback sekwencyjny (brak ingestu jumps)"
        if render_mode == "Mapa" and hidden_without_coords > 0:
            status_reason += f" | ukryto {int(hidden_without_coords)} systemow bez koordynatow (tryb Mapa)"
        if dropped_nodes > 0:
            status_reason += f" | pominieto {int(dropped_nodes)} nodow bez poprawnych koordynatow"
        if bool(startup_center.get("applied")):
            target = _as_text(startup_center.get("target")) or "current"
            status_reason += f" | startup-center={target}"
        layer_state = (
            f" | layers T={int(bool(self.layer_travel_var.get()))}"
            f"/S={int(bool(self.layer_stations_var.get()))}"
            f"/Tr={int(bool(self.layer_trade_var.get()))}"
            f"/C={int(bool(self.layer_cashin_var.get()))}"
            f"/Ex={int(bool(self.layer_exobio_var.get()))}"
            f"/Xp={int(bool(self.layer_exploration_var.get()))}"
            f"/I={int(bool(self.layer_incidents_var.get()))}"
            f"/Cb={int(bool(self.layer_combat_var.get()))}"
        )
        if count_nodes <= 0:
            if render_mode == "Mapa":
                status_reason += " | Brak systemow z koordynatami w tym zakresie"
            else:
                status_reason += " | brak danych po filtrach (time/freshness/source)"
        self.map_status_var.set(
            f"Mapa {render_mode}: {count_nodes} systemow / {count_edges} krawedzi | "
            f"time={'last_session' if bool(self.last_session_only_var.get()) else time_range} "
            f"| freshness={'session' if bool(self.last_session_only_var.get()) else freshness_filter} "
            f"| source={source_filter}{status_reason}{layer_state}"
        )
        self._refresh_legend()
        return {
            "ok": True,
            "travel_enabled": True,
            "nodes": count_nodes,
            "edges": count_edges,
            "startup_center": dict(startup_center or {}),
            "dropped_nodes": int(dropped_nodes),
            "hidden_without_coords": int(hidden_without_coords),
            "edges_mode": edges_mode,
            "nodes_meta": dict(nodes_meta or {}),
            "edges_meta": dict(edges_meta or {}),
        }

    def _block_startup_autocenter_by_user(self) -> None:
        if bool(getattr(self, "_startup_autocenter_done", False)):
            self._startup_autocenter_recenter_pending = False
            return
        self._startup_autocenter_pending = False
        self._startup_autocenter_user_blocked = True
        self._startup_autocenter_recenter_pending = False

    def _try_startup_autocenter(self) -> dict[str, Any]:
        if bool(getattr(self, "_startup_autocenter_user_blocked", False)):
            self._startup_autocenter_pending = False
            return {"applied": False, "reason": "user_blocked"}
        if bool(getattr(self, "_startup_autocenter_done", False)):
            self._startup_autocenter_pending = False
            return {"applied": False, "reason": "already_done"}
        if not bool(getattr(self, "_startup_autocenter_pending", False)):
            return {"applied": False, "reason": "not_pending"}
        if not bool(self._nodes):
            return {"applied": False, "reason": "no_nodes"}

        current_node = self._find_current_system_rendered_node()
        if current_node is not None:
            self._center_world_point(float(current_node.x), float(current_node.y))
            self._redraw_scene()
            self._startup_autocenter_done = True
            self._startup_autocenter_pending = False
            self._startup_autocenter_recenter_pending = True
            return {
                "applied": True,
                "reason": "current_system_node",
                "target": _as_text(getattr(current_node, "system_name", "")),
            }

        current_star_pos = getattr(app_state, "current_star_pos", None)
        if isinstance(current_star_pos, (list, tuple)) and len(current_star_pos) >= 3:
            try:
                wx = float(current_star_pos[0])
                wy = float(current_star_pos[2])  # x/z -> 2D (shell fallback)
                self._center_world_point(wx, wy)
                self._redraw_scene()
                self._startup_autocenter_done = True
                self._startup_autocenter_pending = False
                self._startup_autocenter_recenter_pending = True
                return {"applied": True, "reason": "current_star_pos_fallback", "target": "current_star_pos"}
            except Exception as exc:
                _log_map_soft_failure(
                    "startup_autocenter_starpos_fallback",
                    "startup auto-center fallback current StarPos failed",
                    current_star_pos=str(current_star_pos),
                    error=f"{type(exc).__name__}: {exc}",
                )

        if _as_text(getattr(app_state, "current_system", "")):
            return {"applied": False, "reason": "current_system_not_visible"}
        return {"applied": False, "reason": "no_current_context"}

    def _refresh_trade_commodity_values(self) -> None:
        try:
            values, _meta = self.data_provider.get_known_commodities(
                time_range=self._effective_time_range_filter(),
                freshness_filter=self._effective_freshness_filter(),
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
        except Exception as exc:
            _log_map_soft_failure(
                "trade_combo_values",
                "refresh trade commodity values failed",
                count=len(merged),
                error=f"{type(exc).__name__}: {exc}",
            )
        self._trade_picker_available = list(merged)
        self._trade_picker_selected = {
            item for item in self._trade_picker_selected
            if any(item.casefold() == str(v).casefold() for v in merged)
        }
        self._sync_trade_selected_summary()
        self._refresh_trade_picker_rows_if_open()
        self._sync_trade_highlight_button_state()

    def _sync_trade_highlight_button_state(self) -> None:
        commodity = _as_text(self.trade_compare_commodity_var.get())
        state = "normal" if (commodity or self._trade_selected_commodities) else "disabled"
        try:
            self.trade_highlight_btn.configure(state=state)
            self.trade_clear_btn.configure(state=state)
        except Exception as exc:
            _log_map_soft_failure(
                "trade_highlight_button_state",
                "sync trade highlight button state failed",
                state=state,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _sync_trade_selected_summary(self) -> None:
        selected = list(self._trade_selected_commodities or [])
        if not selected:
            self.trade_selected_summary_var.set("Brak wybranych towarow.")
            return
        preview = ", ".join(selected[:3])
        suffix = f" (+{len(selected) - 3})" if len(selected) > 3 else ""
        self.trade_selected_summary_var.set(f"Wybrane towary ({len(selected)}): {preview}{suffix}")

    def _on_trade_commodity_changed(self, _event=None):
        self._sync_trade_highlight_button_state()
        return None

    def _refresh_trade_compare_if_needed(self) -> None:
        if not bool(self.layer_trade_var.get()):
            if self._trade_highlight_node_keys:
                self._trade_highlight_node_keys.clear()
                self._redraw_scene()
            return
        if self._trade_selected_commodities:
            self._run_trade_compare_multi(self._trade_selected_commodities)
            return
        commodity = _as_text(self.trade_compare_commodity_var.get())
        if not commodity:
            self._trade_highlight_node_keys.clear()
            self._trade_compare_rows = []
            self._trade_compare_rows_by_iid.clear()
            self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
            self._redraw_scene()
            return
        self._run_trade_compare(commodity)

    def _on_trade_highlight_clicked(self) -> None:
        if self._trade_selected_commodities:
            self._run_trade_compare_multi(self._trade_selected_commodities)
            return
        commodity = _as_text(self.trade_compare_commodity_var.get())
        if not commodity:
            self._sync_trade_highlight_button_state()
            return
        self._run_trade_compare(commodity)

    def _clear_trade_compare_state(self) -> None:
        self._trade_selected_commodities = []
        self.trade_compare_commodity_var.set("")
        self._trade_compare_rows = []
        self._trade_compare_rows_by_iid.clear()
        self._trade_highlight_node_keys.clear()
        self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
        self._sync_trade_selected_summary()
        self._sync_trade_highlight_button_state()
        self._redraw_scene()

    def _on_trade_compare_clear_clicked(self) -> None:
        self._clear_trade_compare_state()
        self.map_status_var.set("Mapa: Trade compare wyczyszczony.")

    def _set_trade_selected_commodities(self, values: list[str]) -> None:
        seen: set[str] = set()
        out: list[str] = []
        for item in values or []:
            text = _as_text(item)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        self._trade_selected_commodities = out
        # Keep legacy single value in sync for fallback/tests.
        if out:
            self.trade_compare_commodity_var.set(out[0])
        self._sync_trade_selected_summary()
        self._sync_trade_highlight_button_state()

    def _refresh_trade_picker_rows_if_open(self) -> None:
        win = getattr(self, "_trade_picker_window", None)
        tree = getattr(self, "_trade_picker_tree", None)
        if win is None or tree is None:
            return
        try:
            if not bool(win.winfo_exists()):
                return
        except Exception:
            return
        self._trade_picker_refresh_station_filter_status()
        self._trade_picker_refresh_rows()

    def _open_trade_commodity_picker(self) -> None:
        parent = self.winfo_toplevel()
        win = getattr(self, "_trade_picker_window", None)
        try:
            if win is not None and bool(win.winfo_exists()):
                bring_window_to_front(
                    win,
                    source="journal_map.trade_picker.reopen",
                    user_initiated=True,
                    deiconify=True,
                    request_focus=True,
                    force_focus=False,
                )
                self._trade_picker_refresh_rows()
                return
        except Exception as exc:
            _log_map_soft_failure(
                "trade_picker_reopen",
                "reopen existing trade picker failed",
                error=f"{type(exc).__name__}: {exc}",
            )

        win = tk.Toplevel(parent)
        self._trade_picker_window = win
        win.title("Wybierz towary - Trade Compare")
        win.configure(bg=COLOR_BG)
        win.transient(parent)
        try:
            win.grab_set()
        except Exception as exc:
            _log_map_soft_failure(
                "trade_picker_grab_set",
                "trade picker grab_set failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        win.geometry("620x540")
        win.minsize(520, 420)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(2, weight=1)

        search_var = tk.StringVar(value="")
        self._trade_picker_search_var = search_var
        top = tk.Frame(win, bg=COLOR_BG)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        top.columnconfigure(1, weight=1)
        tk.Label(top, text="Szukaj:", bg=COLOR_BG, fg=COLOR_FG).grid(row=0, column=0, sticky="w")
        search_entry = tk.Entry(top, textvariable=search_var, bg=COLOR_ACCENT, fg=COLOR_FG, insertbackground=COLOR_FG)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        search_entry.bind("<KeyRelease>", lambda _e: self._trade_picker_refresh_rows())

        controls = tk.Frame(win, bg=COLOR_BG)
        controls.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        controls.columnconfigure(3, weight=1)
        tk.Button(
            controls,
            text="Zaznacz wszystkie",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._trade_picker_select_all,
        ).grid(row=0, column=0, sticky="w")
        tk.Button(
            controls,
            text="Wyczysc",
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            relief="flat",
            command=self._trade_picker_clear_all,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        station_only_var = tk.BooleanVar(value=False)
        self._trade_picker_station_only_var = station_only_var
        station_only_chk = tk.Checkbutton(
            controls,
            text="Pokaż tylko dostępne na stacji",
            variable=station_only_var,
            bg=COLOR_BG,
            fg=COLOR_FG,
            selectcolor=COLOR_ACCENT,
            activebackground=COLOR_BG,
            activeforeground=COLOR_FG,
            command=self._trade_picker_on_station_only_toggled,
        )
        station_only_chk.grid(row=0, column=2, sticky="w", padx=(14, 0))
        self._trade_picker_station_only_chk = station_only_chk

        station_filter_status_var = tk.StringVar(value="")
        self._trade_picker_station_filter_status_var = station_filter_status_var
        tk.Label(
            controls,
            textvariable=station_filter_status_var,
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="e",
            justify="right",
        ).grid(row=0, column=3, sticky="e", padx=(10, 0))

        tree_wrap = tk.Frame(win, bg=COLOR_BG)
        tree_wrap.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            tree_wrap,
            columns=("sel", "commodity"),
            show="headings",
            style="Treeview",
            height=16,
        )
        tree.heading("sel", text="[ ]")
        tree.heading("commodity", text="Towar")
        tree.column("sel", width=50, anchor="center")
        tree.column("commodity", width=500, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.bind("<Button-1>", self._trade_picker_on_tree_click)
        tree.bind("<Double-Button-1>", lambda _e: self._trade_picker_toggle_selected_row())
        tree.bind("<Return>", lambda _e: self._trade_picker_toggle_selected_row())
        self._trade_picker_tree = tree
        self._trade_picker_tree_vsb = vsb
        self._trade_picker_tree_hsb = hsb

        hint = tk.Label(
            win,
            text="Towary pochodzą z Market.json (commodities), nie materiały inżynierskie.",
            bg=COLOR_BG,
            fg=COLOR_SEC,
            anchor="w",
            justify="left",
        )
        hint.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

        bottom = tk.Frame(win, bg=COLOR_BG)
        bottom.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom.columnconfigure(0, weight=1)
        tk.Button(bottom, text="Anuluj", bg=COLOR_ACCENT, fg=COLOR_FG, relief="flat", command=self._trade_picker_close).grid(
            row=0, column=1, sticky="e", padx=(0, 8)
        )
        tk.Button(bottom, text="Akceptuj", bg=COLOR_ACCENT, fg=COLOR_FG, relief="flat", command=self._trade_picker_accept).grid(
            row=0, column=2, sticky="e"
        )

        self._trade_picker_selected = {str(v) for v in (self._trade_selected_commodities or [])}
        win.protocol("WM_DELETE_WINDOW", self._trade_picker_close)
        self._trade_picker_refresh_station_filter_status()
        self._trade_picker_refresh_rows()
        try:
            search_entry.focus_set()
        except Exception as exc:
            _log_map_soft_failure(
                "trade_picker_focus_search",
                "trade picker search focus failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _trade_picker_filtered_commodities(self) -> list[str]:
        query = _as_text(getattr(self._trade_picker_search_var, "get", lambda: "")()).casefold()
        values = list(self._trade_picker_available or [])
        station_only = bool(getattr(self._trade_picker_station_only_var, "get", lambda: False)())
        if station_only:
            available_on_station, meta = self._trade_picker_current_station_available_commodities()
            if not bool(meta.get("ok")):
                return []
            values = [v for v in values if str(v).casefold() in available_on_station]
        if not query:
            return values
        return [v for v in values if query in str(v).casefold()]

    def _trade_picker_selected_station_row(self) -> dict[str, Any] | None:
        try:
            sel = self.system_stations_tree.selection() or ()
        except Exception:
            return None
        if not sel:
            try:
                children = self.system_stations_tree.get_children() or ()
            except Exception:
                children = ()
            if children:
                # Selection may be lost after focus changes; fall back to first visible station row.
                sel = (children[0],)
        if not sel:
            return None
        row = self._station_rows_by_iid.get(str(sel[0]))
        return dict(row) if isinstance(row, dict) else None

    def _trade_picker_current_station_available_commodities(self) -> tuple[set[str], dict[str, Any]]:
        row = self._trade_picker_selected_station_row()
        if not isinstance(row, dict):
            return set(), {"ok": False, "reason": "no_selected_station"}
        market_id = row.get("market_id")
        if market_id is None:
            return set(), {"ok": False, "reason": "station_no_market_id", "station_name": _as_text(row.get("station_name"))}
        try:
            snapshots, _meta = self.data_provider.get_market_last_seen(int(market_id), limit=1)
        except Exception as exc:
            return set(), {
                "ok": False,
                "reason": "provider_error",
                "station_name": _as_text(row.get("station_name")),
                "error": type(exc).__name__,
            }
        if not snapshots:
            return set(), {"ok": False, "reason": "no_market_snapshot", "station_name": _as_text(row.get("station_name"))}
        latest = dict(snapshots[0] or {})
        out: set[str] = set()
        for item in list(latest.get("items") or []):
            if not isinstance(item, dict):
                continue
            commodity = _as_text(item.get("commodity"))
            if commodity:
                out.add(commodity.casefold())
        return out, {
            "ok": True,
            "reason": "ok",
            "station_name": _as_text(row.get("station_name")) or "-",
            "market_id": int(market_id),
            "commodities_count": len(out),
        }

    def _trade_picker_refresh_station_filter_status(self) -> None:
        status_var = getattr(self, "_trade_picker_station_filter_status_var", None)
        chk = getattr(self, "_trade_picker_station_only_chk", None)
        chk_var = getattr(self, "_trade_picker_station_only_var", None)
        if status_var is None:
            return
        row = self._trade_picker_selected_station_row()
        if not isinstance(row, dict):
            try:
                status_var.set("Filtr stacji: brak wybranej stacji")
            except Exception as exc:
                _log_map_soft_failure(
                    "trade_picker_station_status_none",
                    "set trade picker station filter status (no station) failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            if chk_var is not None:
                try:
                    chk_var.set(False)
                except Exception as exc:
                    _log_map_soft_failure(
                        "trade_picker_station_only_var_none",
                        "reset station-only checkbox variable (no station) failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            if chk is not None:
                try:
                    chk.configure(state="disabled")
                except Exception as exc:
                    _log_map_soft_failure(
                        "trade_picker_station_only_chk_disable_none",
                        "disable station-only checkbox (no station) failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            return
        station_name = _as_text(row.get("station_name")) or "-"
        market_id = row.get("market_id")
        if market_id is None:
            try:
                status_var.set(f"Filtr stacji: {station_name} (brak MarketID)")
            except Exception as exc:
                _log_map_soft_failure(
                    "trade_picker_station_status_no_marketid",
                    "set trade picker station filter status (missing market id) failed",
                    station_name=station_name,
                    error=f"{type(exc).__name__}: {exc}",
                )
            if chk_var is not None:
                try:
                    chk_var.set(False)
                except Exception as exc:
                    _log_map_soft_failure(
                        "trade_picker_station_only_var_no_marketid",
                        "reset station-only checkbox variable (missing market id) failed",
                        station_name=station_name,
                        error=f"{type(exc).__name__}: {exc}",
                    )
            if chk is not None:
                try:
                    chk.configure(state="disabled")
                except Exception as exc:
                    _log_map_soft_failure(
                        "trade_picker_station_only_chk_disable_no_marketid",
                        "disable station-only checkbox (missing market id) failed",
                        station_name=station_name,
                        error=f"{type(exc).__name__}: {exc}",
                    )
            return
        if chk is not None:
            try:
                chk.configure(state="normal")
            except Exception as exc:
                _log_map_soft_failure(
                    "trade_picker_station_only_chk_enable",
                    "enable station-only checkbox failed",
                    station_name=station_name,
                    error=f"{type(exc).__name__}: {exc}",
                )
        try:
            status_var.set(f"Stacja: {station_name}")
        except Exception as exc:
            _log_map_soft_failure(
                "trade_picker_station_status_ok",
                "set trade picker station filter status failed",
                station_name=station_name,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _trade_picker_on_station_only_toggled(self) -> None:
        self._trade_picker_refresh_station_filter_status()
        self._trade_picker_refresh_rows()

    def _trade_picker_selection_contains(self, commodity: str) -> bool:
        target = _as_text(commodity).casefold()
        if not target:
            return False
        for item in (self._trade_picker_selected or set()):
            if _as_text(item).casefold() == target:
                return True
        return False

    def _trade_picker_selection_add(self, commodity: str) -> None:
        text = _as_text(commodity)
        if not text:
            return
        target = text.casefold()
        selected = {
            str(item)
            for item in (self._trade_picker_selected or set())
            if _as_text(item).casefold() != target
        }
        selected.add(text)
        self._trade_picker_selected = selected

    def _trade_picker_selection_remove(self, commodity: str) -> None:
        target = _as_text(commodity).casefold()
        if not target:
            return
        self._trade_picker_selected = {
            str(item)
            for item in (self._trade_picker_selected or set())
            if _as_text(item).casefold() != target
        }

    def _trade_picker_refresh_rows(self) -> None:
        tree = getattr(self, "_trade_picker_tree", None)
        if tree is None:
            return
        station_only = bool(getattr(self._trade_picker_station_only_var, "get", lambda: False)())
        total_values = list(self._trade_picker_available or [])
        filtered_values = list(self._trade_picker_filtered_commodities())
        try:
            tree.delete(*tree.get_children())
        except Exception:
            return
        for idx, commodity in enumerate(filtered_values):
            selected = self._trade_picker_selection_contains(str(commodity))
            tree.insert(
                "",
                "end",
                iid=f"c:{idx}",
                values=("[x]" if selected else "[ ]", commodity),
            )
        if station_only:
            status_var = getattr(self, "_trade_picker_station_filter_status_var", None)
            if status_var is not None:
                base_status = _as_text(getattr(status_var, "get", lambda: "")())
                if base_status and "towary:" not in base_status.casefold():
                    try:
                        status_var.set(f"{base_status} | towary: {len(filtered_values)}/{len(total_values)}")
                    except Exception as exc:
                        _log_map_soft_failure(
                            "trade_picker_station_status_counts",
                            "set trade picker station filter counts failed",
                            error=f"{type(exc).__name__}: {exc}",
                        )

    def _trade_picker_toggle_selected_row(self) -> None:
        tree = getattr(self, "_trade_picker_tree", None)
        if tree is None:
            return
        sel = tree.selection() or ()
        if not sel:
            return
        self._trade_picker_toggle_row_iid(str(sel[0]))

    def _trade_picker_toggle_row_iid(self, iid: str) -> None:
        tree = getattr(self, "_trade_picker_tree", None)
        if tree is None:
            return
        iid = str(iid)
        values = tree.item(iid, "values") or ()
        commodity = _as_text(values[1] if len(values) > 1 else "")
        if not commodity:
            return
        if self._trade_picker_selection_contains(commodity):
            self._trade_picker_selection_remove(commodity)
        else:
            self._trade_picker_selection_add(commodity)
        self._trade_picker_refresh_rows()
        try:
            tree.selection_set(iid)
            tree.focus(iid)
        except Exception as exc:
            _log_map_soft_failure(
                    "trade_picker_toggle_reselect",
                    "reselect trade picker row after toggle failed",
                    iid=str(iid),
                    error=f"{type(exc).__name__}: {exc}",
                )

    def _trade_picker_on_tree_click(self, event=None):
        tree = getattr(self, "_trade_picker_tree", None)
        if tree is None or event is None:
            return None
        try:
            region = str(tree.identify("region", int(event.x), int(event.y)) or "")
            column = str(tree.identify_column(int(event.x)) or "")
            row_iid = str(tree.identify_row(int(event.y)) or "")
        except Exception as exc:
            _log_map_soft_failure(
                "trade_picker_tree_click_identify",
                "identify trade picker tree click target failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        # Single-click toggles only when user clicks the pseudo-checkbox column.
        if region in {"cell", "tree"} and column == "#1" and row_iid:
            try:
                tree.selection_set(row_iid)
                tree.focus(row_iid)
            except Exception as exc:
                _log_map_soft_failure(
                    "trade_picker_tree_click_reselect",
                    "select trade picker row on single-click toggle failed",
                    iid=row_iid,
                    error=f"{type(exc).__name__}: {exc}",
                )
            self._trade_picker_toggle_row_iid(row_iid)
            return "break"
        return None

    def _trade_picker_select_all(self) -> None:
        self._trade_picker_selected = set(self._trade_picker_filtered_commodities())
        self._trade_picker_refresh_rows()

    def _trade_picker_clear_all(self) -> None:
        self._trade_picker_selected = set()
        self._trade_picker_refresh_rows()

    def _trade_picker_close(self) -> None:
        win = getattr(self, "_trade_picker_window", None)
        self._trade_picker_window = None
        self._trade_picker_tree = None
        self._trade_picker_tree_vsb = None
        self._trade_picker_tree_hsb = None
        self._trade_picker_search_var = None
        self._trade_picker_station_only_var = None
        self._trade_picker_station_only_chk = None
        self._trade_picker_station_filter_status_var = None
        try:
            if win is not None and bool(win.winfo_exists()):
                try:
                    win.grab_release()
                except Exception as exc:
                    _log_map_soft_failure(
                        "trade_picker_close_grab_release",
                        "trade picker grab_release on close failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                win.destroy()
        except Exception as exc:
            _log_map_soft_failure(
                "trade_picker_close_destroy",
                "trade picker close/destroy failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _trade_picker_accept(self) -> None:
        selected_sorted: list[str] = []
        seen_cf: set[str] = set()
        for item in sorted(set(self._trade_picker_selected or set()), key=lambda v: str(v).casefold()):
            text = _as_text(item)
            key = text.casefold()
            if not text or key in seen_cf:
                continue
            seen_cf.add(key)
            selected_sorted.append(text)
        self._set_trade_selected_commodities(selected_sorted)
        self._trade_picker_close()
        if selected_sorted:
            self._run_trade_compare_multi(selected_sorted)
        else:
            self._clear_trade_compare_state()
            self.map_status_var.set("Mapa: wyczyszczono wybor towarow Trade compare.")

    def _node_keys_for_system_name(self, system_name: Any) -> list[str]:
        target = _as_text(system_name).casefold()
        if not target:
            return []
        return [key for key, node in (self._nodes or {}).items() if _as_text(node.system_name).casefold() == target]

    def focus_system_by_name_external(self, system_name: Any, *, center: bool = True) -> dict[str, Any]:
        target_name = _as_text(system_name)
        if not target_name:
            self.map_status_var.set("Mapa: brak nazwy systemu do pokazania.")
            return {"ok": False, "reason": "system_name_missing"}

        keys = self._node_keys_for_system_name(target_name)
        if not keys:
            try:
                self.reload_from_playerdb()
            except Exception as exc:
                _log_map_soft_failure(
                    "focus_system_external_reload",
                    "reload map before external focus failed",
                    system_name=target_name,
                    error=f"{type(exc).__name__}: {exc}",
                )
            keys = self._node_keys_for_system_name(target_name)
        if not keys:
            self.map_status_var.set(f"Mapa: system {target_name} nie jest widoczny (filtry/warstwy/playerdb).")
            return {"ok": False, "reason": "system_not_found", "system_name": target_name}

        node_key = str(keys[0])
        result = self.select_system_node(node_key)
        if not bool((result or {}).get("ok")):
            return dict(result or {"ok": False, "reason": "select_failed", "system_name": target_name})
        node = self._nodes.get(node_key)
        if center and node is not None:
            self._center_world_point(node.x, node.y)
            self._redraw_scene()
            try:
                self.map_status_var.set(f"Mapa: wybrano i wycentrowano system {node.system_name}.")
            except Exception as exc:
                _log_map_soft_failure(
                    "focus_system_external_status",
                    "set map status after external focus failed",
                    system_name=target_name,
                    error=f"{type(exc).__name__}: {exc}",
                )
        return {"ok": True, "system_name": target_name, "node_key": node_key, "centered": bool(center)}

    def _highlight_trade_compare_for_commodity(self, commodity: str) -> None:
        commodity_cf = _as_text(commodity).casefold()
        self._trade_highlight_node_keys.clear()
        if not commodity_cf:
            self._redraw_scene()
            return
        for row in self._trade_compare_rows or []:
            if not isinstance(row, dict):
                continue
            if _as_text(row.get("commodity")).casefold() != commodity_cf:
                continue
            for key in self._node_keys_for_system_name(row.get("system_name")):
                self._trade_highlight_node_keys.add(key)
        self._redraw_scene()

    def _on_trade_compare_row_selected(self, _event=None) -> None:
        selection = self.trade_compare_tree.selection() or ()
        if not selection:
            return
        row = self._trade_compare_rows_by_iid.get(str(selection[0])) or {}
        commodity = _as_text(row.get("commodity"))
        if commodity:
            self._highlight_trade_compare_for_commodity(commodity)
            self.map_status_var.set(f"Mapa: Trade compare aktywny towar '{commodity}'.")

    def _on_trade_compare_tree_configure(self, _event=None) -> None:
        tree = getattr(self, "trade_compare_tree", None)
        if not isinstance(tree, ttk.Treeview):
            return
        try:
            tree_width = int(tree.winfo_width() or 0)
        except Exception:
            return
        if tree_width <= 0:
            return
        if tree_width == int(getattr(self, "_trade_compare_tree_last_reflow_width", 0) or 0):
            return
        self._trade_compare_tree_last_reflow_width = tree_width
        self._reflow_trade_compare_tree_columns()

    def _trade_compare_scope_from_selection(self) -> dict[str, Any]:
        station_row = self._trade_picker_selected_station_row()
        selected_node = self._nodes.get(_as_text(getattr(self, "_selected_node_key", "")))
        system_name = _as_text((station_row or {}).get("system_name"))
        if not system_name and selected_node is not None:
            system_name = _as_text(getattr(selected_node, "system_name", ""))

        station_name = _as_text((station_row or {}).get("station_name"))
        market_id = None
        try:
            raw_market_id = (station_row or {}).get("market_id")
            if raw_market_id is not None:
                market_id = int(raw_market_id)
        except Exception:
            market_id = None

        if not system_name:
            return {
                "ok": False,
                "reason": "no_selected_system",
                "system_name": "",
                "station_name": "",
                "market_id": None,
            }

        return {
            "ok": True,
            "reason": "selected_station" if station_row else "selected_system_only",
            "system_name": system_name,
            "station_name": station_name,
            "market_id": market_id,
        }

    def _reflow_trade_compare_tree_columns(self) -> None:
        tree = getattr(self, "trade_compare_tree", None)
        if not isinstance(tree, ttk.Treeview):
            return
        try:
            columns = list(tree["columns"] or ())
        except Exception:
            return
        if not columns:
            return
        try:
            tree_width = int(tree.winfo_width() or 0)
        except Exception:
            return
        if tree_width <= 0:
            return
        # Deterministic reflow for widget width changes only. This avoids fighting
        # manual column resizing and keeps numeric columns visible.
        fixed_widths = {"mode": 58, "price": 86, "age": 96}
        min_commodity = 180
        padding = 18
        try:
            available = max(220, tree_width - padding)
            fixed_total = sum(fixed_widths.get(col, 0) for col in columns)
            commodity_width = max(min_commodity, available - fixed_total)
            for col in columns:
                if col in fixed_widths:
                    tree.column(col, width=fixed_widths[col], stretch=False)
                elif col == "commodity":
                    tree.column(col, width=commodity_width, stretch=True)
        except Exception:
            return

    def _run_trade_compare(self, commodity: str) -> dict[str, Any]:
        commodity_name = _as_text(commodity)
        self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
        self._trade_highlight_node_keys.clear()
        self._trade_compare_rows = []
        self._trade_compare_rows_by_iid.clear()
        self._sync_trade_highlight_button_state()
        if not commodity_name:
            self.trade_compare_tree.insert("", "end", values=("INFO", "wybierz towar", "-", "-"))
            self._redraw_scene()
            return {"ok": False, "reason": "missing_commodity"}

        scope = self._trade_compare_scope_from_selection()
        if not bool(scope.get("ok")):
            self.trade_compare_tree.insert(
                "",
                "end",
                values=("INFO", "wybierz system/stacje", "-", "-"),
            )
            self._redraw_scene()
            self.map_status_var.set("Mapa: Trade compare wymaga wybranego systemu/stacji z panelu System details.")
            return {"ok": False, "reason": "missing_scope"}

        scope_system = _as_text(scope.get("system_name"))
        scope_station = _as_text(scope.get("station_name"))
        scope_market_id = scope.get("market_id")

        time_range = self._effective_time_range_filter()
        freshness_filter = self._effective_freshness_filter()
        try:
            sell_rows, sell_meta = self.data_provider.get_top_prices(
                commodity_name,
                "sell",
                time_range=time_range,
                freshness_filter=freshness_filter,
                system_name=scope_system,
                station_market_id=scope_market_id,
                station_name=scope_station,
                limit=5,
            )
            buy_rows, buy_meta = self.data_provider.get_top_prices(
                commodity_name,
                "buy",
                time_range=time_range,
                freshness_filter=freshness_filter,
                system_name=scope_system,
                station_market_id=scope_market_id,
                station_name=scope_station,
                limit=5,
            )
        except Exception as exc:
            self.trade_compare_tree.insert("", "end", values=("ERR", type(exc).__name__, "-", "-"))
            self._redraw_scene()
            return {"ok": False, "reason": "provider_error"}

        rows_inserted = 0
        for mode_label, rows in (("SELL", sell_rows), ("BUY", buy_rows)):
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                if not self._passes_freshness_filter(row.get("freshness_ts")):
                    continue
                self._trade_compare_rows.append(dict(row))
                system_name = _as_text(row.get("system_name")) or "-"
                station_name = _as_text(row.get("station_name")) or "-"
                price = int(row.get("price") or 0)
                age = _format_age_short(row.get("freshness_ts"))
                conf = _as_text(row.get("confidence")) or "observed"
                iid = f"tc:{rows_inserted}"
                self._trade_compare_rows_by_iid[iid] = dict(row)
                self.trade_compare_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(mode_label, commodity_name, f"{price}", f"{age} | {conf}"),
                )
                for key in self._node_keys_for_system_name(system_name):
                    self._trade_highlight_node_keys.add(key)
                rows_inserted += 1

        if rows_inserted <= 0:
            self.trade_compare_tree.insert(
                "",
                "end",
                values=("INFO", commodity_name, "-", "brak danych po filtrach"),
            )
        else:
            # Default active commodity highlight (single commodity mode = all rows same commodity).
            self._highlight_trade_compare_for_commodity(commodity_name)
            rows = self.trade_compare_tree.get_children()
            if rows:
                try:
                    self.trade_compare_tree.selection_set(rows[0])
                    self.trade_compare_tree.focus(rows[0])
                except Exception as exc:
                    _log_map_soft_failure(
                        "trade_compare_single_autoselect",
                        "auto-select first trade compare row (single) failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
        self._reflow_trade_compare_tree_columns()
        if rows_inserted <= 0:
            self._redraw_scene()

        trade_layer_on = bool(self.layer_trade_var.get())
        suffix = "" if trade_layer_on else " (warstwa Trade wylaczona - highlight ukryty)"
        self.map_status_var.set(
            f"Mapa: Trade compare '{commodity_name}' [{scope_system}{' / ' + scope_station if scope_station else ''}] | "
            f"sell={len(sell_rows)} buy={len(buy_rows)} | "
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

    def _run_trade_compare_multi(self, commodities: list[str]) -> dict[str, Any]:
        selected = []
        seen: set[str] = set()
        for item in commodities or []:
            text = _as_text(item)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            selected.append(text)
        self._set_trade_selected_commodities(selected)

        self.trade_compare_tree.delete(*self.trade_compare_tree.get_children())
        self._trade_compare_rows = []
        self._trade_compare_rows_by_iid.clear()
        self._trade_highlight_node_keys.clear()
        self._sync_trade_highlight_button_state()
        if not selected:
            self.trade_compare_tree.insert("", "end", values=("INFO", "wybierz towary", "-", "-"))
            self._redraw_scene()
            return {"ok": False, "reason": "missing_commodities"}

        scope = self._trade_compare_scope_from_selection()
        if not bool(scope.get("ok")):
            self.trade_compare_tree.insert(
                "",
                "end",
                values=("INFO", "wybierz system/stacje", "-", "-"),
            )
            self._redraw_scene()
            self.map_status_var.set("Mapa: Trade compare wymaga wybranego systemu/stacji z panelu System details.")
            return {"ok": False, "reason": "missing_scope", "commodities": selected}

        scope_system = _as_text(scope.get("system_name"))
        scope_station = _as_text(scope.get("station_name"))
        scope_market_id = scope.get("market_id")

        rows_inserted = 0
        total_sell = 0
        total_buy = 0
        provider_errors = 0
        for commodity_name in selected:
            try:
                sell_rows, _sell_meta = self.data_provider.get_top_prices(
                    commodity_name,
                    "sell",
                    time_range=self._effective_time_range_filter(),
                    freshness_filter=self._effective_freshness_filter(),
                    system_name=scope_system,
                    station_market_id=scope_market_id,
                    station_name=scope_station,
                    limit=5,
                )
                buy_rows, _buy_meta = self.data_provider.get_top_prices(
                    commodity_name,
                    "buy",
                    time_range=self._effective_time_range_filter(),
                    freshness_filter=self._effective_freshness_filter(),
                    system_name=scope_system,
                    station_market_id=scope_market_id,
                    station_name=scope_station,
                    limit=5,
                )
            except Exception:
                provider_errors += 1
                continue

            total_sell += len(sell_rows or [])
            total_buy += len(buy_rows or [])
            for mode_label, rows in (("SELL", sell_rows), ("BUY", buy_rows)):
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    if not self._passes_freshness_filter(row.get("freshness_ts")):
                        continue
                    rec = dict(row)
                    self._trade_compare_rows.append(rec)
                    system_name = _as_text(rec.get("system_name")) or "-"
                    station_name = _as_text(rec.get("station_name")) or "-"
                    price = int(rec.get("price") or 0)
                    age = _format_age_short(rec.get("freshness_ts"))
                    conf = _as_text(rec.get("confidence")) or "observed"
                    iid = f"tcm:{rows_inserted}"
                    self._trade_compare_rows_by_iid[iid] = rec
                    self.trade_compare_tree.insert(
                        "",
                        "end",
                        iid=iid,
                        values=(mode_label, commodity_name, f"{price}", f"{age} | {conf}"),
                    )
                    rows_inserted += 1

        if rows_inserted <= 0:
            self.trade_compare_tree.insert("", "end", values=("INFO", "brak danych", "-", "po filtrach"))
            self._redraw_scene()
            self.map_status_var.set("Mapa: Trade compare (multi) - brak danych dla wybranych towarow.")
            self._reflow_trade_compare_tree_columns()
            return {"ok": False, "reason": "no_rows", "commodities": selected, "provider_errors": provider_errors}

        # Auto-select first row and highlight by active commodity.
        rows = self.trade_compare_tree.get_children()
        if rows:
            try:
                self.trade_compare_tree.selection_set(rows[0])
                self.trade_compare_tree.focus(rows[0])
            except Exception as exc:
                _log_map_soft_failure(
                    "trade_compare_multi_autoselect",
                    "auto-select first trade compare row (multi) failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            row = self._trade_compare_rows_by_iid.get(str(rows[0])) or {}
            active_commodity = _as_text(row.get("commodity")) or selected[0]
            self._highlight_trade_compare_for_commodity(active_commodity)
        self._reflow_trade_compare_tree_columns()

        trade_layer_on = bool(self.layer_trade_var.get())
        suffix = "" if trade_layer_on else " (warstwa Trade wylaczona - highlight ukryty)"
        self.map_status_var.set(
            f"Mapa: Trade compare multi ({len(selected)} towarow) [{scope_system}{' / ' + scope_station if scope_station else ''}] | "
            f"sell={total_sell} buy={total_buy} | rows={rows_inserted}{suffix}"
        )
        return {
            "ok": True,
            "commodities": list(selected),
            "rows_inserted": rows_inserted,
            "sell_count": total_sell,
            "buy_count": total_buy,
            "provider_errors": provider_errors,
        }

    def _canvas_current_node_key(self) -> str | None:
        return self._node_key_from_canvas_current_item()

    def _node_key_from_canvas_current_item(self) -> str | None:
        try:
            current = self.map_canvas.find_withtag("current")
            if not current:
                return None
            tags = self.map_canvas.gettags(current[0]) or ()
        except Exception:
            return None
        return self._node_key_from_tags(tags)

    def _node_key_from_tags(self, tags: tuple[Any, ...] | list[Any]) -> str | None:
        for tag in tags:
            text = str(tag)
            if text.startswith("node:"):
                key = text.split(":", 1)[1].strip()
                if key:
                    return key
        return None

    def _node_key_near_canvas_point(self, sx: int, sy: int, *, near_px: int = 6) -> str | None:
        try:
            radius = max(0, int(near_px))
            ids = self.map_canvas.find_overlapping(sx - radius, sy - radius, sx + radius, sy + radius)
        except Exception:
            return None
        if not ids:
            return None
        for item_id in reversed(ids):
            try:
                tags = self.map_canvas.gettags(item_id) or ()
            except Exception:
                continue
            key = self._node_key_from_tags(tags)
            if key:
                return key
        return None

    def _on_canvas_node_click(self, event=None):
        key = self._canvas_current_node_key()
        if not key and event is not None:
            key = self._node_key_near_canvas_point(int(getattr(event, "x", 0)), int(getattr(event, "y", 0)), near_px=8)
        if not key:
            return None
        self._pan_active = False
        self._hide_map_tooltip()
        self._set_map_cursor("arrow")
        self.select_system_node(key)
        return "break"

    def _on_canvas_node_double_click(self, event=None):
        key = self._canvas_current_node_key()
        if not key and event is not None:
            key = self._node_key_near_canvas_point(int(getattr(event, "x", 0)), int(getattr(event, "y", 0)), near_px=8)
        if not key:
            return None
        self._pan_active = False
        self._hide_map_tooltip()
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

        prefetched = self._prefetched_stations_for_node(node)
        if prefetched is not None:
            stations_rows, stations_meta = prefetched
        else:
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

        compare_refreshed = False
        # Auto-select first station for quick drilldown UX.
        children = self.system_stations_tree.get_children()
        if children:
            first_iid = str(children[0])
            try:
                self.system_stations_tree.selection_set(first_iid)
                self.system_stations_tree.focus(first_iid)
            except Exception as exc:
                _log_map_soft_failure(
                    "system_stations_autoselect_first",
                    "auto-select first station row failed",
                    iid=first_iid,
                    error=f"{type(exc).__name__}: {exc}",
                )
            selected_station_result = self._select_station_by_iid(first_iid)
            compare_refreshed = bool(isinstance(selected_station_result, dict) and selected_station_result.get("ok"))
        else:
            self.station_market_tree.delete(*self.station_market_tree.get_children())
            if bool(self.layer_stations_var.get()):
                self.station_details_var.set("Brak znanych stacji w playerdb dla wybranego systemu (po filtrach).")

        # Keep trade compare in sync even when there is no station in selected system.
        if not compare_refreshed:
            self._refresh_trade_compare_if_needed()

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
            f"Gwiazda: {self._star_label_for_node(node)}",
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
            + (
                f"\nSnapshoty rynku: {shown_rows}/{len(snapshots)} (freshness="
                f"{'session' if bool(self.last_session_only_var.get()) else _as_text(self.freshness_var.get())})"
            )
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
        self._refresh_trade_picker_rows_if_open()
        self._refresh_trade_compare_if_needed()
        return {"ok": True, "iid": str(iid), "station_name": _as_text(row.get("station_name")), **result}

    def reset_view(self) -> None:
        self.view_scale = 1.0
        self._center_world_point(0.0, 0.0)
        self._redraw_scene()
        self.map_status_var.set("Mapa: zresetowano zoom i pozycje.")

    def center_on_current_system(self) -> None:
        current_name = str(getattr(app_state, "current_system", "") or "").strip()
        current_node = self._find_current_system_rendered_node()
        if current_node is not None:
            self._center_world_point(float(current_node.x), float(current_node.y))
            self._redraw_scene()
            self.map_status_var.set(f"Mapa: wycentrowano na aktualnym systemie ({current_node.system_name}).")
            return

        if current_name:
            self._redraw_scene()
            self.map_status_var.set(
                f"Mapa: aktualny system ({current_name}) nie jest widoczny na mapie (po filtrach/warstwach)."
            )
            return

        current_star_pos = getattr(app_state, "current_star_pos", None)
        if isinstance(current_star_pos, (list, tuple)) and len(current_star_pos) >= 3:
            try:
                wx = float(current_star_pos[0])
                wy = float(current_star_pos[2])  # x/z -> 2D (shell fallback)
                self._center_world_point(wx, wy)
                self._redraw_scene()
                self.map_status_var.set("Mapa: wycentrowano na fallback current StarPos (shell).")
                return
            except Exception as exc:
                _log_map_soft_failure(
                    "center_on_current_starpos_fallback",
                    "center on fallback current StarPos failed",
                    current_star_pos=str(current_star_pos),
                    error=f"{type(exc).__name__}: {exc}",
                )

        self._redraw_scene()
        self.map_status_var.set("Mapa: brak danych do wycentrowania aktualnego systemu.")

    def _on_canvas_configure(self, _event=None) -> None:
        # If offsets are zero (first layout), center origin.
        if abs(self.view_offset_x) < 1e-6 and abs(self.view_offset_y) < 1e-6:
            self._center_world_point(0.0, 0.0)
        self._hide_map_tooltip()
        self._redraw_scene()
        # Startup auto-center can be delayed until canvas has a real size.
        if (
            bool(getattr(self, "_startup_autocenter_pending", False))
            and not bool(getattr(self, "_startup_autocenter_done", False))
            and not bool(getattr(self, "_startup_autocenter_user_blocked", False))
            and bool(self._nodes)
        ):
            self._try_startup_autocenter()
        if (
            bool(getattr(self, "_startup_autocenter_recenter_pending", False))
            and bool(getattr(self, "_startup_autocenter_done", False))
            and not bool(getattr(self, "_startup_autocenter_user_blocked", False))
            and bool(self._nodes)
        ):
            canvas_w = max(0, int(self.map_canvas.winfo_width() or 0))
            canvas_h = max(0, int(self.map_canvas.winfo_height() or 0))
            if canvas_w >= 32 and canvas_h >= 32:
                current_node = self._find_current_system_rendered_node()
                if current_node is not None:
                    self._center_world_point(float(current_node.x), float(current_node.y))
                    self._redraw_scene()
                self._startup_autocenter_recenter_pending = False

    def _on_canvas_press(self, event) -> None:
        self._pan_active = True
        self._hide_map_tooltip()
        self._pan_last_x = int(getattr(event, "x", 0))
        self._pan_last_y = int(getattr(event, "y", 0))
        self._set_map_cursor("arrow")

    def _on_canvas_drag(self, event) -> None:
        if not self._pan_active:
            return
        self._hide_map_tooltip()
        x = int(getattr(event, "x", 0))
        y = int(getattr(event, "y", 0))
        dx = x - self._pan_last_x
        dy = y - self._pan_last_y
        if dx or dy:
            self._block_startup_autocenter_by_user()
        self._pan_last_x = x
        self._pan_last_y = y
        self._set_map_cursor("fleur")
        self.view_offset_x += dx
        self.view_offset_y += dy
        self._redraw_scene()

    def _on_canvas_release(self, _event=None) -> None:
        self._pan_active = False
        self._hide_map_tooltip()
        self._set_map_cursor("arrow")

    def _on_canvas_leave(self, _event=None) -> None:
        self._hide_map_tooltip()
        return None

    def _on_canvas_mousewheel(self, event) -> None:
        self._hide_map_tooltip()
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

        self._block_startup_autocenter_by_user()
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
        self._hide_map_tooltip()
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
        show_labels = self.view_scale >= 0.90
        for node in self._nodes.values():
            sx, sy = self.world_to_screen(node.x, node.y)
            r = 5 if self.view_scale < 1.2 else 6
            star_color = self._star_color_for_node(node)
            # Keep click hitbox tight: only the star glyph should carry map_node events.
            node_hit_tags = ("map_node", f"node:{node.key}")
            node_label_tags = ("map_node_label", f"node:{node.key}")
            base_fill = star_color
            base_outline = star_color
            if int(getattr(node, "is_black_hole", 0) or 0):
                base_fill = COLOR_BG
                base_outline = star_color
            elif int(getattr(node, "is_neutron", 0) or 0):
                base_fill = COLOR_BG
                base_outline = star_color
            self.map_canvas.create_oval(
                sx - r,
                sy - r,
                sx + r,
                sy + r,
                outline=base_outline,
                fill=base_fill,
                tags=node_hit_tags,
            )
            # Distinguish special stars while preserving click hitbox on base glyph.
            if int(getattr(node, "is_black_hole", 0) or 0):
                inner = max(1, r - 2)
                self.map_canvas.create_oval(
                    sx - inner,
                    sy - inner,
                    sx + inner,
                    sy + inner,
                    outline=star_color,
                    width=1.2,
                    tags=("map_star_marker", f"node:{node.key}"),
                )
            elif int(getattr(node, "is_neutron", 0) or 0):
                burst = r + 2
                self.map_canvas.create_line(
                    sx - burst,
                    sy,
                    sx + burst,
                    sy,
                    fill=star_color,
                    width=1.0,
                    tags=("map_star_marker", f"node:{node.key}"),
                )
                self.map_canvas.create_line(
                    sx,
                    sy - burst,
                    sx,
                    sy + burst,
                    fill=star_color,
                    width=1.0,
                    tags=("map_star_marker", f"node:{node.key}"),
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
                    tags=node_label_tags,
                )

    def _is_current_system_node(self, node: _MapNode) -> bool:
        current_name = _as_text(getattr(app_state, "current_system", ""))
        if not current_name:
            return False
        return current_name.casefold() == _as_text(node.system_name).casefold()

    def _find_current_system_rendered_node(self) -> _MapNode | None:
        current_name = _as_text(getattr(app_state, "current_system", ""))
        if not current_name:
            return None
        for node in (self._nodes or {}).values():
            try:
                if current_name.casefold() == _as_text(getattr(node, "system_name", "")).casefold():
                    return node
            except Exception:
                continue
        return None

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
        show_service_badges = bool(self.view_scale >= 0.45)
        show_action_badges = bool(self.view_scale >= 0.75)
        # Stations layer: outer ring (known stations in system).
        if show_service_badges and bool(self.layer_stations_var.get()) and bool(flags.get("has_station")):
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
        if show_service_badges and bool(self.layer_trade_var.get()) and bool(flags.get("has_market")):
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
        if show_service_badges and bool(self.layer_cashin_var.get()) and bool(flags.get("has_cashin")):
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

        if not show_action_badges:
            return

        def _dot(cx: float, cy: float, color: str, tag_name: str) -> None:
            rr = 2.8
            c.create_oval(
                cx - rr,
                cy - rr,
                cx + rr,
                cy + rr,
                outline=color,
                fill=color,
                tags=(tag_name, "layer_action_badge", f"node:{node.key}"),
            )

        # Action badges (history/activity): badge/dot markers, not extra rings.
        if bool(self.layer_exploration_var.get()) and bool(flags.get("has_exploration")):
            _dot(sx - r - 6, sy - r - 6, COLOR_EXPLORATION_LAYER, "layer_exploration")
        if bool(self.layer_exobio_var.get()) and bool(flags.get("has_exobio")):
            _dot(sx - r - 6, sy + r + 6, COLOR_EXOBIO_LAYER, "layer_exobio")
        if bool(self.layer_incidents_var.get()) and bool(flags.get("has_incident")):
            _dot(sx - r - 8, sy, COLOR_INCIDENT_LAYER, "layer_incidents")
        if bool(self.layer_combat_var.get()) and bool(flags.get("has_combat")):
            _dot(sx, sy - r - 9, COLOR_COMBAT_LAYER, "layer_combat")

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

