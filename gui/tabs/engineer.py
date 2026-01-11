import tkinter as tk
from tkinter import ttk
import config
from logic import engineer

class EngineerTab(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.pack(fill="both", expand=1)
        self._init_ui()

    def _init_ui(self):
        ttk.Label(self, text="Wybierz recepturę:", font=("Arial", 10)).pack(pady=5)
        self.cb_rec = ttk.Combobox(self, values=list(config.RECEPTURY.keys()), width=30)
        self.cb_rec.pack(pady=5)
        if config.RECEPTURY:
            self.cb_rec.current(0)

        ttk.Button(self, text="Sprawdź Braki (Magazyn)", command=self.run_engi).pack(pady=10)

    def run_engi(self):
        engineer.sprawdz_magazyn(self.cb_rec.get(), self.main_app)
