import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import utils, ammonia
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class AmmoniaTab(ttk.Frame):
    def __init__(self, parent, root_window):
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        self.var_start = tk.StringVar()
        self.var_cel = tk.StringVar()
        self.var_range = tk.DoubleVar(value=50.0)
        self.var_radius = tk.StringVar(value="50")
        self.var_max_sys = tk.StringVar(value="25")
        self.var_max_dist = tk.IntVar(value=5000)
        self.var_loop = tk.BooleanVar(value=False)
        self.var_avoid_tharg = tk.BooleanVar(value=True)
        self._busy = False

        self._use_treeview = bool(config.get("features.tables.treeview_enabled", False)) and bool(
            config.get("features.tables.spansh_schema_enabled", True)
        ) and bool(config.get("features.tables.schema_renderer_enabled", True)) and bool(
            config.get("features.tables.normalized_rows_enabled", True)
        )

        self._build_ui()
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

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

        # Autocomplete poprawione
        self.ac = AutocompleteController(self.root, self.e_start)
        self.ac_c = AutocompleteController(self.root, self.e_cel)

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

        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        self.btn_run = ttk.Button(bf, text=ui.BUTTON_CALCULATE, command=self.run_amm)
        self.btn_run.pack(side="left", padx=5)
        ttk.Button(bf, text=ui.BUTTON_CLEAR, command=self.clear_amm).pack(side="left", padx=5)
        if self._use_treeview:
            self.lst_amm = common.stworz_tabele_trasy(self, title=ui.LIST_TITLE_AMMONIA)
        else:
            self.lst_amm = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_AMMONIA)

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac.hide()
        self.ac_c.hide()

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
        self._set_busy(True)
        route_manager.start_route_thread("ammonia", self._th, args=args, gui_ref=self.root)

    def apply_jump_range_from_ship(self, value: float | None) -> None:
        if not config.get("planner_auto_use_ship_jump_range", True):
            return
        if self._range_user_overridden:
            return
        if value is None:
            return
        self._set_range_value(value)

    def _on_range_changed(self, *_args) -> None:
        if self._range_updating:
            return
        if not config.get("planner_allow_manual_range_override", True):
            return
        self._range_user_overridden = True

    def _set_range_value(self, value: float) -> None:
        try:
            self._range_updating = True
            self.var_range.set(float(value))
        except Exception:
            pass
        finally:
            self._range_updating = False

    def _resolve_jump_range(self) -> float:
        if not config.get("planner_auto_use_ship_jump_range", True):
            return float(self.var_range.get())
        if self._range_user_overridden:
            return float(self.var_range.get())

        jr = getattr(app_state.ship_state, "jump_range_current_ly", None)
        if jr is not None:
            self._set_range_value(jr)
            return float(jr)

        fallback = config.get("planner_fallback_range_ly", 30.0)
        try:
            fallback = float(fallback)
        except Exception:
            fallback = 30.0
        self._set_range_value(fallback)
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="ammonia"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.ammonia",
                notify_overlay=True,
            )
        return fallback

    def _th(self, s, cel, rng, rad, mx, max_dist, loop, avoid):
        try:
            tr, rows = ammonia.oblicz_ammonia(s, cel, rng, rad, mx, max_dist, loop, avoid, None)

            if tr:
                route_manager.set_route(tr, "ammonia")
                if config.get("features.tables.spansh_schema_enabled", True) and config.get("features.tables.schema_renderer_enabled", True) and config.get("features.tables.normalized_rows_enabled", True):
                    if self._use_treeview:
                        common.render_table_treeview(self.lst_amm, "ammonia", rows)
                        common.register_active_route_list(
                            self.lst_amm,
                            [],
                            numerate=False,
                            offset=1,
                            schema_id="ammonia",
                            rows=rows,
                        )
                    else:
                        opis = common.render_table_lines("ammonia", rows)
                        common.register_active_route_list(
                            self.lst_amm,
                            opis,
                            numerate=False,
                            offset=1,
                            schema_id="ammonia",
                            rows=rows,
                        )
                        common.wypelnij_liste(
                            self.lst_amm,
                            opis,
                            numerate=False,
                            show_copied_suffix=False,
                        )
                else:
                    counts = {}
                    for row in rows:
                        sys_name = row.get("system_name")
                        if sys_name:
                            counts[sys_name] = counts.get(sys_name, 0) + 1
                    opis = [f"{sys} ({counts.get(sys, 0)} cial)" for sys in tr]
                    common.register_active_route_list(self.lst_amm, opis)
                    common.wypelnij_liste(self.lst_amm, opis)
                common.handle_route_ready_autoclipboard(self, tr, status_target="amm")
                common.emit_status(
                    "OK",
                    "ROUTE_FOUND",
                    text=f"Znaleziono {len(tr)}",
                    source="spansh.ammonia",
                    ui_target="amm",
                )
            else:
                common.emit_status(
                    "ERROR",
                    "ROUTE_EMPTY",
                    text="Brak wynikow",
                    source="spansh.ammonia",
                    ui_target="amm",
                )
        finally:
            self.root.after(0, lambda: self._set_busy(False))

    def _can_start(self) -> bool:
        if self._busy:
            common.emit_status("WARN", "ROUTE_BUSY", text="Laduje...", source="spansh.ammonia", ui_target="amm")
            return False
        if route_manager.is_busy():
            common.emit_status("WARN", "ROUTE_BUSY", text="Inny planner juz liczy.", source="spansh.ammonia", ui_target="amm")
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            common.emit_status("INFO", "ROUTE_BUSY", text="Laduje...", source="spansh.ammonia", ui_target="amm")
        if getattr(self, "btn_run", None):
            self.btn_run.config(state=("disabled" if busy else "normal"))

    def clear_amm(self):
        if isinstance(self.lst_amm, ttk.Treeview):
            self.lst_amm.delete(*self.lst_amm.get_children())
        else:
            self.lst_amm.delete(0, tk.END)
        common.emit_status(
            "INFO",
            "ROUTE_CLEARED",
            source="spansh.ammonia",
            ui_target="amm",
        )
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

