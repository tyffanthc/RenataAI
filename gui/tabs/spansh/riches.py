import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import utils, riches
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class RichesTab(ttk.Frame):
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
        self.var_min_scan = tk.IntVar(value=3)
        self.var_loop = tk.BooleanVar(value=False)
        self.var_use_map = tk.BooleanVar(value=True)
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
        self.ac_start = AutocompleteController(self.root, self.e_start)
        self.ac_cel = AutocompleteController(self.root, self.e_cel)

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

        # Checkboxy
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

        # Przyciski
        f_btn = ttk.Frame(fr)
        f_btn.pack(pady=6)

        self.btn_run = ttk.Button(f_btn, text=ui.BUTTON_CALCULATE, command=self.run_rtr)
        self.btn_run.pack(side="left", padx=4)
        ttk.Button(f_btn, text=ui.BUTTON_CLEAR, command=self.clear_rtr).pack(side="left", padx=4)

        # Lista
        if self._use_treeview:
            self.lst_rtr = common.stworz_tabele_trasy(self, title=ui.LIST_TITLE_RICHES)
        else:
            self.lst_rtr = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_RICHES)

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac_start.hide()
        self.ac_cel.hide()

    def clear_rtr(self):
        if isinstance(self.lst_rtr, ttk.Treeview):
            self.lst_rtr.delete(*self.lst_rtr.get_children())
        else:
            self.lst_rtr.delete(0, tk.END)
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

        self._set_busy(True)
        route_manager.start_route_thread("riches", self._th_r, args=args, gui_ref=self.root)

    def _can_start(self) -> bool:
        if self._busy:
            common.emit_status("WARN", "ROUTE_BUSY", text="Laduje...", source="spansh.riches", ui_target="rtr")
            return False
        if route_manager.is_busy():
            common.emit_status("WARN", "ROUTE_BUSY", text="Inny planner juz liczy.", source="spansh.riches", ui_target="rtr")
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            common.emit_status("INFO", "ROUTE_BUSY", text="Laduje...", source="spansh.riches", ui_target="rtr")
        if getattr(self, "btn_run", None):
            self.btn_run.config(state=("disabled" if busy else "normal"))

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
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="riches"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.riches",
                notify_overlay=True,
            )
        return fallback

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
        try:
            tr, rows = riches.oblicz_rtr(
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
            )

            if tr:
                route_manager.set_route(tr, "riches")
                if config.get("features.tables.spansh_schema_enabled", True) and config.get("features.tables.schema_renderer_enabled", True) and config.get("features.tables.normalized_rows_enabled", True):
                    if self._use_treeview:
                        common.render_table_treeview(self.lst_rtr, "riches", rows)
                        common.register_active_route_list(
                            self.lst_rtr,
                            [],
                            numerate=False,
                            offset=1,
                            schema_id="riches",
                            rows=rows,
                        )
                    else:
                        opis = common.render_table_lines("riches", rows)
                        common.register_active_route_list(
                            self.lst_rtr,
                            opis,
                            numerate=False,
                            offset=1,
                            schema_id="riches",
                            rows=rows,
                        )
                        common.wypelnij_liste(
                            self.lst_rtr,
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
                    common.register_active_route_list(self.lst_rtr, opis)
                    common.wypelnij_liste(self.lst_rtr, opis)
                common.handle_route_ready_autoclipboard(self, tr, status_target="rtr")
                common.emit_status(
                    "OK",
                    "ROUTE_FOUND",
                    text=f"Znaleziono {len(tr)}",
                    source="spansh.riches",
                    ui_target="rtr",
                )
            else:
                common.emit_status(
                    "ERROR",
                    "ROUTE_EMPTY",
                    text="Brak wynikow",
                    source="spansh.riches",
                    ui_target="rtr",
                )
        finally:
            self.root.after(0, lambda: self._set_busy(False))

