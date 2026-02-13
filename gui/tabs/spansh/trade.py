import tkinter as tk

from tkinter import ttk

import time
import math
import re

from datetime import datetime, timedelta

import config

from logic import trade

from logic import utils
from logic.utils.http_edsm import edsm_stations_for_system, is_edsm_enabled

from logic.spansh_client import client as spansh_client

from gui import common
from gui import empty_state

from gui import strings as ui

from gui import ui_layout as layout
from gui.ui_thread import run_on_ui_thread

from gui.common_autocomplete import AutocompleteController

from app.route_manager import route_manager

from app.state import app_state





class TradeTab(ttk.Frame):

    """

    ZakĹ‚adka: Trade Planner (Spansh)

    """

    _UPDATED_AGE_RE = re.compile(
        r"(?P<num>\d+)\s*(?P<unit>"
        r"second|seconds|sec|secs|s|"
        r"minute|minutes|min|mins|m|"
        r"hour|hours|hr|hrs|h|"
        r"day|days|d|"
        r"week|weeks|w|"
        r"month|months|"
        r"year|years|y|"
        r"sekunda|sekundy|sekund|sek|"
        r"minuta|minuty|minut|"
        r"godzina|godziny|godzin|godz|"
        r"dzien|dni|"
        r"tydzien|tygodnie|tygodni|"
        r"miesiac|miesiace|miesiecy|"
        r"rok|lata|lat"
        r")\b",
        flags=re.IGNORECASE,
    )



    def __init__(self, parent, root_window):

        super().__init__(parent)

        self.root = root_window

        self.pack(fill="both", expand=1)



        # Referencja do globalnego AppState (nie tworzymy nowej instancji)

        self.app_state = app_state



        # System / stacja startowa â€“ inicjalnie puste,

        # uzupeĹ‚niane z app_state w refresh_from_app_state().

        self.var_start_system = tk.StringVar()

        self.var_start_station = tk.StringVar()
        self._station_hint_var = tk.StringVar()
        self._station_loading = False
        self._station_last_trigger_ts = 0.0

        self._station_cache = {}

        self._recent_stations = []

        self._recent_limit = 25

        self._station_autocomplete_by_system = bool(

            config.get("features.trade.station_autocomplete_by_system", True)

        )

        self._station_lookup_online = bool(

            config.get("features.trade.station_lookup_online", False)

        )
        self._station_picker_window = None



        # Parametry liczbowo-konfiguracyjne

        self.var_capital = tk.IntVar(value=10_000_000)

        self.var_max_hop = tk.DoubleVar(value=20.0)

        self.var_cargo = tk.IntVar(value=256)

        self.var_max_hops = tk.IntVar(value=10)

        self.var_max_dta = tk.IntVar(value=5000)

        self.var_max_age = tk.DoubleVar(value=2.0)

        self.var_market_age_cutoff = tk.StringVar()

        self.var_market_age_hours = tk.DoubleVar(value=48.0)
        self.var_market_age_relative = tk.StringVar(value="")
        self._market_age_forever = False



        # Flagowe checkboxy

        self.var_large_pad = tk.BooleanVar(value=True)

        self.var_planetary = tk.BooleanVar(value=True)

        self.var_player_owned = tk.BooleanVar(value=False)

        self.var_restricted = tk.BooleanVar(value=False)

        self.var_prohibited = tk.BooleanVar(value=False)

        self.var_avoid_loops = tk.BooleanVar(value=True)

        self.var_allow_permits = tk.BooleanVar(value=True)



        self._results_rows: list[dict] = []
        self._trade_table_layout_ready: bool = False
        self._trade_table_layout_retry_count: int = 0

        self._results_row_offset = 0
        self._results_widget = None
        self._last_effective_jump_range: float | None = None
        self.var_trade_summary = tk.StringVar(value="")
        self.var_trade_leg_route = tk.StringVar(value="")
        self.var_trade_leg_meta = tk.StringVar(value="")

        self._busy = False



        self._use_treeview = bool(config.get("features.tables.treeview_enabled", False)) and bool(

            config.get("features.tables.spansh_schema_enabled", True)

        ) and bool(config.get("features.tables.schema_renderer_enabled", True)) and bool(

            config.get("features.tables.normalized_rows_enabled", True)

        )



        self._market_age_slider_enabled = bool(

            config.get("features.trade.market_age_slider", False)

        )

        self._market_age_updating = False



        self._build_ui()

        self._hop_user_overridden = False

        self._hop_updating = False

        self.var_max_hop.trace_add("write", self._on_hop_changed)



        self._required_fields = [

            (ui.LABEL_STATION, self.var_start_station, self.e_station),

        ]



        if self._market_age_slider_enabled:

            self._apply_market_age_hours(float(self.var_max_age.get() or 0) * 24.0)



        # D3c â€“ pierwsze uzupeĹ‚nienie pĂłl z app_state

        self.refresh_from_app_state()
        self._update_station_hint()
        self._start_system_last_key = self._normalize_key(self.var_start_system.get() or "")
        self.var_start_system.trace_add("write", self._on_start_system_changed)
        self.var_start_station.trace_add("write", lambda *_a: self._update_station_hint())

        self.bind("<Visibility>", self._on_visibility)



    def _on_visibility(self, _event):

        self.refresh_from_app_state()
        self._update_station_hint()



    def _build_ui(self):

        fr = ttk.Frame(self)

        fr.pack(fill="both", expand=True, padx=8, pady=8)



        f_form = ttk.Frame(fr)

        f_form.pack(fill="x", pady=4)

        layout.configure_form_grid(f_form)



        self.e_system = layout.add_labeled_entry(

            f_form,

            0,

            ui.LABEL_SYSTEM,

            self.var_start_system,

            entry_width=layout.ENTRY_W_LONG,

        )

        self.e_station = layout.add_labeled_entry(

            f_form,

            1,

            ui.LABEL_STATION_REQUIRED,

            self.var_start_station,

            entry_width=layout.ENTRY_W_LONG,

        )
        station_tools = ttk.Frame(f_form)
        station_tools.grid(row=1, column=2, sticky="w", padx=(8, 0))
        self.btn_station_picker = ttk.Button(
            station_tools,
            text="Wybierz stacje...",
            command=self._open_station_picker_dialog,
        )
        self.btn_station_picker.pack(side="left")
        self.lbl_station_hint = ttk.Label(station_tools, textvariable=self._station_hint_var)
        self.lbl_station_hint.pack(side="left", padx=(8, 0))



        # Autocomplete dla systemu

        self.ac_source = AutocompleteController(

            self.root,

            self.e_system,

            suggest_func=self._suggest_system,

        )



        # Autocomplete dla stacji (D3b ??" na podstawie wybranego systemu)

        self.ac_station = AutocompleteController(

            self.root,

            self.e_station,

            min_chars=2,

            suggest_func=self._suggest_station,

        )
        self.e_station.bind("<FocusIn>", self._on_station_focus, add="+")
        self.e_station.bind("<Button-1>", self._on_station_focus, add="+")
        self.e_station.bind("<FocusOut>", self._on_station_focus_out, add="+")
        self.e_station.bind("<KeyPress>", self._on_station_keypress, add="+")
        self.e_station.bind("<Control-space>", self._on_station_picker_hotkey, add="+")



        f_detect = ttk.Frame(fr)

        f_detect.pack(fill="x", pady=(0, 6))

        self.lbl_detected = ttk.Label(f_detect, text="")

        self.lbl_detected.pack(side="left", padx=(10, 0))



        layout.add_labeled_pair(

            f_form,

            2,

            ui.LABEL_CAPITAL,

            self.var_capital,

            ui.LABEL_MAX_HOP,

            self.var_max_hop,

            left_entry_width=12,

        )

        layout.add_labeled_pair(

            f_form,

            3,

            ui.LABEL_CARGO,

            self.var_cargo,

            ui.LABEL_MAX_HOPS,

            self.var_max_hops,

        )

        if self._market_age_slider_enabled:

            _, max_age_entry = layout.add_labeled_pair(

                f_form,

                4,

                ui.LABEL_MAX_DISTANCE,

                self.var_max_dta,

                ui.LABEL_MARKET_AGE_CUTOFF,

                self.var_market_age_cutoff,

                right_entry_width=18,

            )

            self.e_max_age = max_age_entry

            self.e_max_age.bind("<FocusOut>", self._on_market_age_cutoff_commit)

            self.e_max_age.bind("<Return>", self._on_market_age_cutoff_commit)
            self.lbl_market_age_relative = ttk.Label(
                f_form,
                textvariable=self.var_market_age_relative,
            )
            self.lbl_market_age_relative.grid(
                row=4,
                column=5,
                sticky="w",
                padx=(8, 0),
            )



            f_age = ttk.Frame(fr)

            f_age.pack(fill="x", pady=(0, 4))

            ttk.Label(f_age, text=f"{ui.LABEL_MARKET_AGE_SLIDER}:").pack(

                side="left", padx=(10, 6)

            )

            self.scale_market_age = ttk.Scale(

                f_age,

                from_=self._market_age_slider_min_position(),

                to=self._market_age_slider_max_position(),

                variable=self.var_market_age_hours,

                command=self._on_market_age_slider,

            )

            self.scale_market_age.pack(side="left", fill="x", expand=True, padx=(0, 6))
        else:

            _, max_age_entry = layout.add_labeled_pair(

                f_form,

                4,

                ui.LABEL_MAX_DISTANCE,

                self.var_max_dta,

                ui.LABEL_MAX_AGE,

                self.var_max_age,

            )

            self.e_max_age = max_age_entry





        # --- Flagowe checkboxy -------------------------------------------------

        f_flags1 = ttk.Frame(fr)

        f_flags1.pack(fill="x", pady=4)



        ttk.Checkbutton(

            f_flags1,

            text=ui.FLAG_LARGE_PAD,

            variable=self.var_large_pad,

        ).pack(side="left", padx=5)

        ttk.Checkbutton(

            f_flags1,

            text=ui.FLAG_PLANETARY,

            variable=self.var_planetary,

        ).pack(side="left", padx=5)

        ttk.Checkbutton(

            f_flags1,

            text=ui.FLAG_PLAYER_OWNED,

            variable=self.var_player_owned,

        ).pack(side="left", padx=5)



        f_flags2 = ttk.Frame(fr)

        f_flags2.pack(fill="x", pady=4)



        ttk.Checkbutton(

            f_flags2,

            text=ui.FLAG_RESTRICTED,

            variable=self.var_restricted,

        ).pack(side="left", padx=5)

        ttk.Checkbutton(

            f_flags2,

            text=ui.FLAG_PROHIBITED,

            variable=self.var_prohibited,

        ).pack(side="left", padx=5)

        ttk.Checkbutton(

            f_flags2,

            text=ui.FLAG_AVOID_LOOPS,

            variable=self.var_avoid_loops,

        ).pack(side="left", padx=5)

        ttk.Checkbutton(

            f_flags2,

            text=ui.FLAG_ALLOW_PERMITS,

            variable=self.var_allow_permits,

        ).pack(side="left", padx=5)



        # --- Przyciski / status / lista ---------------------------------------

        f_actions = ttk.Frame(fr)
        f_actions.pack(fill="x", pady=(6, 4))

        center_group = ttk.Frame(f_actions)
        center_group.pack(anchor="center")

        bf = ttk.Frame(center_group)
        bf.pack(side="left")

        self.btn_run = ttk.Button(
            bf,
            text=ui.BUTTON_CALCULATE_TRADE,
            command=self.run_trade,
        )
        self.btn_run.pack(side="left", padx=(0, 6))
        ttk.Button(bf, text=ui.BUTTON_CLEAR, command=self.clear).pack(side="left")

        self.lbl_status = ttk.Label(center_group, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack(side="left", padx=(20, 0))

        if self._use_treeview:

            self.lst_trade = common.stworz_tabele_trasy(fr, title=ui.LIST_TITLE_TRADE)
            common.render_table_treeview(self.lst_trade, "trade", [])
            self.lst_trade.bind("<Map>", self._on_trade_table_mapped, add="+")

        else:

            self.lst_trade = common.stworz_liste_trasy(fr, title=ui.LIST_TITLE_TRADE)

        common.attach_results_context_menu(

            self.lst_trade,

            self._get_results_payload,

            self._get_results_actions,

        )
        self._results_widget = self.lst_trade
        common.enable_results_checkboxes(self.lst_trade, enabled=True)
        self._show_empty_state()
        if isinstance(self.lst_trade, ttk.Treeview):
            self.lst_trade.bind("<<TreeviewSelect>>", self._on_results_selection_changed, add="+")
        else:
            self.lst_trade.bind("<<ListboxSelect>>", self._on_results_selection_changed, add="+")
        summary_wrap = ttk.Frame(fr)
        summary_wrap.pack(fill="x", padx=8, pady=(4, 0))
        self.lbl_trade_summary = ttk.Label(
            summary_wrap,
            textvariable=self.var_trade_summary,
            anchor="e",
            justify="right",
        )
        self.lbl_trade_summary.pack(side="right", fill="x", expand=True)
        self._clear_trade_summary()

        details_wrap = ttk.LabelFrame(fr, text="Szczegoly kroku")
        details_wrap.pack(fill="x", padx=8, pady=(4, 8))
        self.lbl_trade_leg_route = ttk.Label(
            details_wrap,
            textvariable=self.var_trade_leg_route,
            anchor="w",
            justify="left",
        )
        self.lbl_trade_leg_route.pack(fill="x", padx=8, pady=(6, 0))
        self.lbl_trade_leg_meta = ttk.Label(
            details_wrap,
            textvariable=self.var_trade_leg_meta,
            anchor="w",
            justify="left",
        )
        self.lbl_trade_leg_meta.pack(fill="x", padx=8, pady=(0, 6))

        leg_table_wrap = ttk.Frame(details_wrap)
        leg_table_wrap.pack(fill="x", padx=8, pady=(0, 8))
        leg_scroll = ttk.Scrollbar(leg_table_wrap)
        leg_scroll.pack(side="right", fill="y")
        self.tree_leg_commodities = ttk.Treeview(
            leg_table_wrap,
            columns=("commodity", "amount", "buy", "sell", "profit_t", "profit_total"),
            show="headings",
            selectmode="browse",
            height=4,
            yscrollcommand=leg_scroll.set,
        )
        self.tree_leg_commodities.heading("commodity", text="Towar")
        self.tree_leg_commodities.heading("amount", text="Ilosc")
        self.tree_leg_commodities.heading("buy", text="Kupno")
        self.tree_leg_commodities.heading("sell", text="Sprzedaz")
        self.tree_leg_commodities.heading("profit_t", text="Zysk/t")
        self.tree_leg_commodities.heading("profit_total", text="Zysk")
        self.tree_leg_commodities.column("commodity", anchor="w", width=220, stretch=True)
        self.tree_leg_commodities.column("amount", anchor="e", width=80, stretch=False)
        self.tree_leg_commodities.column("buy", anchor="e", width=95, stretch=False)
        self.tree_leg_commodities.column("sell", anchor="e", width=95, stretch=False)
        self.tree_leg_commodities.column("profit_t", anchor="e", width=95, stretch=False)
        self.tree_leg_commodities.column("profit_total", anchor="e", width=115, stretch=False)
        self.tree_leg_commodities.pack(side="left", fill="x", expand=True)
        leg_scroll.config(command=self.tree_leg_commodities.yview)
        self._clear_trade_leg_details()

    def _on_trade_table_mapped(self, _event=None) -> None:
        if not isinstance(self.lst_trade, ttk.Treeview):
            return
        if self._trade_table_layout_ready and self.lst_trade.winfo_width() > 1:
            return
        self._trade_table_layout_retry_count = 0
        self.root.after_idle(self._refresh_trade_table_layout)

    def _refresh_trade_table_layout(self) -> None:
        if not isinstance(self.lst_trade, ttk.Treeview):
            return
        try:
            if not self.lst_trade.winfo_exists():
                return
        except Exception:
            return

        # Hidden notebook pages can report width=1 for a long time.
        # Avoid infinite startup polling and wait for the next real map/visibility.
        try:
            if not self.lst_trade.winfo_viewable():
                return
        except Exception:
            return

        try:
            current_width = int(self.lst_trade.winfo_width())
        except Exception:
            current_width = 0
        if current_width <= 1:
            self._trade_table_layout_retry_count += 1
            if self._trade_table_layout_retry_count <= 10:
                self.root.after(60, self._refresh_trade_table_layout)
            return

        selected = tuple(self.lst_trade.selection())
        rows = list(self._results_rows or getattr(self.lst_trade, "_renata_table_rows", []) or [])
        common.render_table_treeview(self.lst_trade, "trade", rows)
        for iid in selected:
            if self.lst_trade.exists(iid):
                self.lst_trade.selection_add(iid)
        self._trade_table_layout_ready = True
        self._trade_table_layout_retry_count = 0





    def _market_age_min_hours(self) -> float:

        return 1.0



    def _market_age_max_hours(self) -> float:

        return 24.0 * 365.0 * 10.0



    def _market_age_slider_min_position(self) -> float:

        return 0.0


    def _market_age_slider_max_position(self) -> float:

        return 100.0


    def _market_age_forever_position(self) -> float:

        return self._market_age_slider_min_position()


    def _is_market_age_forever_position(self, position: float) -> bool:

        return position <= (self._market_age_forever_position() + 0.5)


    def _market_age_clamp_slider_position(self, position: float) -> float:

        min_pos = self._market_age_slider_min_position()

        max_pos = self._market_age_slider_max_position()

        if position < min_pos:

            return min_pos

        if position > max_pos:

            return max_pos

        return position



    def _clamp_market_age_hours(self, hours: float) -> float:

        min_h = self._market_age_min_hours()

        max_h = self._market_age_max_hours()

        if hours < min_h:

            return min_h

        if hours > max_h:

            return max_h

        return hours



    def _market_age_hours_from_slider_position(self, position: float) -> float | None:

        position = self._market_age_clamp_slider_position(position)

        if self._is_market_age_forever_position(position):

            return None

        min_h = self._market_age_min_hours()

        max_h = self._market_age_max_hours()

        # Log scale keeps short ranges usable while still allowing multi-year history.
        normalized = (self._market_age_slider_max_position() - position) / (
            self._market_age_slider_max_position() - 1.0
        )
        normalized = max(0.0, min(1.0, normalized))
        ratio = max_h / min_h
        hours = min_h * (ratio ** normalized)
        return self._clamp_market_age_hours(hours)


    def _market_age_slider_position_from_hours(self, hours: float) -> float:

        hours = self._clamp_market_age_hours(hours)
        min_h = self._market_age_min_hours()
        max_h = self._market_age_max_hours()
        if hours <= min_h:
            return self._market_age_slider_max_position()
        if hours >= max_h:
            return 1.0
        ratio = max_h / min_h
        normalized = math.log(hours / min_h, ratio)
        position = self._market_age_slider_max_position() - (
            normalized * (self._market_age_slider_max_position() - 1.0)
        )
        return self._market_age_clamp_slider_position(position)


    def _format_market_age_cutoff(self, value: datetime) -> str:

        return value.strftime("%Y-%m-%d %H:%M")



    def _parse_market_age_cutoff(self, raw: str) -> datetime | None:

        try:

            return datetime.strptime(raw, "%Y-%m-%d %H:%M")

        except Exception:

            return None



    def _format_market_age_relative(self, hours: float | None) -> str:

        if hours is None:

            return "forever"

        if hours < 24.0:

            return f"{int(round(hours))}h wstecz"

        days = hours / 24.0
        if days < 365.0:
            return f"{int(round(days))}d wstecz"
        years = days / 365.0
        if years >= 10.0:
            return "10 lat wstecz"
        return f"{years:.1f} lat wstecz"


    def _set_market_age_forever(self) -> None:

        if self._market_age_updating:
            return

        self._market_age_updating = True
        try:
            self._market_age_forever = True
            self.var_market_age_hours.set(self._market_age_forever_position())
            self.var_max_age.set(0.0)
            self.var_market_age_cutoff.set("forever")
            self.var_market_age_relative.set(self._format_market_age_relative(None))
        finally:
            self._market_age_updating = False


    def _apply_market_age_hours(self, hours: float) -> None:

        if self._market_age_updating:

            return

        try:

            hours = float(hours)

        except Exception:

            return

        self._market_age_updating = True

        try:

            hours = self._clamp_market_age_hours(hours)

            self._market_age_forever = False

            self.var_market_age_hours.set(self._market_age_slider_position_from_hours(hours))

            self.var_max_age.set(hours / 24.0)

            cutoff = datetime.now() - timedelta(hours=hours)

            self.var_market_age_cutoff.set(self._format_market_age_cutoff(cutoff))
            self.var_market_age_relative.set(self._format_market_age_relative(hours))

        finally:

            self._market_age_updating = False



    def _on_market_age_slider(self, value: str) -> None:

        if self._market_age_updating:

            return

        try:
            position = float(value)
        except Exception:
            return
        hours = self._market_age_hours_from_slider_position(position)
        if hours is None:
            self._set_market_age_forever()
            return
        self._apply_market_age_hours(hours)



    def _on_market_age_cutoff_commit(self, _event=None) -> None:

        if self._market_age_updating:

            return

        raw = (self.var_market_age_cutoff.get() or "").strip()

        if not raw:

            return

        if raw.casefold() in {"forever", "bez limitu", "brak limitu"}:
            self._set_market_age_forever()
            return

        parsed = self._parse_market_age_cutoff(raw)

        if parsed is None:

            return

        hours = (datetime.now() - parsed).total_seconds() / 3600.0

        self._apply_market_age_hours(hours)


    def _resolve_trade_max_age(self) -> float | None:

        if self._market_age_slider_enabled and self._market_age_forever:
            return None
        try:
            return float(self.var_max_age.get())
        except Exception:
            return None




    def _can_start(self) -> bool:
        if self._busy:
            common.emit_status("WARN", "ROUTE_BUSY", text="Laduje...", source="spansh.trade", ui_target="trade")
            return False
        if route_manager.is_busy():
            common.emit_status("WARN", "ROUTE_BUSY", text="Inny planner juz liczy.", source="spansh.trade", ui_target="trade")
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if getattr(self, "btn_run", None):
            self.btn_run.config(state=("disabled" if busy else "normal"))
        if getattr(self, "lbl_status", None):
            self.lbl_status.config(text=("Laduje..." if busy else "Gotowy"))

    def _get_results_payload(self, row_index, row_text=None) -> dict | None:

        try:

            idx = int(row_index) - int(self._results_row_offset)

        except Exception:

            return None

        if idx < 0 or idx >= len(self._results_rows):

            return None

        row = self._results_rows[idx]
        system, has_system = common.resolve_copy_system_value("trade", row, row_text)
        from_station = (row.get("from_station") or "").strip()
        to_station = (row.get("to_station") or "").strip()
        unknown_station = "UNKNOWN_STATION"
        station_values = [
            val
            for val in (from_station, to_station)
            if val and val != unknown_station
        ]
        if len(station_values) >= 2 and station_values[0].casefold() != station_values[1].casefold():
            station_value = f"{station_values[0]} -> {station_values[1]}"
        elif station_values:
            station_value = station_values[0]
        else:
            station_value = unknown_station

        return {

            "row_index": idx,

            "row_text": row_text,

            "schema_id": "trade",

            "row": row,
            "system": system,
            "has_system": has_system,

            "from_system": row.get("from_system"),

            "to_system": row.get("to_system"),

            "station": station_value,

        }



    def _get_results_actions(self, payload: dict) -> list[dict]:

        actions = []

        system = (payload.get("system") or "").strip()
        has_system = bool(payload.get("has_system", False))
        from_system = (payload.get("from_system") or "").strip()

        station = (payload.get("station") or "").strip()

        actions.append(

            {

                "label": "Kopiuj system",

                "action": lambda p: common.copy_text_to_clipboard(system, context="results.system"),

            }

        )
        row_idx = int(payload.get("row_index", -1))
        row_exists = 0 <= row_idx < len(self._results_rows)
        selected_exists = bool(self._selected_internal_indices())
        all_exists = bool(self._results_rows)
        actions.append({"separator": True})
        actions.append(
            {
                "label": "Kopiuj wiersze",
                "children": [
                    {
                        "label": "Kopiuj wiersz",
                        "action": lambda p: self._copy_clicked_row(p),
                        "enabled": row_exists,
                    },
                    {
                        "label": "Kopiuj z naglowkiem",
                        "action": lambda p: self._copy_clicked_delimited(
                            p,
                            sep="\t",
                            include_header=True,
                            context="results.row_with_header",
                        ),
                        "enabled": row_exists,
                    },
                    {
                        "label": "Kopiuj zaznaczone",
                        "action": lambda p: self._copy_selected_rows(p),
                        "enabled": selected_exists or row_exists,
                    },
                    {
                        "label": "Kopiuj wszystko",
                        "action": lambda p: self._copy_all_rows(),
                        "enabled": all_exists,
                    },
                ],
            }
        )

        if station:

            actions.append(

                {

                    "label": "Kopiuj stacje",

                    "action": lambda p: common.copy_text_to_clipboard(station, context="results.station"),

                }

            )



        if has_system or station:
            actions.append({"separator": True})
        if from_system:

            actions.append(

                {

                    "label": "Ustaw jako Start",

                    "action": lambda p: self.var_start_system.set(from_system),

                }

            )

        if all_exists:
            actions.append({"separator": True})
            actions.append(
                {
                    "label": "Kopiuj do Excela",
                    "children": [
                        {
                            "label": "Zaznaczone",
                            "action": lambda p: self._copy_selected_delimited(
                                p,
                                sep="\t",
                                include_header=False,
                                context="results.excel_selected",
                            ),
                            "enabled": selected_exists or row_exists,
                        },
                        {
                            "label": "Z naglowkiem",
                            "action": lambda p: self._copy_selected_delimited(
                                p,
                                sep="\t",
                                include_header=True,
                                context="results.excel_headers_selected",
                            ),
                            "enabled": selected_exists or row_exists,
                        },
                        {
                            "label": "Wiersz",
                            "action": lambda p: self._copy_clicked_delimited(
                                p,
                                sep="\t",
                                include_header=False,
                                context="results.excel_row",
                            ),
                            "enabled": row_exists,
                        },
                        {
                            "label": "Wszystko",
                            "action": lambda p: self._copy_all_delimited(
                                sep="\t",
                                include_header=False,
                                context="results.excel_all",
                            ),
                            "enabled": all_exists,
                        },
                    ],
                }
            )



        while actions and actions[-1].get("separator"):
            actions.pop()
        return actions

    def _format_result_line(self, row: dict, row_text: str | None = None) -> str:
        try:
            rendered = common.render_table_lines("trade", [row])
            if rendered:
                return str(rendered[0]).strip()
        except Exception:
            pass
        return str(row_text or "").strip()

    def _selected_internal_indices(self) -> list[int]:
        widget = self._results_widget
        if widget is None:
            return []
        checked = common.get_checked_internal_indices(
            widget,
            row_offset=self._results_row_offset,
            rows_len=len(self._results_rows),
        )
        if checked:
            return checked
        indices: list[int] = []
        if isinstance(widget, ttk.Treeview):
            selected_ids = set(str(item) for item in (widget.selection() or ()))
            if not selected_ids:
                return []
            for iid in widget.get_children():
                if str(iid) not in selected_ids:
                    continue
                try:
                    idx = int(str(iid)) - int(self._results_row_offset)
                except Exception:
                    continue
                if 0 <= idx < len(self._results_rows):
                    indices.append(idx)
            return indices

        try:
            selected = list(widget.curselection())
        except Exception:
            selected = []
        for item in selected:
            try:
                idx = int(item) - int(self._results_row_offset)
            except Exception:
                continue
            if 0 <= idx < len(self._results_rows):
                indices.append(idx)
        return indices

    def _copy_indices_to_clipboard(self, indices: list[int], *, context: str) -> None:
        lines: list[str] = []
        for idx in indices:
            if idx < 0 or idx >= len(self._results_rows):
                continue
            row = self._results_rows[idx]
            line = self._format_result_line(row)
            if line:
                lines.append(line)
        text = "\n".join(lines).strip()
        if not text:
            return
        common.copy_text_to_clipboard(text, context=context)

    def _copy_clicked_row(self, payload: dict) -> None:
        idx = int(payload.get("row_index", -1))
        if idx < 0 or idx >= len(self._results_rows):
            return
        self._copy_indices_to_clipboard([idx], context="results.row")

    def _copy_selected_rows(self, payload: dict) -> None:
        indices = self._selected_internal_indices()
        if not indices:
            idx = int(payload.get("row_index", -1))
            if idx >= 0:
                indices = [idx]
        if not indices:
            return
        self._copy_indices_to_clipboard(indices, context="results.rows_selected")

    def _copy_all_rows(self) -> None:
        if not self._results_rows:
            return
        self._copy_indices_to_clipboard(list(range(len(self._results_rows))), context="results.rows_all")

    def _copy_indices_delimited_to_clipboard(
        self,
        indices: list[int],
        *,
        sep: str,
        include_header: bool,
        context: str,
    ) -> None:
        rows: list[dict] = []
        for idx in indices:
            if idx < 0 or idx >= len(self._results_rows):
                continue
            row = self._results_rows[idx]
            if isinstance(row, dict):
                rows.append(row)
        if not rows:
            return

        lines: list[str] = []
        if include_header:
            header = common.format_header_delimited("trade", sep)
            if header:
                lines.append(header)
        for row in rows:
            line = common.format_row_delimited("trade", row, sep)
            if line:
                lines.append(line)
        text = "\n".join(lines).strip()
        if not text:
            return
        common.copy_text_to_clipboard(text, context=context)

    def _copy_clicked_delimited(self, payload: dict, *, sep: str, include_header: bool, context: str) -> None:
        idx = int(payload.get("row_index", -1))
        if idx < 0 or idx >= len(self._results_rows):
            return
        self._copy_indices_delimited_to_clipboard(
            [idx],
            sep=sep,
            include_header=include_header,
            context=context,
        )

    def _copy_selected_delimited(self, payload: dict, *, sep: str, include_header: bool, context: str) -> None:
        indices = self._selected_internal_indices()
        if not indices:
            idx = int(payload.get("row_index", -1))
            if idx >= 0:
                indices = [idx]
        if not indices:
            return
        self._copy_indices_delimited_to_clipboard(
            indices,
            sep=sep,
            include_header=include_header,
            context=context,
        )

    def _copy_all_delimited(self, *, sep: str, include_header: bool, context: str) -> None:
        if not self._results_rows:
            return
        self._copy_indices_delimited_to_clipboard(
            list(range(len(self._results_rows))),
            sep=sep,
            include_header=include_header,
            context=context,
        )





    def refresh_from_app_state(self):

        """D3c: uzupeĹ‚nia pola System/Stacja na podstawie AppState.



        UĹĽywamy TEGO SAMEGO app_state, co navigation_events.

        """

        try:

            sysname = (getattr(self.app_state, "current_system", "") or "").strip()

            staname = (getattr(self.app_state, "current_station", "") or "").strip()

            is_docked = bool(getattr(self.app_state, "is_docked", False))
            live_ready = bool(getattr(self.app_state, "has_live_system_event", False))

        except Exception:

            sysname = ""

            staname = ""

            is_docked = False
            live_ready = False



        # Traktujemy 'Unknown' / 'Nieznany' jak brak realnej lokalizacji

        if sysname in ("Unknown", "Nieznany"):

            sysname = ""

        if not (self.var_start_system.get() or "").strip() and sysname:

            self.var_start_system.set(sysname)

        if is_docked and not self._get_station_input() and staname:

            self.var_start_station.set(staname)

            self._remember_station(sysname, staname)



        print(f"[TRADE] refresh_from_app_state: {sysname!r} / {staname!r}")

        self._set_detected_label(sysname, staname if is_docked else "")



    # ------------------------------------------------------------------ logika GUI



    def _suggest_station(self, tekst: str):

        """Funkcja podpowiedzi stacji dla AutocompleteController.



        Bazuje najpierw na aktualnym systemie z pola,

        a je‘>li jest puste f?" na app_state.current_system.

        """

        system = (self.var_start_system.get() or "").strip()

        if not system:
            live_ready = bool(getattr(self.app_state, "has_live_system_event", False))
            if live_ready:
                system = (getattr(self.app_state, "current_system", "") or "").strip()



        # Je‘>li kto‘> ma w polu systemu format "System / Stacja" / "System, Stacja",

        # to do zapytania o stacje bierzemy tylko nazwŽt systemu (czŽt‘>ŽA przed separatorem).

        raw = system

        if "/" in raw:

            raw = raw.split("/", 1)[0].strip()

        elif "," in raw:

            raw = raw.split(",", 1)[0].strip()



        q = (tekst or "").strip()

        if not q and not raw:

            return []



        if not raw:

            return self._filter_stations(self._recent_stations, q)



        cached = []

        if self._station_autocomplete_by_system:

            cached = self._get_cached_stations(raw)

            if cached:

                # q może być puste -> pokaż całą listę
                return self._filter_stations(cached, q)



        if q == "":
            # pełna lista z EDSM (jeśli dostępny)
            if is_edsm_enabled():
                edsm_list = edsm_stations_for_system(raw)
                if edsm_list:
                    self._remember_station_list(raw, edsm_list)
                    self.root.after(0, lambda: self._finish_station_loading(len(edsm_list)))
                    return self._filter_stations(self._get_cached_stations(raw), q)
                self.root.after(0, lambda: self._finish_station_loading(0))
            return []

        if not self._station_lookup_online:

            return []



        try:
            results = spansh_client.stations_for_system(raw, q or None)
            if results:
                return results
            return []

        except Exception as e:

            print(f"[Spansh] Station autocomplete exception ({raw!r}, {q!r}): {e}")

            return []



    def _on_station_focus(self, _event):

        if not getattr(self, "ac_station", None):

            return
        now = time.monotonic()
        if now - self._station_last_trigger_ts < 0.5:
            return
        self._station_last_trigger_ts = now
        system = (self.var_start_system.get() or "").strip()
        if system:
            cached = self._get_cached_stations(system)
            if not cached and is_edsm_enabled() and not self._get_station_input():
                self._station_loading = True
                self._set_station_hint("Ładuję listę stacji…")

        # Pokazuj listę już na focus, nawet bez wpisanego tekstu.

        self.ac_station.trigger_suggest(force=True)

    def _on_station_focus_out(self, _event):
        self._update_station_hint()

    def _on_station_keypress(self, _event):
        self._update_station_hint()

    def _on_station_picker_hotkey(self, _event):
        self._open_station_picker_dialog()
        return "break"

    def _load_station_candidates(self, system: str) -> list[str]:
        raw_system = (system or "").strip()
        if not raw_system:
            return []

        cached = self._get_cached_stations(raw_system)
        if cached:
            return cached

        stations: list[str] = []
        if self._station_autocomplete_by_system and is_edsm_enabled():
            try:
                stations = edsm_stations_for_system(raw_system) or []
            except Exception:
                stations = []
            if stations:
                self._remember_station_list(raw_system, stations)
                cached = self._get_cached_stations(raw_system)
                if cached:
                    return cached

        if self._station_lookup_online:
            try:
                stations = spansh_client.stations_for_system(raw_system, None) or []
            except Exception:
                stations = []
            if stations:
                self._remember_station_list(raw_system, stations)
                cached = self._get_cached_stations(raw_system)
                if cached:
                    return cached

        return self._filter_stations(self._recent_stations, "")

    def _open_station_picker_dialog(self) -> None:
        system = (self.var_start_system.get() or "").strip()
        if not system:
            self._set_station_hint("Najpierw wybierz system")
            try:
                self.e_system.focus_set()
            except Exception:
                pass
            return

        # Re-open existing picker if still alive.
        existing = getattr(self, "_station_picker_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_set()
                    return
            except Exception:
                pass
            self._station_picker_window = None

        stations_all = self._load_station_candidates(system)
        if not stations_all:
            self._set_station_hint("Brak listy stacji dla wybranego systemu")
            return

        top = tk.Toplevel(self)
        self._station_picker_window = top
        top.title(f"Wybierz stacje ({system})")
        top.transient(self.root)
        top.geometry("760x520")
        top.minsize(560, 380)

        info_var = tk.StringVar(value=f"Dostepne stacje: {len(stations_all)}")
        query_var = tk.StringVar()

        f_top = ttk.Frame(top, padding=10)
        f_top.pack(fill="both", expand=True)

        ttk.Label(f_top, text=f"System: {system}").pack(anchor="w")
        ttk.Label(f_top, textvariable=info_var).pack(anchor="w", pady=(2, 8))

        f_filter = ttk.Frame(f_top)
        f_filter.pack(fill="x", pady=(0, 8))
        ttk.Label(f_filter, text="Filtr stacji:").pack(side="left", padx=(0, 6))
        e_filter = ttk.Entry(f_filter, textvariable=query_var)
        e_filter.pack(side="left", fill="x", expand=True)

        f_list = ttk.Frame(f_top)
        f_list.pack(fill="both", expand=True)
        sc = ttk.Scrollbar(f_list, orient="vertical")
        sc.pack(side="right", fill="y")
        lb = tk.Listbox(
            f_list,
            yscrollcommand=sc.set,
            selectmode="browse",
            exportselection=False,
            font=("Consolas", 10),
        )
        lb.pack(side="left", fill="both", expand=True)
        sc.config(command=lb.yview)

        displayed: list[str] = []

        def _refresh_list(*_args) -> None:
            q = (query_var.get() or "").strip().lower()
            lb.delete(0, tk.END)
            displayed.clear()
            for item in stations_all:
                if q and q not in item.lower():
                    continue
                displayed.append(item)
                lb.insert(tk.END, item)
            info_var.set(f"Dostepne stacje: {len(displayed)} / {len(stations_all)}")
            if displayed:
                lb.selection_clear(0, tk.END)
                lb.selection_set(0)
                lb.activate(0)

        def _apply_selection(_event=None) -> None:
            if not displayed:
                return
            sel = lb.curselection()
            if not sel:
                idx = lb.index("active")
            else:
                idx = sel[0]
            if idx is None:
                return
            try:
                station = displayed[int(idx)]
            except Exception:
                return
            self.var_start_station.set(station)
            self._remember_station(system, station)
            try:
                if hasattr(self, "ac_station"):
                    self.ac_station.hide()
            except Exception:
                pass
            _close_picker()

        def _close_picker() -> None:
            try:
                if top.winfo_exists():
                    top.destroy()
            finally:
                self._station_picker_window = None
                self._update_station_hint()
                try:
                    self.e_station.focus_set()
                except Exception:
                    pass

        f_btn = ttk.Frame(f_top)
        f_btn.pack(fill="x", pady=(10, 0))
        ttk.Button(f_btn, text="Wybierz", command=_apply_selection).pack(side="right")
        ttk.Button(f_btn, text="Anuluj", command=_close_picker).pack(side="right", padx=(0, 8))

        query_var.trace_add("write", _refresh_list)
        lb.bind("<Double-Button-1>", _apply_selection)
        lb.bind("<Return>", _apply_selection)
        top.bind("<Escape>", lambda _e: _close_picker())

        _refresh_list()
        e_filter.focus_set()
        top.protocol("WM_DELETE_WINDOW", _close_picker)

    def _suggest_system(self, tekst: str):

        """Funkcja podpowiedzi systemĂłw dla AutocompleteController."""

        q = (tekst or "").strip()

        if not q:

            return []



        try:

            return spansh_client.systems_suggest(q)

        except Exception as e:

            print(f"[Spansh] System autocomplete exception ({q!r}): {e}")

            return []



    def _normalize_key(self, value: str) -> str:

        return (value or "").strip().lower()

    def _on_start_system_changed(self, *_args) -> None:
        current_key = self._normalize_key(self.var_start_system.get() or "")
        previous_key = getattr(self, "_start_system_last_key", None)
        self._start_system_last_key = current_key

        # Pierwszy trace po starcie nie powinien kasowac juz ustawionej stacji.
        if previous_key is None:
            self._update_station_hint()
            return

        if current_key == previous_key:
            self._update_station_hint()
            return

        if self._get_station_input():
            self.var_start_station.set("")

        try:
            if hasattr(self, "ac_station"):
                self.ac_station.hide()
        except Exception:
            pass

        self._clear_station_hint()
        self._update_station_hint()

    def _get_station_input(self) -> str:
        return (self.var_start_station.get() or "").strip()

    def _finish_station_loading(self, count: int) -> None:
        self._station_loading = False
        if self._get_station_input():
            self._clear_station_hint()
            return
        if count > 0:
            self._set_station_hint("Lista stacji załadowana.")
            self.root.after(1200, self._update_station_hint)
            try:
                focused = str(self.root.focus_get()) == str(self.e_station)
            except Exception:
                focused = False
            if focused and getattr(self, "ac_station", None):
                # Po pierwszym załadowaniu pokaż listę bez drugiego kliku.
                self.root.after(10, lambda: self.ac_station.trigger_suggest(query="", force=True))
            return
        if not is_edsm_enabled():
            self._set_station_hint("Wpisz 1 literę, aby wyszukać stację…")
            return
        self._set_station_hint("Brak stacji w EDSM — wpisz 1 literę, aby wyszukać stację…")

    def _set_station_hint(self, text: str) -> None:
        self._station_hint_var.set(text or "")

    def _clear_station_hint(self) -> None:
        self._station_hint_var.set("")

    def _update_station_hint(self) -> None:
        if self._station_loading:
            return
        if self._get_station_input():
            self._clear_station_hint()
            return

        system = (self.var_start_system.get() or "").strip()
        if not system:
            self._set_station_hint("Najpierw wybierz system")
            return
        if not is_edsm_enabled():
            self._set_station_hint("Wpisz 1 literę, aby wyszukać stację…")
            return
        self._clear_station_hint()



    def _remember_station(self, system: str, station: str) -> None:

        sys_value = (system or "").strip()

        sta_value = (station or "").strip()

        if not sys_value or not sta_value:

            return

        key = self._normalize_key(sys_value)

        if key not in self._station_cache:

            self._station_cache[key] = set()

        self._station_cache[key].add(sta_value)



        recent = [s for s in self._recent_stations if self._normalize_key(s) != self._normalize_key(sta_value)]

        recent.insert(0, sta_value)

        self._recent_stations = recent[: self._recent_limit]

    def _remember_station_list(self, system: str, stations: list[str]) -> None:
        sys_value = (system or "").strip()
        if not sys_value:
            return
        key = self._normalize_key(sys_value)
        bucket = self._station_cache.get(key)
        if bucket is None:
            bucket = set()
            self._station_cache[key] = bucket
        for station in stations or []:
            sta_value = (station or "").strip()
            if sta_value:
                bucket.add(sta_value)



    def _get_cached_stations(self, system: str) -> list[str]:

        key = self._normalize_key(system)

        stations = list(self._station_cache.get(key, set()))

        stations.sort(key=lambda item: item.lower())

        return stations



    def _filter_stations(self, stations: list[str], query: str) -> list[str]:

        if not stations:

            return []

        q = query.strip().lower()

        if not q:

            return stations

        return [item for item in stations if q in item.lower()]



    def _set_detected_label(self, system: str, station: str) -> None:

        if not getattr(self, "lbl_detected", None):

            return

        sys_value = (system or "").strip()

        sta_value = (station or "").strip()

        if sys_value and sta_value:

            text = f"{ui.DETECTED_PREFIX}: {sys_value} / {sta_value}"

        elif sys_value:

            text = f"{ui.DETECTED_PREFIX}: {sys_value}"

        else:

            text = ""

        self.lbl_detected.config(text=text)



    def hide_suggestions(self):

        self.ac_source.hide()

        if hasattr(self, "ac_station"):

            self.ac_station.hide()

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            text = str(value).strip().replace("\xa0", "").replace(" ", "")
            if not text:
                return None
            if "," in text and "." not in text:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
            return float(text)
        except Exception:
            return None

    @classmethod
    def _parse_updated_age_seconds(cls, value: str | None) -> float | None:
        text = (value or "").strip()
        if not text:
            return None
        lower = text.casefold()
        if lower in {"just now", "now", "teraz", "przed chwila"}:
            return 0.0
        if "few second" in lower:
            return 5.0
        if "a minute" in lower or "an minute" in lower:
            return 60.0
        if "an hour" in lower or "a hour" in lower:
            return 3600.0

        match = cls._UPDATED_AGE_RE.search(lower)
        if match:
            try:
                num = float(match.group("num"))
            except Exception:
                num = None
            if num is not None:
                unit = match.group("unit").casefold()
                if unit in {"s", "sec", "secs", "second", "seconds", "sek", "sekunda", "sekundy", "sekund"}:
                    return num
                if unit in {"m", "min", "mins", "minute", "minutes", "minuta", "minuty", "minut"}:
                    return num * 60.0
                if unit in {"h", "hr", "hrs", "hour", "hours", "godz", "godzina", "godziny", "godzin"}:
                    return num * 3600.0
                if unit in {"d", "day", "days", "dzien", "dni"}:
                    return num * 86400.0
                if unit in {"w", "week", "weeks", "tydzien", "tygodnie", "tygodni"}:
                    return num * 7.0 * 86400.0
                if unit in {"month", "months", "miesiac", "miesiace", "miesiecy"}:
                    return num * 30.0 * 86400.0
                if unit in {"y", "year", "years", "rok", "lata", "lat"}:
                    return num * 365.0 * 86400.0

        # Fallback: try timestamp string and convert to "age".
        candidate = text.replace("Z", "")
        try:
            parsed = datetime.fromisoformat(candidate)
        except Exception:
            parsed = None
        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except Exception:
                    continue
        if parsed is None:
            return None
        age = (datetime.now() - parsed.replace(tzinfo=None)).total_seconds()
        return max(age, 0.0)

    @classmethod
    def _updated_range_text(cls, rows: list[dict]) -> str:
        parsed: list[tuple[float, str]] = []
        fallback_values: list[str] = []
        for row in rows:
            raw = (row.get("updated_ago") or row.get("updated_at") or "").strip()
            if not raw:
                continue
            fallback_values.append(raw)
            seconds = cls._parse_updated_age_seconds(raw)
            if seconds is not None:
                parsed.append((seconds, raw))
        if parsed:
            newest = min(parsed, key=lambda item: item[0])[1]
            oldest = max(parsed, key=lambda item: item[0])[1]
            if newest == oldest:
                return newest
            return f"{newest} ... {oldest}"
        if not fallback_values:
            return "-"
        if len(fallback_values) == 1:
            return fallback_values[0]
        return f"{fallback_values[0]} ... {fallback_values[-1]}"

    def _clear_trade_summary(self) -> None:
        self.var_trade_summary.set("")

    def _update_trade_summary(self, rows: list[dict]) -> None:
        if not rows:
            self._clear_trade_summary()
            return

        total_profit_sum = 0
        has_total_profit = False
        last_payload_cumulative: int | None = None
        distance_total = 0.0
        has_distance = False

        for row in rows:
            total_profit = self._to_float(row.get("total_profit"))
            if total_profit is not None:
                total_profit_sum += int(round(total_profit))
                has_total_profit = True

            cumulative = self._to_float(row.get("cumulative_profit"))
            if bool(row.get("cumulative_profit_from_payload")) and cumulative is not None:
                last_payload_cumulative = int(round(cumulative))

            distance_ly = self._to_float(row.get("distance_ly"))
            if distance_ly is not None and distance_ly >= 0:
                distance_total += distance_ly
                has_distance = True

        if last_payload_cumulative is not None:
            profit_label = "Cumulative Profit"
            profit_value = last_payload_cumulative
        else:
            profit_label = "Total Profit"
            profit_value = total_profit_sum if has_total_profit else None

        jump_range = self._to_float(self._last_effective_jump_range)
        if jump_range is None or jump_range <= 0:
            jump_range = self._to_float(self.var_max_hop.get())
        estimated_jumps: int | None = None
        if has_distance and jump_range is not None and jump_range > 0:
            estimated_jumps = 0
            for row in rows:
                distance_ly = self._to_float(row.get("distance_ly"))
                if distance_ly is None or distance_ly < 0:
                    continue
                estimated_jumps += int(math.ceil(distance_ly / jump_range))

        profit_text = common.format_value(profit_value, "cr")
        distance_text = f"{common.format_value(distance_total, 'ly')} ly" if has_distance else "-"
        jumps_text = str(estimated_jumps) if estimated_jumps is not None else "-"
        updated_text = self._updated_range_text(rows)

        summary = (
            f"{profit_label}: {profit_text} | "
            f"Dystans: {distance_text} | "
            f"Skoki (szac.): {jumps_text} | "
            f"Updated: {updated_text}"
        )
        self.var_trade_summary.set(summary)

    def _clear_trade_leg_details(self) -> None:
        self.var_trade_leg_route.set("Wybierz krok trasy, aby zobaczyc szczegoly towarow.")
        self.var_trade_leg_meta.set("Updated: - | Cumulative Profit: -")
        tree = getattr(self, "tree_leg_commodities", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            return

    def _iter_leg_commodities(self, row: dict) -> list[dict]:
        commodities = row.get("commodities_raw")
        if isinstance(commodities, list) and commodities:
            normalized: list[dict] = []
            for item in commodities:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "name": item.get("name"),
                        "amount": item.get("amount"),
                        "buy_price": item.get("buy_price"),
                        "sell_price": item.get("sell_price"),
                        "profit_unit": item.get("profit_unit") if item.get("profit_unit") is not None else item.get("profit"),
                        "total_profit": item.get("total_profit"),
                    }
                )
            if normalized:
                return normalized

        return [
            {
                "name": row.get("commodity_primary") or row.get("commodity_display") or row.get("commodity"),
                "amount": row.get("amount"),
                "buy_price": row.get("buy_price"),
                "sell_price": row.get("sell_price"),
                "profit_unit": row.get("profit"),
                "total_profit": row.get("total_profit"),
            }
        ]

    def _show_trade_leg_details_by_index(self, idx: int | None) -> None:
        if idx is None or idx < 0 or idx >= len(self._results_rows):
            self._clear_trade_leg_details()
            return

        row = self._results_rows[idx]
        from_system = (row.get("from_system") or "-").strip() or "-"
        from_station = (row.get("from_station") or "-").strip() or "-"
        to_system = (row.get("to_system") or "-").strip() or "-"
        to_station = (row.get("to_station") or "-").strip() or "-"
        self.var_trade_leg_route.set(
            f"{from_system} ({from_station}) -> {to_system} ({to_station})"
        )

        updated = (row.get("updated_ago") or row.get("updated_at") or "-").strip() or "-"
        cumulative = common.format_value(row.get("cumulative_profit"), "cr")
        self.var_trade_leg_meta.set(f"Updated: {updated} | Cumulative Profit: {cumulative}")

        tree = getattr(self, "tree_leg_commodities", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            return

        commodities = self._iter_leg_commodities(row)
        for item in commodities:
            name = str(item.get("name") or row.get("commodity_display") or "-")
            amount = common.format_value(item.get("amount"), "int")
            buy_price = common.format_value(item.get("buy_price"), "cr")
            sell_price = common.format_value(item.get("sell_price"), "cr")
            profit_unit = common.format_value(item.get("profit_unit"), "cr")
            total_profit = common.format_value(item.get("total_profit"), "cr")
            tree.insert(
                "",
                "end",
                values=(name, amount, buy_price, sell_price, profit_unit, total_profit),
            )

    def _get_primary_selected_internal_index(self) -> int | None:
        widget = self._results_widget
        if widget is None:
            return None

        if isinstance(widget, ttk.Treeview):
            selected = widget.selection() or ()
            if not selected:
                return None
            try:
                idx = int(str(selected[0])) - int(self._results_row_offset)
            except Exception:
                return None
            return idx if 0 <= idx < len(self._results_rows) else None

        try:
            selected = list(widget.curselection())
        except Exception:
            return None
        if not selected:
            return None
        try:
            idx = int(selected[0]) - int(self._results_row_offset)
        except Exception:
            return None
        return idx if 0 <= idx < len(self._results_rows) else None

    def _on_results_selection_changed(self, _event=None) -> None:
        self._show_trade_leg_details_by_index(self._get_primary_selected_internal_index())

    def _select_first_result_row(self) -> None:
        if not self._results_rows:
            self._clear_trade_leg_details()
            return
        widget = self._results_widget
        if widget is None:
            self._show_trade_leg_details_by_index(0)
            return
        if isinstance(widget, ttk.Treeview):
            children = widget.get_children()
            if children:
                try:
                    first = children[0]
                    widget.selection_set(first)
                    widget.focus(first)
                    widget.see(first)
                except Exception:
                    pass
        else:
            try:
                widget.selection_clear(0, tk.END)
                widget.selection_set(0)
                widget.activate(0)
                widget.see(0)
            except Exception:
                pass
        self._show_trade_leg_details_by_index(0)



    def clear(self):

        if isinstance(self.lst_trade, ttk.Treeview):

            self.lst_trade.delete(*self.lst_trade.get_children())

        else:

            self.lst_trade.delete(0, tk.END)
        common.clear_results_checkboxes(self.lst_trade)

        self.lbl_status.config(text="Wyczyszczono", foreground="grey")

        self._results_rows = []

        self._results_row_offset = 0
        self._last_effective_jump_range = None
        self._clear_trade_summary()
        self._clear_trade_leg_details()
        self._show_empty_state()

    def _show_empty_state(self) -> None:
        title, message = empty_state.get_copy("no_results")
        if isinstance(self.lst_trade, ttk.Treeview):
            empty_state.show_state(
                self.lst_trade,
                empty_state.UIState.EMPTY,
                title,
                message,
                display_mode="overlay_body",
            )
            return
        empty_state.show_state(self.lst_trade, empty_state.UIState.EMPTY, title, message)

    def _hide_empty_state(self) -> None:
        empty_state.hide_state(self.lst_trade)



    def run_trade(self):
        """
        Startuje obliczenia w osobnym watku.
        """
        if not self._can_start():
            return
        self.clear()




        start_system = self.var_start_system.get().strip()

        start_station = self._get_station_input()



        # Fallback do aktualnej lokalizacji z app_state, jeĹ›li pola sÄ… puste

        if not start_system:

            start_system = (getattr(self.app_state, "current_system", "") or "").strip()

        if not start_station and bool(getattr(self.app_state, "is_docked", False)):

            start_station = (getattr(self.app_state, "current_station", "") or "").strip()



        if start_system and start_station:

            self._remember_station(start_system, start_station)



        # Ostateczny fallback do config.STATE (zgodnoĹ›Ä‡ wsteczna)



        if not start_system:

            common.emit_status(

                "ERROR",

                "TRADE_INPUT_MISSING",

                source="spansh.trade",

                ui_target="trade",

            )

            return



        # D3b: dwa tryby wejĹ›cia:

        # 1) klasyczny: osobne System + Stacja,

        # 2) kompatybilny z webowym SPANSH: "System / Stacja" w jednym polu,

        #    puste pole "Stacja" -> backend rozbije to w oblicz_trade().

        if not self._validate_required_fields(start_system, start_station):

            return



        capital = self.var_capital.get()

        max_hop = self._resolve_max_hop()
        self._last_effective_jump_range = max_hop

        cargo = self.var_cargo.get()

        max_hops = self.var_max_hops.get()

        max_dta = self.var_max_dta.get()

        max_age = self._resolve_trade_max_age()



        flags = {

            "large_pad": self.var_large_pad.get(),

            "planetary": self.var_planetary.get(),

            "player_owned": self.var_player_owned.get(),

            "restricted": self.var_restricted.get(),

            "prohibited": self.var_prohibited.get(),

            "avoid_loops": self.var_avoid_loops.get(),

            "allow_permits": self.var_allow_permits.get(),

        }



        args = (

            start_system,

            start_station,

            capital,

            max_hop,

            cargo,

            max_hops,

            max_dta,

            max_age,

            flags,

        )



        self._set_busy(True)
        route_manager.start_route_thread("trade", self._th, args=args, gui_ref=self.root)



    def _has_inline_station(self, system_value: str) -> bool:

        if not system_value:

            return False

        return "/" in system_value or "," in system_value



    def _validate_required_fields(self, start_system: str, start_station: str) -> bool:

        if start_station:

            return True

        if self._has_inline_station(start_system):

            return True

        label = self._required_fields[0][0] if self._required_fields else "Stacja"

        common.emit_status(

            "WARN",

            "TRADE_STATION_REQUIRED",

            text=f"Uzupełnij pole: {label}",

            source="spansh.trade",

            ui_target="trade",

            notify_overlay=True,

        )

        return False



    def apply_jump_range_from_ship(self, value: float | None) -> None:

        if not config.get("planner_auto_use_ship_jump_range", True):

            return

        if self._hop_user_overridden:

            return

        if value is None:

            return

        self._set_max_hop(value)



    def _on_hop_changed(self, *_args) -> None:

        if self._hop_updating:

            return

        if not config.get("planner_allow_manual_range_override", True):

            return

        self._hop_user_overridden = True



    def _set_max_hop(self, value: float) -> None:

        try:

            self._hop_updating = True

            self.var_max_hop.set(float(value))

        except Exception:

            pass

        finally:

            self._hop_updating = False



    def _resolve_max_hop(self) -> float:

        if not config.get("planner_auto_use_ship_jump_range", True):

            return float(self.var_max_hop.get())

        if self._hop_user_overridden:

            return float(self.var_max_hop.get())



        jr = getattr(self.app_state.ship_state, "jump_range_current_ly", None)

        if jr is not None:

            self._set_max_hop(jr)

            return float(jr)



        fallback = config.get("planner_fallback_range_ly", 30.0)

        try:

            fallback = float(fallback)

        except Exception:

            fallback = 30.0

        self._set_max_hop(fallback)

        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="trade"):

            common.emit_status(

                "WARN",

                "JR_NOT_READY_FALLBACK",

                source="spansh.trade",

                ui_target="trade",

                notify_overlay=True,

            )

        return fallback



    def _th(
        self,
        start_system,
        start_station,
        capital,
        max_hop,
        cargo,
        max_hops,
        max_dta,
        max_age,
        flags,
    ):
        """
        Watek roboczy: wywoluje logike trade.oblicz_trade i wypelnia liste.
        """
        tr = []
        rows = []
        worker_error = None
        try:
            tr, rows = trade.oblicz_trade(
                start_system,
                start_station,
                capital,
                max_hop,
                cargo,
                max_hops,
                max_dta,
                max_age,
                flags,
                self.root,
            )
        except Exception as exc:
            worker_error = exc
        finally:
            def _apply_result() -> None:
                try:
                    if worker_error is not None:
                        self._clear_trade_summary()
                        common.emit_status(
                            "ERROR",
                            "TRADE_ERROR",
                            text=f"Blad: {worker_error}",
                            source="spansh.trade",
                            ui_target="trade",
                        )
                        return

                    if rows:
                        common.clear_results_checkboxes(self.lst_trade)
                        self._results_rows = rows
                        self._results_row_offset = 0
                        route_manager.set_route(tr, "trade")
                        if (
                            config.get("features.tables.spansh_schema_enabled", True)
                            and config.get("features.tables.schema_renderer_enabled", True)
                            and config.get("features.tables.normalized_rows_enabled", True)
                        ):
                            if self._use_treeview:
                                common.render_table_treeview(self.lst_trade, "trade", rows)
                                common.register_active_route_list(
                                    self.lst_trade,
                                    [],
                                    numerate=False,
                                    offset=1,
                                    schema_id="trade",
                                    rows=rows,
                                )
                            else:
                                opis = common.render_table_lines("trade", rows)
                                common.register_active_route_list(
                                    self.lst_trade,
                                    opis,
                                    numerate=False,
                                    offset=1,
                                    schema_id="trade",
                                    rows=rows,
                                )
                                common.wypelnij_liste(
                                    self.lst_trade,
                                    opis,
                                    numerate=False,
                                    show_copied_suffix=False,
                                )
                        else:
                            opis = [
                                (
                                    f"{row.get('from_system', '')} ({row.get('from_station', 'UNKNOWN_STATION')})"
                                    f" -> {row.get('to_system', '')} ({row.get('to_station', 'UNKNOWN_STATION')})"
                                )
                                for row in rows
                            ]
                            common.register_active_route_list(self.lst_trade, opis)
                            common.wypelnij_liste(self.lst_trade, opis)
                        self._hide_empty_state()
                        self._update_trade_summary(rows)
                        self._select_first_result_row()
                        common.handle_route_ready_autoclipboard(self, tr, status_target="trade")
                        common.emit_status(
                            "OK",
                            "TRADE_FOUND",
                            text=f"Znaleziono {len(rows)} propozycji.",
                            source="spansh.trade",
                            ui_target="trade",
                        )
                    else:
                        self._clear_trade_summary()
                        self._show_empty_state()
                        common.emit_status(
                            "ERROR",
                            "TRADE_NO_RESULTS",
                            source="spansh.trade",
                            ui_target="trade",
                        )
                finally:
                    self._set_busy(False)

            run_on_ui_thread(self.root, _apply_result)


