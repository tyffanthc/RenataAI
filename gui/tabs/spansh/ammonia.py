import tkinter as tk
from tkinter import ttk

from app.state import app_state
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController, edsm_single_system_lookup
from gui.tabs.spansh.planner_base import SpanshPlannerBase
from logic import ammonia


class AmmoniaTab(SpanshPlannerBase):
    def __init__(self, parent, root_window):
        super().__init__(
            parent,
            root_window,
            mode_key="ammonia",
            schema_id="ammonia",
            status_source="spansh.ammonia",
            status_target="amm",
            emit_busy_status=True,
        )

        self.var_start = tk.StringVar()
        self.var_cel = tk.StringVar()
        self.var_range = tk.DoubleVar(value=50.0)
        self.var_radius = tk.StringVar(value="50")
        self.var_max_sys = tk.StringVar(value="25")
        self.var_max_dist = tk.IntVar(value=5000)
        self.var_loop = tk.BooleanVar(value=False)
        self.var_avoid_tharg = tk.BooleanVar(value=True)

        self._build_ui()
        self._setup_range_tracking()

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        f_form = ttk.Frame(fr)
        f_form.pack(fill="x", pady=4)
        layout.configure_form_grid(f_form)

        self.e_start, self.e_cel = layout.add_labeled_pair(
            f_form,
            0,
            ui.LABEL_START,
            self.var_start,
            ui.LABEL_TARGET,
            self.var_cel,
            left_entry_width=layout.ENTRY_W_LONG,
            right_entry_width=layout.ENTRY_W_LONG,
        )

        self.ac = AutocompleteController(
            self.root,
            self.e_start,
            fallback_lookup=edsm_single_system_lookup,
        )
        self.ac_c = AutocompleteController(
            self.root,
            self.e_cel,
            fallback_lookup=edsm_single_system_lookup,
        )

        layout.add_labeled_pair(
            f_form,
            1,
            ui.LABEL_JUMP_RANGE,
            self.var_range,
            ui.LABEL_RADIUS,
            self.var_radius,
        )
        layout.add_labeled_pair(
            f_form,
            2,
            ui.LABEL_MAX_DISTANCE,
            self.var_max_dist,
            ui.LABEL_MAX_SYSTEMS,
            self.var_max_sys,
        )

        f_chk = ttk.Frame(fr)
        f_chk.pack(fill="x", padx=5, pady=2)

        ttk.Checkbutton(
            f_chk, text=ui.LABEL_AVOID_THARGOIDS, variable=self.var_avoid_tharg
        ).pack(side="left", padx=10)
        ttk.Checkbutton(f_chk, text=ui.LABEL_LOOP, variable=self.var_loop).pack(
            side="left", padx=10
        )

        self._build_centered_actions_row(
            fr,
            run_command=self.run_amm,
            clear_command=self.clear_amm,
            status_text="Gotowy",
        )

        if self._use_treeview:
            self.lst_amm = common.stworz_tabele_trasy(fr, title=ui.LIST_TITLE_AMMONIA)
        else:
            self.lst_amm = common.stworz_liste_trasy(fr, title=ui.LIST_TITLE_AMMONIA)
        self._attach_default_results_context_menu(self.lst_amm)

    def run_amm(self):
        if not self._can_start():
            return
        self.clear_amm()

        start_sys = self.e_start.get().strip()
        if not start_sys:
            start_sys = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.e_cel.get().strip()
        jump_range = self._resolve_jump_range()
        radius = self.var_radius.get()
        max_sys = self.var_max_sys.get()
        max_dist = self.var_max_dist.get()
        loop = self.var_loop.get()
        avoid_tharg = self.var_avoid_tharg.get()

        args = (start_sys, cel, jump_range, radius, max_sys, max_dist, loop, avoid_tharg)
        self._start_route_thread(self._th, args)

    def _th(self, s, cel, rng, rad, mx, max_dist, loop, avoid):
        self._execute_route_call(
            ammonia.oblicz_ammonia,
            (
                s,
                cel,
                rng,
                rad,
                mx,
                max_dist,
                loop,
                avoid,
                None,
            ),
            list_widget=self.lst_amm,
        )

    def clear_amm(self):
        self._clear_list_widget(self.lst_amm)
        if getattr(self, "lbl_status", None):
            self.lbl_status.config(text="Wyczyszczono", foreground="grey")
        common.emit_status(
            "INFO",
            "ROUTE_CLEARED",
            source="spansh.ammonia",
            ui_target="amm",
        )
        self._reset_shared_route_state()
