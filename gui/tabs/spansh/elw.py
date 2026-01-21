import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import utils
from logic import elw_route
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class ELWTab(ttk.Frame):
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
        self.var_avoid = tk.BooleanVar(value=True)
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

        ttk.Checkbutton(f_chk, text=ui.LABEL_AVOID_THARGOIDS, variable=self.var_avoid).pack(
            side="left", padx=10
        )
        ttk.Checkbutton(f_chk, text=ui.LABEL_LOOP, variable=self.var_loop).pack(
            side="left", padx=10
        )

        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        self.btn_run = ttk.Button(bf, text=ui.BUTTON_CALCULATE, command=self.run)
        self.btn_run.pack(side="left", padx=5)
        ttk.Button(bf, text=ui.BUTTON_CLEAR, command=self.clear).pack(side="left", padx=5)

        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack()
        if self._use_treeview:
            self.lst = common.stworz_tabele_trasy(self, title=ui.LIST_TITLE_ELW)
        else:
            self.lst = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_ELW)

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac.hide()
        self.ac_c.hide()

    def run(self):
        if not self._can_start():
            return
        self.clear()

        start_sys = self.e_start.get().strip()
        if not start_sys:
            start_sys = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.e_cel.get().strip()
        rng = self._resolve_jump_range()
        rad = self.var_radius.get()
        mx = self.var_max_sys.get()
        max_dist = self.var_max_dist.get()
        loop = self.var_loop.get()
        avoid = self.var_avoid.get()

        args = (start_sys, cel, rng, rad, mx, max_dist, loop, avoid)
        self._set_busy(True)
        route_manager.start_route_thread("elw", self._th, args=args, gui_ref=self.root)

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
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="elw"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.elw",
                notify_overlay=True,
            )
        return fallback

    def _th(self, s, cel, rng, rad, mx, max_dist, loop, avoid):
        try:
            tr, rows = elw_route.oblicz_elw(s, cel, rng, rad, mx, max_dist, loop, avoid)

            if tr:
                route_manager.set_route(tr, "elw")
                if config.get("features.tables.spansh_schema_enabled", True) and config.get("features.tables.schema_renderer_enabled", True) and config.get("features.tables.normalized_rows_enabled", True):
                    if self._use_treeview:
                        common.render_table_treeview(self.lst, "elw", rows)
                        common.register_active_route_list(
                            self.lst,
                            [],
                            numerate=False,
                            offset=1,
                            schema_id="elw",
                            rows=rows,
                        )
                    else:
                        opis = common.render_table_lines("elw", rows)
                        common.register_active_route_list(
                            self.lst,
                            opis,
                            numerate=False,
                            offset=1,
                            schema_id="elw",
                            rows=rows,
                        )
                        common.wypelnij_liste(
                            self.lst,
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
                    common.register_active_route_list(self.lst, opis)
                    common.wypelnij_liste(self.lst, opis)
                common.handle_route_ready_autoclipboard(self, tr, status_target="rtr")
                common.emit_status(
                    "OK",
                    "ROUTE_FOUND",
                    text=f"Znaleziono {len(tr)}",
                    source="spansh.elw",
                    ui_target="rtr",
                )
            else:
                common.emit_status(
                    "ERROR",
                    "ROUTE_EMPTY",
                    text="Brak wynikow",
                    source="spansh.elw",
                    ui_target="rtr",
                )
        finally:
            self.root.after(0, lambda: self._set_busy(False))

    def _can_start(self) -> bool:
        if self._busy:
            common.emit_status("WARN", "ROUTE_BUSY", text="Laduje...", source="spansh.elw", ui_target="rtr")
            return False
        if route_manager.is_busy():
            common.emit_status("WARN", "ROUTE_BUSY", text="Inny planner juz liczy.", source="spansh.elw", ui_target="rtr")
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if getattr(self, "btn_run", None):
            self.btn_run.config(state=("disabled" if busy else "normal"))
        if getattr(self, "lbl_status", None):
            self.lbl_status.config(text=("Laduje..." if busy else "Gotowy"))

    def clear(self):
        if isinstance(self.lst, ttk.Treeview):
            self.lst.delete(*self.lst.get_children())
        else:
            self.lst.delete(0, tk.END)
        self.lbl_status.config(text="Wyczyszczono", foreground="grey")
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

