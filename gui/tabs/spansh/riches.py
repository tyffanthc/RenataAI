import tkinter as tk
from tkinter import ttk
import threading
import pyperclip
import config
from logic import utils, riches
from gui import common
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

        self._build_ui()

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
        self.ac_start = AutocompleteController(self.root, self.e_start)
        self.ac_cel = AutocompleteController(self.root, self.e_cel)

        # Range slider
        f_rng = ttk.Frame(fr)
        f_rng.pack(fill="x", pady=4)

        ttk.Label(f_rng, text="Range:", width=10).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_range, width=7).pack(side="left", padx=(0, 12))
        ttk.Scale(
            f_rng, from_=10, to=100, variable=self.var_range, orient="horizontal"
        ).pack(side="left", fill="x", expand=True, padx=5)

        # Radius + Max Sys
        f_rm = ttk.Frame(fr)
        f_rm.pack(fill="x", pady=4)

        ttk.Label(f_rm, text="Radius:", width=10).pack(side="left")
        ttk.Entry(f_rm, textvariable=self.var_radius, width=7).pack(side="left", padx=(0, 12))

        ttk.Label(f_rm, text="Max Sys:", width=10).pack(side="left")
        ttk.Entry(f_rm, textvariable=self.var_max_sys, width=7).pack(side="left")

        # Max Dist + Min Scan
        f_dm = ttk.Frame(fr)
        f_dm.pack(fill="x", pady=4)

        ttk.Label(f_dm, text="Max Dist (ls):", width=12).pack(side="left")
        ttk.Entry(f_dm, textvariable=self.var_max_dist, width=7).pack(side="left", padx=(0, 12))

        ttk.Label(f_dm, text="Min scans:", width=10).pack(side="left")
        ttk.Entry(f_dm, textvariable=self.var_min_scan, width=7).pack(side="left")

        # Checkboxy
        f_chk = ttk.Frame(fr)
        f_chk.pack(fill="x", pady=4)

        ttk.Checkbutton(f_chk, text="Loop", variable=self.var_loop).pack(side="left")
        ttk.Checkbutton(f_chk, text="Use Map", variable=self.var_use_map).pack(side="left", padx=10)
        ttk.Checkbutton(f_chk, text="Avoid Thargoids", variable=self.var_avoid_tharg).pack(
            side="left", padx=10
        )

        # Przyciski
        f_btn = ttk.Frame(fr)
        f_btn.pack(pady=6)

        ttk.Button(f_btn, text="Wyznacz Riches", command=self.run_rtr).pack(side="left", padx=4)
        ttk.Button(f_btn, text="Wyczyść", command=self.clear_rtr).pack(side="left", padx=4)

        # Lista
        self.lst_rtr = common.stworz_liste_trasy(self, title="Riches Route")

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac_start.hide()
        self.ac_cel.hide()

    def clear_rtr(self):
        self.lst_rtr.delete(0, tk.END)
        utils.MSG_QUEUE.put(("status_rtr", ("Wyczyszczono", "grey")))

    def run_rtr(self):
        self.clear_rtr()

        start_sys = self.var_start.get().strip()
        if not start_sys:
            start_sys = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.var_cel.get().strip()
        jump_range = self.var_range.get()
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

        route_manager.start_route_thread("riches", self._th_r, args=args, gui_ref=self.root)

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
        tr, det = riches.oblicz_rtr(
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
            opis = [f"{sys} ({len(det.get(sys, []))} ciał)" for sys in tr]

            nxt = None
            if config.SETTINGS.get("COPY") and len(tr) > 0:
                nxt = 1 if len(tr) > 1 and tr[0].lower() == s.lower() else 0
                pyperclip.copy(tr[nxt])
                config.STATE["copied_idx"] = nxt
                config.STATE["copied_sys"] = tr[nxt]

            common.wypelnij_liste(self.lst_rtr, opis, copied_index=nxt)
            utils.MSG_QUEUE.put(("status_rtr", (f"Znaleziono {len(tr)}", "green")))
        else:
            utils.MSG_QUEUE.put(("status_rtr", ("Brak wyników", "red")))
