import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import utils
from logic import exomastery
from gui import common
from gui import strings as ui
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class ExomasteryTab(ttk.Frame):
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
        self.var_min_landmark = tk.IntVar(value=3)
        self.var_loop = tk.BooleanVar(value=False)
        self.var_avoid = tk.BooleanVar(value=True)

        self._build_ui()
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        f_sys = ttk.Frame(fr)
        f_sys.pack(fill="x", pady=4)

        ttk.Label(f_sys, text=f"{ui.LABEL_START}:", width=8).pack(side="left")
        self.e_start = ttk.Entry(f_sys, textvariable=self.var_start, width=25)
        self.e_start.pack(side="left", padx=(0, 10))

        ttk.Label(f_sys, text=f"{ui.LABEL_TARGET}:", width=8).pack(side="left")
        self.e_cel = ttk.Entry(f_sys, textvariable=self.var_cel, width=25)
        self.e_cel.pack(side="left")

        self.ac = AutocompleteController(self.root, self.e_start)
        self.ac_c = AutocompleteController(self.root, self.e_cel)

        f_rng = ttk.Frame(fr)
        f_rng.pack(fill="x", pady=4)

        ttk.Label(f_rng, text=ui.LABEL_JUMP_RANGE, width=16).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_range, width=7).pack(side="left", padx=(0, 12))

        f_rm = ttk.Frame(fr)
        f_rm.pack(fill="x", padx=5, pady=2)

        ttk.Label(f_rm, text=ui.LABEL_RADIUS, width=16).pack(side="left")
        self.e_radius = ttk.Entry(f_rm, width=5)
        self.e_radius.insert(0, "50")
        self.e_radius.pack(side="left", padx=(0, 12))

        ttk.Label(f_rm, text=ui.LABEL_MAX_SYSTEMS, width=18).pack(side="left")
        self.e_maxsys = ttk.Entry(f_rm, width=5)
        self.e_maxsys.insert(0, "25")
        self.e_maxsys.pack(side="left")

        f_dist = ttk.Frame(fr)
        f_dist.pack(fill="x", padx=5, pady=5)

        ttk.Label(f_dist, text=ui.LABEL_MAX_DISTANCE, width=18).pack(side="left")
        ttk.Entry(f_dist, textvariable=self.var_max_dist, width=7).pack(side="left", padx=5)

        f_lm = ttk.Frame(fr)
        f_lm.pack(fill="x", padx=5, pady=2)

        ttk.Label(f_lm, text=ui.LABEL_MIN_LANDMARK_VALUE, width=26).pack(side="left")
        ttk.Entry(f_lm, textvariable=self.var_min_landmark, width=7).pack(side="left", padx=5)

        f_chk = ttk.Frame(fr)
        f_chk.pack(fill="x", padx=5, pady=2)

        ttk.Checkbutton(f_chk, text=ui.LABEL_AVOID_THARGOIDS, variable=self.var_avoid).pack(
            side="left", padx=10
        )
        ttk.Checkbutton(f_chk, text=ui.LABEL_LOOP, variable=self.var_loop).pack(side="left", padx=10)

        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        ttk.Button(bf, text=ui.BUTTON_CALCULATE, command=self.run).pack(side="left", padx=5)
        ttk.Button(bf, text=ui.BUTTON_CLEAR, command=self.clear).pack(side="left", padx=5)

        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack()
        self.lst = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_EXOMASTERY)

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac.hide()
        self.ac_c.hide()

    def run(self):
        self.clear()

        start_sys = self.e_start.get().strip()
        if not start_sys:
            start_sys = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.e_cel.get().strip()
        rng = self._resolve_jump_range()
        rad = self.e_radius.get()
        mx = self.var_max_sys.get()
        max_dist = self.var_max_dist.get()
        min_lm = self.var_min_landmark.get()
        loop = self.var_loop.get()
        avoid = self.var_avoid.get()

        args = (start_sys, cel, rng, rad, mx, max_dist, min_lm, loop, avoid)
        route_manager.start_route_thread("exomastery", self._th, args=args, gui_ref=self.root)

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
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="exomastery"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.exomastery",
                notify_overlay=True,
            )
        return fallback

    def _th(self, s, cel, rng, rad, mx, max_dist, min_lm, loop, avoid):
        tr, rows = exomastery.oblicz_exomastery(
            s, cel, rng, rad, mx, max_dist, min_lm, loop, avoid
        )

        if tr:
            route_manager.set_route(tr, "exomastery")
            if config.get("features.tables.spansh_schema_enabled", True) and config.get("features.tables.schema_renderer_enabled", True) and config.get("features.tables.normalized_rows_enabled", True):
                opis = common.render_table_lines("exomastery", rows)
                common.register_active_route_list(
                    self.lst,
                    opis,
                    numerate=False,
                    offset=1,
                    schema_id="exomastery",
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
                source="spansh.exomastery",
                ui_target="rtr",
            )
        else:
            common.emit_status(
            "ERROR",
            "ROUTE_EMPTY",
            text="Brak wyników",
            source="spansh.exomastery",
            ui_target="rtr",
        )

    def clear(self):
        self.lst.delete(0, tk.END)
        self.lbl_status.config(text="Wyczyszczono", foreground="grey")
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

