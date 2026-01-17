import tkinter as tk
from tkinter import ttk
import threading
import pyperclip
import config
from logic import neutron
from logic import utils
from gui import common
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class NeutronTab(ttk.Frame):
    def __init__(self, parent, root_window):
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        self.var_start = tk.StringVar()
        self.var_cel = tk.StringVar()
        self.var_range = tk.DoubleVar(value=50.0)
        self.var_eff = tk.DoubleVar(value=0.6)

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

        # Autocomplete (poprawiona sygnatura)
        self.ac_start = AutocompleteController(self.root, self.e_start)
        self.ac_cel = AutocompleteController(self.root, self.e_cel)

        # Range + Efficiency
        f_rng = ttk.Frame(fr)
        f_rng.pack(fill="x", pady=4)

        ttk.Label(f_rng, text="Max range:", width=10).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_range, width=7).pack(side="left", padx=(0, 12))

        ttk.Label(f_rng, text="Eff.:", width=6).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_eff, width=7).pack(side="left")

        # Przyciski
        f_btn = ttk.Frame(fr)
        f_btn.pack(pady=6)

        ttk.Button(f_btn, text="Wyznacz trasę", command=self.run_neutron).pack(side="left", padx=4)
        ttk.Button(f_btn, text="Wyczyść", command=self.clear).pack(side="left", padx=4)
        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack(pady=(4, 2))


        # Lista wyników
        self.lst = common.stworz_liste_trasy(self, title="Neutron Route")

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac_start.hide()
        self.ac_cel.hide()

    def clear(self):
        self.lst.delete(0, tk.END)
        utils.MSG_QUEUE.put(("status_neu", ("Wyczyszczono", "grey")))
        config.STATE["trasa"] = []
        config.STATE["copied_idx"] = None
        config.STATE["copied_sys"] = None

    def run_neutron(self):
        self.clear()

        s = self.var_start.get().strip()
        if not s:
            s = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.var_cel.get().strip()
        rng = self.var_range.get()
        eff = self.var_eff.get()

        args = (s, cel, rng, eff)

        route_manager.start_route_thread("neutron", self._th, args=args, gui_ref=self.root)

    def _th(self, s, cel, rng, eff):
        try:
            tr = neutron.oblicz_spansh(s, cel, rng, eff, self.root)

            if tr:
                route_manager.set_route(tr, "neutron")
                opis = [f"{sys}" for sys in tr]

                nxt = None
                if config.get("auto_clipboard") and len(tr) > 0:
                    nxt = 1 if len(tr) > 1 and tr[0].lower() == s.lower() else 0
                    pyperclip.copy(tr[nxt])

                    config.STATE["copied_idx"] = nxt
                    config.STATE["copied_sys"] = tr[nxt]

                common.wypelnij_liste(self.lst, opis, copied_index=nxt)
                utils.MSG_QUEUE.put(("status_neu", (f"Znaleziono {len(tr)}", "green")))
            else:
                utils.MSG_QUEUE.put(("status_neu", ("Brak wyników", "red")))
        except Exception as e:  # żeby nie uwalić GUI przy wyjątku w wątku
            utils.MSG_QUEUE.put(("status_neu", (f"Błąd: {e}", "red")))

