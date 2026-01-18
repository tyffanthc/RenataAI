import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import utils, ammonia
from gui import common
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
        self.var_max_dist = tk.IntVar(value=5000)
        self.var_loop = tk.BooleanVar(value=False)
        self.var_avoid_tharg = tk.BooleanVar(value=True)

        self._build_ui()
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        # Start / Cel
        f_sys = ttk.Frame(fr)
        f_sys.pack(fill="x", pady=4)

        ttk.Label(f_sys, text="Start:", width=8).pack(side="left")
        self.e_start = ttk.Entry(f_sys, textvariable=self.var_start, width=25)
        self.e_start.pack(side="left", padx=(0, 10))

        ttk.Label(f_sys, text="Cel:", width=8).pack(side="left")
        self.e_cel = ttk.Entry(f_sys, textvariable=self.var_cel, width=25)
        self.e_cel.pack(side="left")

        # Autocomplete poprawione
        self.ac = AutocompleteController(self.root, self.e_start)
        self.ac_c = AutocompleteController(self.root, self.e_cel)

        # Range
        f_rng = ttk.Frame(fr)
        f_rng.pack(fill="x", pady=4)

        ttk.Label(f_rng, text="Range:", width=10).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_range, width=7).pack(side="left", padx=(0, 12))
        ttk.Scale(
            f_rng, from_=10, to=100, variable=self.var_range, orient="horizontal"
        ).pack(side="left", fill="x", expand=True, padx=5)

        # Radius + Max Sys
        f_rm = ttk.Frame(fr)
        f_rm.pack(fill="x", padx=5, pady=2)

        ttk.Label(f_rm, text="Radius (LY):", width=10).pack(side="left")
        self.e_radius = ttk.Entry(f_rm, width=5)
        self.e_radius.insert(0, "50")
        self.e_radius.pack(side="left", padx=(0, 12))

        ttk.Label(f_rm, text="Max Sys:", width=8).pack(side="left")
        self.e_maxsys = ttk.Entry(f_rm, width=5)
        self.e_maxsys.insert(0, "25")
        self.e_maxsys.pack(side="left")

        # Max dist + loop + avoid thargoids
        f_md = ttk.Frame(fr)
        f_md.pack(fill="x", padx=5, pady=2)

        ttk.Label(f_md, text="Max DTA (ls):", width=10).pack(side="left")
        ttk.Entry(f_md, textvariable=self.var_max_dist, width=7).pack(side="left", padx=(0, 12))
        ttk.Scale(
            f_md, from_=100, to=10000, variable=self.var_max_dist, orient="horizontal"
        ).pack(side="left", fill="x", expand=True, padx=5)

        f_chk = ttk.Frame(fr)
        f_chk.pack(fill="x", padx=5, pady=2)

        ttk.Checkbutton(f_chk, text="Loop", variable=self.var_loop).pack(side="left", padx=5)
        ttk.Checkbutton(f_chk, text="Avoid Thargoids", variable=self.var_avoid_tharg).pack(
            side="left", padx=5
        )

        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        ttk.Button(bf, text="Wyznacz Ammonia", command=self.run_amm).pack(side="left", padx=5)
        ttk.Button(bf, text="Wyczyść", command=self.clear_amm).pack(side="left", padx=5)

        self.lst_amm = common.stworz_liste_trasy(self, title="Ammonia Route")

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac.hide()
        self.ac_c.hide()

    def run_amm(self):
        self.clear_amm()

        start_sys = self.e_start.get().strip()
        if not start_sys:
            start_sys = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.e_cel.get().strip()
        jump_range = self._resolve_jump_range()
        radius = self.e_radius.get()
        max_sys = self.e_maxsys.get()
        max_dist = self.var_max_dist.get()
        loop = self.var_loop.get()
        avoid_tharg = self.var_avoid_tharg.get()

        args = (start_sys, cel, jump_range, radius, max_sys, max_dist, loop, avoid_tharg)
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
        tr, det = ammonia.oblicz_ammonia(s, cel, rng, rad, mx, max_dist, loop, avoid, None)

        if tr:
            route_manager.set_route(tr, "ammonia")
            opis = [f"{sys} ({len(det.get(sys, []))} ciał)" for sys in tr]

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
            text="Brak wyników",
            source="spansh.ammonia",
            ui_target="amm",
        )

    def clear_amm(self):
        self.lst_amm.delete(0, tk.END)
        common.emit_status(
            "INFO",
            "ROUTE_CLEARED",
            source="spansh.ammonia",
            ui_target="amm",
        )
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

