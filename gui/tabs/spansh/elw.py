import tkinter as tk
from tkinter import ttk
import threading
import pyperclip
import config
from logic import utils
from logic import elw_route
from gui import common
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

        self._build_ui()

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

        ttk.Label(f_chk, text="", width=10).pack(side="left")
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
        self.lst = common.stworz_liste_trasy(self, title="ELW Route")

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
        rng = self.var_range.get()
        rad = self.e_radius.get()
        mx = self.e_maxsys.get()
        max_dist = self.var_max_dist.get()
        loop = self.var_loop.get()
        avoid = self.var_avoid.get()

        args = (start_sys, cel, rng, rad, mx, max_dist, loop, avoid)
        route_manager.start_route_thread("elw", self._th, args=args, gui_ref=self.root)

    def _th(self, s, cel, rng, rad, mx, max_dist, loop, avoid):
        tr, det = elw_route.oblicz_elw(s, cel, rng, rad, mx, max_dist, loop, avoid)

        if tr:
            route_manager.set_route(tr, "elw")
            opis = [f"{sys} ({len(det.get(sys, []))} ciał)" for sys in tr]

            nxt = None
            if config.get("auto_clipboard") and len(tr) > 0:
                nxt = 1 if len(tr) > 1 and tr[0].lower() == s.lower() else 0
                pyperclip.copy(tr[nxt])

                config.STATE["copied_idx"] = nxt
                config.STATE["copied_sys"] = tr[nxt]

            common.wypelnij_liste(self.lst, opis, copied_index=nxt)
            utils.MSG_QUEUE.put(("status_rtr", (f"Znaleziono {len(tr)}", "green")))
        else:
            utils.MSG_QUEUE.put(("status_rtr", ("Brak wyników", "red")))

    def clear(self):
        self.lst.delete(0, tk.END)
        self.lbl_status.config(text="Wyczyszczono", foreground="grey")
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

