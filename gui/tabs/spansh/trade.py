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
from gui.window_chrome import apply_renata_orange_window_chrome
from gui.window_focus import bring_window_to_front
from logic.utils.renata_log import log_event, log_event_throttled





class TradeTab(ttk.Frame):

    """

    Zakladka: Trade Planner (Spansh)

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



        # System / stacja startowa - inicjalnie puste,

        # uzupelniane z app_state w refresh_from_app_state().

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
        self._ui_state_suppress_persist = True



        self._results_rows: list[dict] = []
        self._trade_table_layout_ready: bool = False
        self._trade_table_layout_retry_count: int = 0
        self._trade_details_collapsed: bool = True

        self._results_row_offset = 0
        self._results_widget = None
        self._last_effective_jump_range: float | None = None
        self.var_trade_summary = tk.StringVar(value="")
        self.var_trade_leg_route = tk.StringVar(value="")
        self.var_trade_leg_meta = tk.StringVar(value="")
        self.var_trade_details_toggle = tk.StringVar(value="Pokaz szczegoly kroku")
        self.var_sell_assist_state = tk.StringVar(value="")
        self.var_sell_assist_note = tk.StringVar(value="")
        self._sell_assist_dismissed = False
        self._sell_assist_decision_space: dict | None = None

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
        self._restore_trade_ui_state()



        self._build_ui()

        self._hop_user_overridden = False

        self._hop_updating = False

        self.var_max_hop.trace_add("write", self._on_hop_changed)



        self._required_fields = [

            (ui.LABEL_STATION, self.var_start_station, self.e_station),

        ]



        if self._market_age_slider_enabled:

            self._apply_market_age_hours(float(self.var_max_age.get() or 0) * 24.0)



        # D3c - pierwsze uzupelnienie pol z app_state

        self.refresh_from_app_state()
        self._update_station_hint()
        self._start_system_last_key = self._normalize_key(self.var_start_system.get() or "")
        self.var_start_system.trace_add("write", self._on_start_system_changed)
        self.var_start_station.trace_add("write", lambda *_a: self._update_station_hint())

        self.bind("<Visibility>", self._on_visibility)
        self._bind_trade_ui_state_persistence()



    def _on_visibility(self, _event):

        self.refresh_from_app_state()
        self._update_station_hint()

    def _collect_trade_ui_state_flags(self) -> dict[str, bool]:
        return {
            "large_pad": bool(self.var_large_pad.get()),
            "planetary": bool(self.var_planetary.get()),
            "player_owned": bool(self.var_player_owned.get()),
            "restricted": bool(self.var_restricted.get()),
            "prohibited": bool(self.var_prohibited.get()),
            "avoid_loops": bool(self.var_avoid_loops.get()),
            "allow_permits": bool(self.var_allow_permits.get()),
        }

    def _restore_trade_ui_state(self) -> None:
        try:
            ui_state = config.get_ui_state(default={})
            spansh_state = ui_state.get("spansh") if isinstance(ui_state, dict) else {}
            trade_state = (spansh_state or {}).get("trade")
            flags = (trade_state or {}).get("flags") if isinstance(trade_state, dict) else {}
            if not isinstance(flags, dict):
                return
            mapping = {
                "large_pad": self.var_large_pad,
                "planetary": self.var_planetary,
                "player_owned": self.var_player_owned,
                "restricted": self.var_restricted,
                "prohibited": self.var_prohibited,
                "avoid_loops": self.var_avoid_loops,
                "allow_permits": self.var_allow_permits,
            }
            for key, var in mapping.items():
                if key in flags:
                    var.set(bool(flags.get(key)))
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_UI_STATE_RESTORE_FAILED",
                "Spansh Trade: restore UI state failed",
                cooldown_sec=120.0,
                context="spansh.trade.ui_state.restore",
            )

    def _persist_trade_ui_state(self) -> None:
        if bool(getattr(self, "_ui_state_suppress_persist", False)):
            return
        try:
            config.update_ui_state(
                {
                    "spansh": {
                        "trade": {
                            "flags": self._collect_trade_ui_state_flags(),
                        }
                    }
                }
            )
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_UI_STATE_PERSIST_FAILED",
                "Spansh Trade: persist UI state failed",
                cooldown_sec=120.0,
                context="spansh.trade.ui_state.persist",
            )

    def _on_trade_flag_var_changed(self, *_args) -> None:
        self._persist_trade_ui_state()

    def _bind_trade_ui_state_persistence(self) -> None:
        for var in (
            self.var_large_pad,
            self.var_planetary,
            self.var_player_owned,
            self.var_restricted,
            self.var_prohibited,
            self.var_avoid_loops,
            self.var_allow_permits,
        ):
            var.trace_add("write", self._on_trade_flag_var_changed)
        self._ui_state_suppress_persist = False



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

            slider_wrap = tk.Frame(
                f_age,
                bg="#d0ccc6",
                borderwidth=0,
                highlightthickness=0,
            )
            slider_wrap.pack(side="left", fill="x", expand=True, padx=(0, 6))

            self.scale_market_age = ttk.Scale(

                slider_wrap,

                from_=self._market_age_slider_min_position(),

                to=self._market_age_slider_max_position(),

                variable=self.var_market_age_hours,

                command=self._on_market_age_slider,
                style="Horizontal.TScale",

            )

            self.scale_market_age.pack(fill="x", expand=True, padx=1, pady=1)
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

        # Sell Assist pozostaje aktywny w logice runtime, ale bez panelu UI w Trade.
        self._clear_sell_assist()

        self.trade_split = ttk.PanedWindow(fr, orient=tk.VERTICAL)
        self.trade_split.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self.trade_top_wrap = ttk.Frame(self.trade_split)
        self.trade_bottom_wrap = ttk.Frame(self.trade_split)
        self.trade_split.add(self.trade_top_wrap, weight=4)
        self.trade_split.add(self.trade_bottom_wrap, weight=2)

        if self._use_treeview:

            self.lst_trade = common.stworz_tabele_trasy(self.trade_top_wrap, title=ui.LIST_TITLE_TRADE)
            common.render_table_treeview(self.lst_trade, "trade", [])
            self._apply_trade_tree_compact_columns()
            self.lst_trade.bind("<Map>", self._on_trade_table_mapped, add="+")
            self.lst_trade.bind("<Configure>", self._on_trade_results_tree_configure, add="+")

        else:

            self.lst_trade = common.stworz_liste_trasy(self.trade_top_wrap, title=ui.LIST_TITLE_TRADE)

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
        summary_wrap = ttk.Frame(self.trade_top_wrap)
        summary_wrap.pack(fill="x", padx=8, pady=(4, 0))
        self.lbl_trade_summary = ttk.Label(
            summary_wrap,
            textvariable=self.var_trade_summary,
            anchor="e",
            justify="right",
        )
        self.lbl_trade_summary.pack(side="right", fill="x", expand=True)
        self._clear_trade_summary()

        details_header = ttk.Frame(self.trade_bottom_wrap)
        details_header.pack(fill="x")
        self.btn_trade_details_toggle = ttk.Button(
            details_header,
            textvariable=self.var_trade_details_toggle,
            command=self._toggle_trade_details,
        )
        self.btn_trade_details_toggle.pack(side="left")
        ttk.Label(
            details_header,
            text="Panel szczegolow aktywuje sie po zaznaczeniu kroku trasy.",
        ).pack(side="right")

        self.trade_details_body = ttk.LabelFrame(self.trade_bottom_wrap, text="Szczegoly kroku")
        self.trade_details_body.pack(fill="both", expand=True, pady=(4, 0))

        details_wrap = self.trade_details_body
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
        leg_table_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        leg_scroll = ttk.Scrollbar(leg_table_wrap, orient="vertical", style="Vertical.TScrollbar")
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
        self.tree_leg_commodities.pack(side="left", fill="both", expand=True)
        self.tree_leg_commodities.bind("<Configure>", self._on_trade_leg_tree_configure, add="+")
        leg_scroll.config(command=self.tree_leg_commodities.yview)
        self._clear_trade_leg_details(collapse=True)
        self._set_trade_details_collapsed(True, force=True)

    def _apply_trade_tree_compact_columns(self) -> None:
        if not isinstance(self.lst_trade, ttk.Treeview):
            return
        try:
            columns = list(self.lst_trade["columns"] or [])
        except Exception:
            columns = []
        for col in columns:
            if col in ("__sel__", "__lp__"):
                continue
            try:
                self.lst_trade.column(col, stretch=False)
            except Exception:
                continue
        # Keep the compact profile, but allow a few text columns to absorb extra width
        # so short result sets do not look "broken" on wide windows.
        for col in ("from_system", "from_station", "to_system", "to_station", "commodity"):
            if col not in columns:
                continue
            try:
                self.lst_trade.column(col, stretch=True)
            except Exception:
                continue
        self._reflow_trade_results_tree_columns()

    def _on_trade_results_tree_configure(self, _event=None) -> None:
        self._reflow_trade_results_tree_columns()

    def _reflow_trade_results_tree_columns(self) -> None:
        if not isinstance(self.lst_trade, ttk.Treeview):
            return
        tree = self.lst_trade
        try:
            columns = list(tree["columns"] or [])
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
        try:
            total = 0
            for col in columns:
                total += int(tree.column(col, "width") or 0)
        except Exception:
            return
        extra = tree_width - total - 24
        if extra <= 0:
            return

        elastic_cols = [col for col in ("to_station", "from_station", "commodity", "to_system", "from_system") if col in columns]
        if not elastic_cols:
            return
        share = max(1, extra // len(elastic_cols))
        remainder = max(0, extra - (share * len(elastic_cols)))
        for idx, col in enumerate(elastic_cols):
            try:
                current = int(tree.column(col, "width") or 0)
                bonus = share + (1 if idx < remainder else 0)
                tree.column(col, width=max(80, current + bonus), stretch=True)
            except Exception:
                continue

    def _on_trade_leg_tree_configure(self, _event=None) -> None:
        self._reflow_trade_leg_tree_columns()

    def _reflow_trade_leg_tree_columns(self) -> None:
        tree = getattr(self, "tree_leg_commodities", None)
        if not isinstance(tree, ttk.Treeview):
            return
        try:
            tree_width = int(tree.winfo_width() or 0)
        except Exception:
            return
        if tree_width <= 0:
            return
        try:
            columns = list(tree["columns"] or [])
        except Exception:
            return
        if not columns or "commodity" not in columns:
            return
        try:
            total = 0
            for col in columns:
                total += int(tree.column(col, "width") or 0)
        except Exception:
            return
        extra = tree_width - total - 18
        if extra <= 0:
            return
        try:
            current = int(tree.column("commodity", "width") or 0)
            tree.column("commodity", width=max(140, current + extra), stretch=True)
        except Exception:
            return

    def _clear_sell_assist(self) -> None:
        self._sell_assist_decision_space = None
        self._sell_assist_dismissed = False
        self.var_sell_assist_state.set("Sell Assist: brak aktywnego rankingu.")
        self.var_sell_assist_note.set("Po wyznaczeniu trasy pojawia sie 2-3 opcje + Pomijam.")
        host = getattr(self, "sell_assist_cards_host", None)
        if host is None:
            return
        for child in host.winfo_children():
            try:
                child.destroy()
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_SELL_ASSIST_CARD_DESTROY_FAILED",
                    "Spansh Trade: sell-assist card destroy failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.sell_assist.clear",
                )

    def _dismiss_sell_assist(self) -> None:
        self._sell_assist_dismissed = True
        self.var_sell_assist_state.set("Sell Assist: pomijam - decyzja po stronie pilota.")
        self.var_sell_assist_note.set("Mozesz wrzucic nowe dane trasy, aby odswiezyc ranking.")
        common.emit_status(
            "INFO",
            "SELL_ASSIST_SKIPPED",
            text="Sell Assist pominięty. Renata nie zmienia trasy.",
            source="spansh.trade.sell_assist",
            ui_target="trade",
            notify_overlay=False,
        )

    def _apply_sell_assist_intent(self, option: dict | None) -> None:
        result = trade.handoff_sell_assist_to_route_intent(
            option if isinstance(option, dict) else {},
            set_route_intent=self.app_state.set_route_intent,
            source="spansh.trade.sell_assist.intent",
            allow_auto_route=False,
        )
        if not bool(result.get("ok")):
            self.var_sell_assist_state.set("Sell Assist: brak celu dla intentu.")
            self.var_sell_assist_note.set("Nie udało się ustawić intentu dla tej opcji.")
            common.emit_status(
                "WARN",
                "SELL_ASSIST_INTENT_NOT_SET",
                text="Nie udało się ustawić intentu (brak celu).",
                source="spansh.trade.sell_assist",
                ui_target="trade",
                notify_overlay=False,
            )
            return

        target_display = str(result.get("target_display") or result.get("target_system") or "-")
        self.var_sell_assist_state.set(f"Sell Assist: ustawiono intent -> {target_display}")
        self.var_sell_assist_note.set("Tryb intent aktywny. Bez auto-route i bez automatyzacji mapy gry.")
        common.emit_status(
            "OK",
            "SELL_ASSIST_INTENT_SET",
            text=f"Ustawiono intent: {target_display} (bez auto-route).",
            source="spansh.trade.sell_assist",
            ui_target="trade",
            notify_overlay=False,
        )

    def _format_sell_assist_card(self, option: dict, index: int) -> tuple[str, str]:
        label = str(option.get("label") or f"Opcja {index}")
        to_system = str(option.get("to_system") or "-")
        to_station = str(option.get("to_station") or "-")
        destination = f"{to_system} ({to_station})"
        reason = option.get("reasoning") or {}
        profit = str(reason.get("profit_text") or common.format_value(option.get("estimated_profit"), "cr"))
        eta = str(reason.get("eta_text") or "-")
        distance = str(reason.get("distance_text") or "-")
        risk = str(reason.get("risk_text") or option.get("risk_label") or "-")
        trust = str(reason.get("trust_text") or option.get("trust_label") or "-")
        scores = option.get("scores") or {}
        s_price = int(scores.get("price_score") or 0)
        s_time = int(scores.get("time_score") or 0)
        s_risk = int(scores.get("risk_score") or 0)
        s_trust = int(scores.get("trust_score") or 0)
        line1 = (
            f"{index}. {label} -> {destination} | Zysk: {profit} | ETA: {eta} | Dystans: {distance}"
        )
        line2 = (
            f"Trade-off: ryzyko={risk}, zaufanie={trust} | "
            f"SCORES P/T/R/Tr: {s_price}/{s_time}/{s_risk}/{s_trust}"
        )
        return line1, line2

    def _render_sell_assist_cards(self, decision_space: dict | None) -> None:
        host = getattr(self, "sell_assist_cards_host", None)
        if host is None:
            return
        for child in host.winfo_children():
            try:
                child.destroy()
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_SELL_ASSIST_CARD_DESTROY_FAILED",
                    "Spansh Trade: sell-assist card destroy failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.sell_assist.render",
                )

        payload = decision_space or {}
        options = list(payload.get("options") or [])
        mode = str(payload.get("mode") or "empty")
        advisory = bool(payload.get("advisory_only", False))
        if mode == "empty" or not options:
            self.var_sell_assist_state.set("Sell Assist: brak opcji do porownania.")
            self.var_sell_assist_note.set(str(payload.get("note") or "Sprawdz dane i sprobuj ponownie."))
            return

        state = f"Sell Assist: {len(options)} opcje (bez top 1)."
        if advisory:
            state += " Tryb orientacyjny."
        self.var_sell_assist_state.set(state)
        self.var_sell_assist_note.set(str(payload.get("note") or ""))

        for idx, option in enumerate(options, start=1):
            card = ttk.Frame(host)
            card.pack(fill="x", pady=(0, 4))
            action_row = ttk.Frame(card)
            action_row.pack(fill="x")
            ttk.Button(
                action_row,
                text="Ustaw intent",
                command=lambda opt=option: self._apply_sell_assist_intent(opt),
            ).pack(side="right")
            line1, line2 = self._format_sell_assist_card(option, idx)
            ttk.Label(card, text=line1, anchor="w", justify="left").pack(fill="x")
            ttk.Label(card, text=line2, anchor="w", justify="left").pack(fill="x")

    def _update_sell_assist(self, rows: list[dict], jump_range: float | None) -> None:
        if not rows:
            self._clear_sell_assist()
            return
        decision_space = trade.build_sell_assist_decision_space(rows, jump_range=jump_range)
        self._sell_assist_decision_space = decision_space
        self._sell_assist_dismissed = False
        self._render_sell_assist_cards(decision_space)
        if bool((decision_space or {}).get("advisory_only")):
            self._emit_trade_data_stale_callout(rows)

    def _emit_trade_data_stale_callout(self, rows: list[dict]) -> None:
        try:
            from logic.insight_dispatcher import emit_insight
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_DATA_STALE_CALLOUT_IMPORT_FAILED",
                "Spansh Trade: stale-data callout import failed",
                cooldown_sec=120.0,
                context="spansh.trade.data_stale.import",
            )
            return
        first = rows[0] if rows else {}
        system = str(first.get("from_system") or getattr(app_state, "current_system", "") or "unknown").strip() or "unknown"
        raw_text = "Dane rynkowe sa nieswieze. Traktuj wynik orientacyjnie."
        try:
            emit_insight(
                raw_text,
                gui_ref=self.root,
                message_id="MSG.TRADE_DATA_STALE",
                source="spansh_trade",
                event_type="TRADE_DATA_QUALITY",
                context={
                    "system": system,
                    "raw_text": raw_text,
                    "source_status": str(first.get("source_status") or "").strip(),
                    "confidence": str(first.get("confidence") or "").strip(),
                    "data_age": str(first.get("data_age") or "").strip(),
                },
                priority="P2_NORMAL",
                dedup_key=f"trade_stale:{system}",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
            )
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_DATA_STALE_CALLOUT_EMIT_FAILED",
                "Spansh Trade: stale-data callout emit failed",
                cooldown_sec=120.0,
                context=f"spansh.trade.data_stale.emit:{system}",
            )
            return

    def _toggle_trade_details(self) -> None:
        self._set_trade_details_collapsed(not self._trade_details_collapsed)

    def _set_trade_details_collapsed(self, collapsed: bool, *, force: bool = False) -> None:
        if self._trade_details_collapsed == bool(collapsed) and not force:
            return
        self._trade_details_collapsed = bool(collapsed)
        if self._trade_details_collapsed:
            self.var_trade_details_toggle.set("Pokaz szczegoly kroku")
            try:
                self.trade_details_body.pack_forget()
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_DETAILS_PANEL_COLLAPSE_FAILED",
                    "Spansh Trade: collapse details panel failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.details.collapse",
                )
            return

        self.var_trade_details_toggle.set("Ukryj szczegoly kroku")
        try:
            if not self.trade_details_body.winfo_manager():
                self.trade_details_body.pack(fill="both", expand=True, pady=(4, 0))
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_DETAILS_PANEL_EXPAND_FAILED",
                "Spansh Trade: expand details panel failed",
                cooldown_sec=60.0,
                context="spansh.trade.details.expand",
            )
        self.root.after_idle(self._position_trade_splitter_for_details)

    def _position_trade_splitter_for_details(self) -> None:
        try:
            if not self.trade_split.winfo_viewable():
                return
        except Exception:
            return
        try:
            total_h = int(self.trade_split.winfo_height())
        except Exception:
            return
        if total_h <= 1:
            return
        detail_h = max(200, int(total_h * 0.32))
        sash_pos = max(120, total_h - detail_h)
        try:
            self.trade_split.sashpos(0, sash_pos)
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_DETAILS_SPLITTER_POSITION_FAILED",
                "Spansh Trade: details splitter position failed",
                cooldown_sec=60.0,
                context="spansh.trade.details.splitter",
            )

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
        self._apply_trade_tree_compact_columns()
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
            log_event_throttled(
                "WARN",
                "TRADE_ROW_RENDER_FALLBACK",
                "Spansh Trade: row render fallback used",
                cooldown_sec=60.0,
                context="spansh.trade.results.row_render",
            )
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

        """D3c: uzupelnia pola System/Stacja na podstawie AppState.



        Uzywamy TEGO SAMEGO app_state, co navigation_events.

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



        if config.get("features.debug.trade_state_trace", False):
            log_event(
                "TRADE",
                "refresh_from_app_state",
                system=sysname,
                station=staname,
                is_docked=is_docked,
                live_ready=live_ready,
            )

        self._set_detected_label(sysname, staname if is_docked else "")



    # ------------------------------------------------------------------ logika GUI



    def _suggest_station(self, tekst: str):

        """Funkcja podpowiedzi stacji dla AutocompleteController.



        Bazuje najpierw na aktualnym systemie z pola,

        a jesli jest puste - na app_state.current_system.

        """

        system = self._system_name_for_station_lookup(self.var_start_system.get() or "")

        if not system:
            if hasattr(self.app_state, "has_live_system_event_flag"):
                live_ready = bool(self.app_state.has_live_system_event_flag())
            else:
                live_ready = bool(getattr(self.app_state, "has_live_system_event", False))
            if live_ready:
                if hasattr(self.app_state, "get_current_system_name"):
                    system = self._system_name_for_station_lookup(
                        self.app_state.get_current_system_name() or ""
                    )
                else:
                    system = self._system_name_for_station_lookup(
                        getattr(self.app_state, "current_system", "") or ""
                    )

        raw = self._system_name_for_station_lookup(system)



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
            log_event_throttled(
                "TRADE:station_autocomplete_exception",
                3000,
                "TRADE",
                "station autocomplete exception",
                system=raw,
                query=q,
                error=f"{type(e).__name__}: {e}",
            )
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

    @staticmethod
    def _system_name_for_station_lookup(value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return ""
        if "/" in raw:
            raw = raw.split("/", 1)[0].strip()
        elif "," in raw:
            raw = raw.split(",", 1)[0].strip()
        return raw

    def _load_station_candidates(self, system: str) -> list[str]:
        raw_system = self._system_name_for_station_lookup(system)
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
                log_event_throttled(
                    "WARN",
                    "TRADE_STATION_LOOKUP_EDSM_FAILED",
                    "Spansh Trade: EDSM station lookup failed",
                    cooldown_sec=60.0,
                    context=f"spansh.trade.station_lookup.edsm:{raw_system.lower()}",
                )
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
                log_event_throttled(
                    "WARN",
                    "TRADE_STATION_LOOKUP_SPANSH_FAILED",
                    "Spansh Trade: Spansh station lookup failed",
                    cooldown_sec=60.0,
                    context=f"spansh.trade.station_lookup.spansh:{raw_system.lower()}",
                )
                stations = []
            if stations:
                self._remember_station_list(raw_system, stations)
                cached = self._get_cached_stations(raw_system)
                if cached:
                    return cached

        return self._filter_stations(self._recent_stations, "")

    def _open_station_picker_dialog(self) -> None:
        source_system = (self.var_start_system.get() or "").strip()
        if not source_system:
            self._set_station_hint("Najpierw wybierz system")
            try:
                self.e_system.focus_set()
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_STATION_PICKER_FOCUS_FAILED",
                    "Spansh Trade: focus system field failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.station_picker.focus_system",
                )
            return
        system = self._system_name_for_station_lookup(source_system)
        if not system:
            self._set_station_hint("Najpierw wybierz system")
            try:
                self.e_system.focus_set()
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_STATION_PICKER_FOCUS_FAILED",
                    "Spansh Trade: focus system field failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.station_picker.focus_system",
                )
            return

        # Re-open existing picker if still alive.
        existing = getattr(self, "_station_picker_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    bring_window_to_front(
                        existing,
                        source="spansh.trade.station_picker.reopen",
                        user_initiated=True,
                        deiconify=True,
                        request_focus=True,
                        force_focus=False,
                    )
                    return
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_STATION_PICKER_REOPEN_FAILED",
                    "Spansh Trade: reopen station picker failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.station_picker.reopen",
                )
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
        # Explicit palette for picker to avoid theme-dependent invisible controls.
        bg = "#0b0c10"
        panel_bg = "#1f2833"
        fg_main = "#ff7100"
        fg_sec = "#c5c6c7"
        fg_text = "#ffffff"
        top.configure(bg=bg)
        try:
            apply_renata_orange_window_chrome(top)
        except Exception:
            log_event_throttled(
                "WARN",
                "TRADE_STATION_PICKER_CHROME_FAILED",
                "Spansh Trade: station picker chrome styling failed",
                cooldown_sec=120.0,
                context="spansh.trade.station_picker.chrome",
            )

        info_var = tk.StringVar(value=f"Dostepne stacje: {len(stations_all)}")
        query_var = tk.StringVar()

        f_top = tk.Frame(top, bg=bg, padx=10, pady=10)
        f_top.pack(fill="both", expand=True)

        tk.Label(
            f_top,
            text=f"System: {system}",
            bg=bg,
            fg=fg_main,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            f_top,
            textvariable=info_var,
            bg=bg,
            fg=fg_sec,
            anchor="w",
        ).pack(anchor="w", pady=(2, 8))

        f_filter = tk.Frame(f_top, bg=bg)
        f_filter.pack(fill="x", pady=(0, 8))
        tk.Label(
            f_filter,
            text="Filtr stacji:",
            bg=bg,
            fg=fg_main,
        ).pack(side="left", padx=(0, 6))
        e_filter = tk.Entry(
            f_filter,
            textvariable=query_var,
            bg=panel_bg,
            fg=fg_text,
            insertbackground=fg_text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=panel_bg,
            highlightcolor=fg_main,
            borderwidth=0,
        )
        e_filter.pack(side="left", fill="x", expand=True)

        f_list = tk.Frame(f_top, bg=bg)
        f_list.pack(fill="both", expand=True)
        sc = tk.Scrollbar(
            f_list,
            orient="vertical",
            bg=panel_bg,
            troughcolor=bg,
            activebackground=fg_main,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        sc.pack(side="right", fill="y")
        lb = tk.Listbox(
            f_list,
            yscrollcommand=sc.set,
            selectmode="browse",
            exportselection=False,
            font=("Consolas", 10),
            bg=panel_bg,
            fg=fg_text,
            selectbackground=fg_main,
            selectforeground=bg,
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=panel_bg,
            highlightcolor=fg_main,
        )
        lb.pack(side="left", fill="both", expand=True)
        sc.config(command=lb.yview)

        displayed: list[str] = []

        def _refresh_list(*_args) -> None:
            try:
                q = (query_var.get() or "").strip().lower()
                lb.delete(0, tk.END)
                displayed.clear()
                for item in stations_all:
                    text = str(item or "").strip()
                    if not text:
                        continue
                    if q and q not in text.lower():
                        continue
                    displayed.append(text)
                    lb.insert(tk.END, text)
                info_var.set(f"Dostepne stacje: {len(displayed)} / {len(stations_all)}")
                if displayed:
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(0)
                    lb.activate(0)
            except Exception as e:
                log_event_throttled(
                    "TRADE:station_picker_refresh_exception",
                    3000,
                    "TRADE",
                    "station picker refresh exception",
                    system=system,
                    error=f"{type(e).__name__}: {e}",
                )

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
                log_event_throttled(
                    "WARN",
                    "TRADE_STATION_PICKER_AC_HIDE_FAILED",
                    "Spansh Trade: station autocomplete hide failed",
                    cooldown_sec=60.0,
                    context="spansh.trade.station_picker.ac_hide",
                )
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
                    log_event_throttled(
                        "WARN",
                        "TRADE_STATION_PICKER_FOCUS_RESTORE_FAILED",
                        "Spansh Trade: restore station field focus failed",
                        cooldown_sec=60.0,
                        context="spansh.trade.station_picker.focus_restore",
                    )

        f_btn = tk.Frame(f_top, bg=bg)
        f_btn.pack(fill="x", pady=(10, 0))
        tk.Button(
            f_btn,
            text="Wybierz",
            command=_apply_selection,
            bg=panel_bg,
            fg=fg_main,
            activebackground=fg_main,
            activeforeground=bg,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=4,
        ).pack(side="right")
        tk.Button(
            f_btn,
            text="Anuluj",
            command=_close_picker,
            bg=panel_bg,
            fg=fg_sec,
            activebackground=fg_main,
            activeforeground=bg,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=4,
        ).pack(side="right", padx=(0, 8))

        query_var.trace_add("write", _refresh_list)
        lb.bind("<Double-Button-1>", _apply_selection)
        lb.bind("<Return>", _apply_selection)
        top.bind("<Escape>", lambda _e: _close_picker())

        _refresh_list()
        e_filter.focus_set()
        top.protocol("WM_DELETE_WINDOW", _close_picker)

    def _suggest_system(self, tekst: str):

        """Funkcja podpowiedzi systemow dla AutocompleteController."""

        q = (tekst or "").strip()

        if not q:

            return []



        try:

            return spansh_client.systems_suggest(q)

        except Exception as e:
            log_event_throttled(
                "TRADE:system_autocomplete_exception",
                3000,
                "TRADE",
                "system autocomplete exception",
                query=q,
                error=f"{type(e).__name__}: {e}",
            )
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
            log_event_throttled(
                "spansh_trade:station_autocomplete_hide_on_system_change",
                5000,
                "GUI",
                "trade station autocomplete hide on system change failed",
            )

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
        def _collect(raw_value: str | None) -> None:
            raw = (raw_value or "").strip()
            if not raw:
                return
            if "/" in raw:
                for part in raw.split("/"):
                    _collect(part)
                return
            fallback_values.append(raw)
            seconds = cls._parse_updated_age_seconds(raw)
            if seconds is not None:
                parsed.append((seconds, raw))

        for row in rows:
            _collect(str(row.get("updated_buy_ago") or ""))
            _collect(str(row.get("updated_sell_ago") or ""))
            if not (row.get("updated_buy_ago") or row.get("updated_sell_ago")):
                _collect(str(row.get("updated_ago") or row.get("updated_at") or ""))
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

    @staticmethod
    def _source_status_text(value: object) -> str:
        raw = str(value or "").strip().upper()
        mapping = {
            "ONLINE_LIVE": "online",
            "CACHE_TTL_HIT": "cache",
            "OFFLINE_CACHE_FALLBACK": "offline-fallback",
            "ERROR_NO_DATA": "brak danych",
            "UNKNOWN": "-",
        }
        return mapping.get(raw, raw.lower() if raw else "-")

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
        jump_total = 0
        has_jump_data = False
        for row in rows:
            leg_jumps = self._estimate_trade_leg_jumps(row, jump_range)
            if leg_jumps is None:
                continue
            jump_total += leg_jumps
            has_jump_data = True
        if has_jump_data:
            estimated_jumps = jump_total

        profit_text = common.format_value(profit_value, "cr")
        distance_text = f"{common.format_value(distance_total, 'ly')} ly" if has_distance else "-"
        jumps_text = str(estimated_jumps) if estimated_jumps is not None else "-"
        updated_text = self._updated_range_text(rows)
        first_row = rows[0] if rows else {}
        source_status = self._source_status_text(first_row.get("source_status"))
        confidence = str(first_row.get("confidence") or "-").strip() or "-"
        data_age = str(first_row.get("data_age") or "-").strip() or "-"

        summary = (
            f"{profit_label}: {profit_text} | "
            f"Dystans: {distance_text} | "
            f"Skoki (szac.): {jumps_text} | "
            f"Wiek rynku: {updated_text} | "
            f"Zrodlo: {source_status} | "
            f"Pewnosc: {confidence} | "
            f"Wiek danych: {data_age}"
        )
        self.var_trade_summary.set(summary)

    def _clear_trade_leg_details(self, *, collapse: bool = True) -> None:
        self.var_trade_leg_route.set("Wybierz krok trasy, aby zobaczyc szczegoly towarow.")
        self.var_trade_leg_meta.set(
            "Wiek rynku: - | Cumulative Profit: - | Zrodlo: - | Pewnosc: - | Wiek danych: -"
        )
        tree = getattr(self, "tree_leg_commodities", None)
        if tree is None:
            if collapse:
                self._set_trade_details_collapsed(True)
            return
        try:
            tree.delete(*tree.get_children())
        except Exception:
            if collapse:
                self._set_trade_details_collapsed(True)
            return
        if collapse:
            self._set_trade_details_collapsed(True)

    @staticmethod
    def _extract_primary_commodity_name(row: dict) -> str:
        if not isinstance(row, dict):
            return ""
        for key in ("commodity_primary", "commodity_display", "commodity"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        raw_items = row.get("commodities_raw")
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("name") or "").strip()
                if value:
                    return value
        return ""

    def _build_last_commodity_payload(self, row: dict, *, source: str) -> dict:
        name = self._extract_primary_commodity_name(row)
        if not name:
            return {}
        return {
            "name": name,
            "from_system": str(row.get("from_system") or "").strip(),
            "from_station": str(row.get("from_station") or "").strip(),
            "to_system": str(row.get("to_system") or "").strip(),
            "to_station": str(row.get("to_station") or "").strip(),
            "source": str(source or "").strip(),
            "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }

    def _persist_last_commodity_context(self, row: dict | None, *, source: str) -> None:
        if not isinstance(row, dict):
            return
        payload = self._build_last_commodity_payload(row, source=source)
        if not payload:
            return
        try:
            config.update_last_context(last_commodity=payload)
        except Exception:
            try:
                config.STATE["last_commodity"] = payload
            except Exception:
                log_event_throttled(
                    "spansh_trade:last_commodity_state_fallback",
                    5000,
                    "GUI",
                    "trade persist last commodity state fallback failed",
                )

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
            self._clear_trade_leg_details(collapse=not bool(self._results_rows))
            return

        row = self._results_rows[idx]
        self._persist_last_commodity_context(row, source="spansh.trade.selection")
        self._set_trade_details_collapsed(False)
        from_system = (row.get("from_system") or "-").strip() or "-"
        from_station = (row.get("from_station") or "-").strip() or "-"
        to_system = (row.get("to_system") or "-").strip() or "-"
        to_station = (row.get("to_station") or "-").strip() or "-"
        self.var_trade_leg_route.set(
            f"{from_system} ({from_station}) -> {to_system} ({to_station})"
        )

        updated_buy = (row.get("updated_buy_ago") or "").strip()
        updated_sell = (row.get("updated_sell_ago") or "").strip()
        if updated_buy and updated_sell:
            updated = f"{updated_buy} / {updated_sell}"
        else:
            updated = (row.get("updated_ago") or row.get("updated_at") or "-").strip() or "-"
        cumulative = common.format_value(row.get("cumulative_profit"), "cr")
        source_status = self._source_status_text(row.get("source_status"))
        confidence = str(row.get("confidence") or "-").strip() or "-"
        data_age = str(row.get("data_age") or "-").strip() or "-"
        self.var_trade_leg_meta.set(
            f"Wiek rynku (kupno/sprzedaz): {updated} | "
            f"Cumulative Profit: {cumulative} | "
            f"Zrodlo: {source_status} | "
            f"Pewnosc: {confidence} | "
            f"Wiek danych: {data_age}"
        )

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
        self._reflow_trade_leg_tree_columns()

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
        idx = self._get_primary_selected_internal_index()
        if idx is None:
            self._clear_trade_leg_details(collapse=False)
            return
        self._show_trade_leg_details_by_index(idx)

    def _select_first_result_row(self, *, reveal_details: bool = False) -> None:
        if not self._results_rows:
            self._clear_trade_leg_details(collapse=True)
            return
        widget = self._results_widget
        if widget is None:
            if reveal_details:
                self._show_trade_leg_details_by_index(0)
            else:
                self._clear_trade_leg_details(collapse=True)
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
                    log_event_throttled(
                        "WARN",
                        "TRADE_RESULTS_SELECT_FIRST_FAILED",
                        "Spansh Trade: select first row failed (treeview)",
                        cooldown_sec=60.0,
                        context="spansh.trade.results.select_first.tree",
                    )
        else:
            try:
                widget.selection_clear(0, tk.END)
                widget.selection_set(0)
                widget.activate(0)
                widget.see(0)
            except Exception:
                log_event_throttled(
                    "WARN",
                    "TRADE_RESULTS_SELECT_FIRST_FAILED",
                    "Spansh Trade: select first row failed (listbox)",
                    cooldown_sec=60.0,
                    context="spansh.trade.results.select_first.list",
                )
        if reveal_details:
            self._show_trade_leg_details_by_index(0)
        else:
            self._clear_trade_leg_details(collapse=True)



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
        self._clear_sell_assist()
        self._clear_trade_leg_details(collapse=True)
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



        # Fallback do aktualnej lokalizacji z app_state, jesli pola sa puste

        if not start_system:

            start_system = (getattr(self.app_state, "current_system", "") or "").strip()

        if not start_station and bool(getattr(self.app_state, "is_docked", False)):

            start_station = (getattr(self.app_state, "current_station", "") or "").strip()



        if start_system and start_station:

            self._remember_station(start_system, start_station)



        # Ostateczny fallback do config.STATE (zgodnosc wsteczna)



        if not start_system:

            common.emit_status(

                "ERROR",

                "TRADE_INPUT_MISSING",

                source="spansh.trade",

                ui_target="trade",

            )

            return



        # D3b: dwa tryby wejscia:

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

            log_event_throttled(
                "WARN",
                "TRADE_MAX_HOP_SET_FAILED",
                "Spansh Trade: set max hop failed",
                cooldown_sec=60.0,
                context="spansh.trade.max_hop.set",
            )

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
                        self._clear_sell_assist()
                        common.emit_status(
                            "ERROR",
                            "TRADE_ERROR",
                            text=f"Blad: {worker_error}",
                            source="spansh.trade",
                            ui_target="trade",
                        )
                        return

                    if rows:
                        self._apply_trade_jumps_fallback(rows, max_hop)
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
                        self._update_sell_assist(rows, max_hop)
                        self._persist_last_commodity_context(
                            rows[0] if rows else None,
                            source="spansh.trade.route_found",
                        )
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
                        self._clear_sell_assist()
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

    def _estimate_trade_leg_jumps(self, row: dict, jump_range: float | None) -> int | None:
        raw_jumps = self._to_float(row.get("jumps"))
        if raw_jumps is not None and raw_jumps >= 0:
            return int(round(raw_jumps))
        if jump_range is None or jump_range <= 0:
            return None
        distance_ly = self._to_float(row.get("distance_ly"))
        if distance_ly is None or distance_ly < 0:
            return None
        return int(math.ceil(distance_ly / jump_range))

    def _apply_trade_jumps_fallback(self, rows: list[dict], jump_range: float | None) -> None:
        if not rows:
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            if self._to_float(row.get("jumps")) is not None:
                continue
            computed = self._estimate_trade_leg_jumps(row, jump_range)
            if computed is not None:
                row["jumps"] = computed


