import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import utils
from logic import hmc_route
from gui import common
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class HMCTab(ttk.Frame):
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

        self._build_ui()
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        f_sys = ttk.Frame(fr)
        f_sys.pack(fill="x", pady=4)

        ttk.Label(f_sys, text="Start:", width=8).pack(side="left")
        self.e_start = ttk.Entry(f_sys, textvariable=self.var_start, width=25)
        self.e_start.pack(side="left", padx=(0, 10))

        ttk.Label(f_sys, text="Cel:", width=8).pack(side="left")
        self.e_cel = ttk.Entry(f_sys, textvariable=self.var_cel, width=25)
        self.e_cel.pack(side="left")

        self.ac = AutocompleteController(self.root, self.e_start)
        self.ac_c = AutocompleteController(self.root, self.e_cel)

        f_rng = ttk.Frame(fr)
        f_rng.pack(fill="x", pady=4)

        ttk.Label(f_rng, text="Range:", width=10).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_range, width=7).pack(side="left", padx=(0, 12))
        ttk.Scale(
            f_rng, from_=10, to=100, variable=self.var_range, orient="horizontal"
        ).pack(side="left", fill="x", expand=True, padx=5)

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

        f_dist = ttk.Frame(fr)
        f_dist.pack(fill="x", padx=5, pady=5)

        ttk.Label(f_dist, text="Max DTA (ls):", width=10).pack(side="left")
        ttk.Entry(f_dist, textvariable=self.var_max_dist, width=7).pack(side="left", padx=5)
        ttk.Scale(
            f_dist, from_=100, to=10000, variable=self.var_max_dist, orient="horizontal"
        ).pack(side="left", fill="x", expand=True, padx=5)

        f_chk = ttk.Frame(fr)
        f_chk.pack(fill="x", padx=5, pady=2)

        ttk.Checkbutton(f_chk, text="Avoid Thargoids", variable=self.var_avoid).pack(
            side="left", padx=10
        )
        ttk.Checkbutton(f_chk, text="Loop", variable=self.var_loop).pack(side="left", padx=10)

        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        ttk.Button(bf, text="Calculate", command=self.run).pack(side="left", padx=5)
        ttk.Button(bf, text="Wyczyść", command=self.clear).pack(side="left", padx=5)

        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack()
        self.lst = common.stworz_liste_trasy(self, title="HMC / Rocky Route")

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
        mx = self.e_maxsys.get()
        max_dist = self.var_max_dist.get()
        loop = self.var_loop.get()
        avoid = self.var_avoid.get()

        args = (start_sys, cel, rng, rad, mx, max_dist, loop, avoid)
        route_manager.start_route_thread("hmc", self._th, args=args, gui_ref=self.root)

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
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="hmc"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.hmc",
                notify_overlay=True,
            )
        return fallback

    def _th(self, s, cel, rng, rad, mx, max_dist, loop, avoid):
        tr, det = hmc_route.oblicz_hmc(s, cel, rng, rad, mx, max_dist, loop, avoid)

        if tr:
            route_manager.set_route(tr, "hmc")
            opis = [f"{sys} ({len(det.get(sys, []))} ciał)" for sys in tr]

            common.handle_route_ready_autoclipboard(self, tr, status_target="rtr")
            common.wypelnij_liste(self.lst, opis)
            common.emit_status(
                "OK",
                "ROUTE_FOUND",
                text=f"Znaleziono {len(tr)}",
                source="spansh.hmc",
                ui_target="rtr",
            )
        else:
            common.emit_status(
            "ERROR",
            "ROUTE_EMPTY",
            text="Brak wyników",
            source="spansh.hmc",
            ui_target="rtr",
        )

    def clear(self):
        self.lst.delete(0, tk.END)
        self.lbl_status.config(text="Wyczyszczono", foreground="grey")
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

