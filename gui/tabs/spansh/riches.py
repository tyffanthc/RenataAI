import tkinter as tk
from tkinter import ttk

from app.state import app_state
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController, edsm_single_system_lookup
from gui.tabs.spansh.planner_base import SpanshPlannerBase
from logic import riches


class RichesTab(SpanshPlannerBase):
    def __init__(self, parent, root_window):
        super().__init__(
            parent,
            root_window,
            mode_key="riches",
            schema_id="riches",
            status_source="spansh.riches",
            status_target="rtr",
            emit_busy_status=True,
        )

        self.var_start = tk.StringVar()
        self.var_cel = tk.StringVar()
        self.var_range = tk.DoubleVar(value=50.0)
        self.var_radius = tk.StringVar(value="50")
        self.var_max_sys = tk.StringVar(value="25")
        self.var_max_dist = tk.IntVar(value=5000)
        self.var_min_scan = tk.IntVar(value=3)
        self.var_loop = tk.BooleanVar(value=False)
        self.var_use_map = tk.BooleanVar(value=True)
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

        self.ac_start = AutocompleteController(
            self.root,
            self.e_start,
            fallback_lookup=edsm_single_system_lookup,
        )
        self.ac_cel = AutocompleteController(
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

        f_extra = ttk.Frame(fr)
        f_extra.pack(fill="x", pady=4)
        layout.configure_form_grid(f_extra)
        layout.add_labeled_entry(
            f_extra,
            0,
            ui.LABEL_MIN_SCAN_VALUE,
            self.var_min_scan,
        )

        f_chk = ttk.Frame(fr)
        f_chk.pack(fill="x", pady=4)

        ttk.Checkbutton(
            f_chk, text=ui.LABEL_AVOID_THARGOIDS, variable=self.var_avoid_tharg
        ).pack(side="left", padx=10)
        ttk.Checkbutton(f_chk, text=ui.LABEL_LOOP, variable=self.var_loop).pack(
            side="left", padx=10
        )
        ttk.Checkbutton(f_chk, text=ui.LABEL_USE_MAP, variable=self.var_use_map).pack(
            side="left", padx=10
        )

        f_btn = ttk.Frame(fr)
        f_btn.pack(pady=6)

        self.btn_run = ttk.Button(f_btn, text=ui.BUTTON_CALCULATE, command=self.run_rtr)
        self.btn_run.pack(side="left", padx=4)
        ttk.Button(f_btn, text=ui.BUTTON_CLEAR, command=self.clear_rtr).pack(side="left", padx=4)

        if self._use_treeview:
            self.lst_rtr = common.stworz_tabele_trasy(self, title=ui.LIST_TITLE_RICHES)
        else:
            self.lst_rtr = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_RICHES)

    def clear_rtr(self):
        self._clear_list_widget(self.lst_rtr)
        common.emit_status(
            "INFO",
            "ROUTE_CLEARED",
            source="spansh.riches",
            ui_target="rtr",
        )

    def run_rtr(self):
        if not self._can_start():
            return
        self.clear_rtr()

        start_sys = self.var_start.get().strip()
        if not start_sys:
            start_sys = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.var_cel.get().strip()
        jump_range = self._resolve_jump_range()
        radius = self.var_radius.get()
        max_sys = self.var_max_sys.get()
        max_dist = self.var_max_dist.get()
        min_scan = self.var_min_scan.get()
        loop = self.var_loop.get()
        use_map = self.var_use_map.get()
        avoid_tharg = self.var_avoid_tharg.get()

        args = (
            start_sys,
            cel,
            jump_range,
            radius,
            max_sys,
            max_dist,
            min_scan,
            loop,
            use_map,
            avoid_tharg,
        )
        self._start_route_thread(self._th_r, args)

    def _th_r(
        self,
        s,
        cel,
        jump_range,
        rad,
        mx,
        max_dist,
        min_scan,
        loop,
        use_map,
        avoid_tharg,
    ):
        self._execute_route_call(
            riches.oblicz_rtr,
            (
                s,
                cel,
                jump_range,
                rad,
                mx,
                max_dist,
                min_scan,
                loop,
                use_map,
                avoid_tharg,
                None,
            ),
            list_widget=self.lst_rtr,
        )
