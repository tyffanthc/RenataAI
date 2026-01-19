import tkinter as tk
from tkinter import ttk
from .neutron import NeutronTab
from .riches import RichesTab
from .ammonia import AmmoniaTab
from .elw import ELWTab
from .hmc import HMCTab
from .exomastery import ExomasteryTab
from .trade import TradeTab
from gui import strings as ui


class SpanshTab(ttk.Frame):
    def __init__(self, parent, root_window):
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=1, padx=5, pady=5)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.tab_neutron = NeutronTab(self.nb, self.root)
        self.nb.add(self.tab_neutron, text=ui.TAB_SPANSH_NEUTRON)

        self.tab_riches = RichesTab(self.nb, self.root)
        self.nb.add(self.tab_riches, text=ui.TAB_SPANSH_RICHES)

        self.tab_ammonia = AmmoniaTab(self.nb, self.root)
        self.nb.add(self.tab_ammonia, text=ui.TAB_SPANSH_AMMONIA)

        self.tab_elw = ELWTab(self.nb, self.root)
        self.nb.add(self.tab_elw, text=ui.TAB_SPANSH_ELW)

        self.tab_hmc = HMCTab(self.nb, self.root)
        self.nb.add(self.tab_hmc, text=ui.TAB_SPANSH_HMC)

        self.tab_exo = ExomasteryTab(self.nb, self.root)
        self.nb.add(self.tab_exo, text=ui.TAB_SPANSH_EXO)

        self.tab_trade = TradeTab(self.nb, root_window)
        self.nb.add(self.tab_trade, text=ui.TAB_SPANSH_TRADE)

        self._add_placeholder("Tourist (beta)")
        self._add_placeholder("Fleet Carrier (beta)")
        self._add_placeholder("Colonisation (beta)")
        self._add_placeholder("Galaxy (later)")

    def _add_placeholder(self, title):
        fr = ttk.Frame(self.nb)
        ttk.Label(fr, text="Ten tryb dodamy w kolejnym etapie.", font=("Arial", 12)).pack(pady=40)
        self.nb.add(fr, text=title)

    def update_start_label(self, text):
        for t in [self.tab_neutron, self.tab_riches, self.tab_ammonia,
                  self.tab_elw, self.tab_hmc, self.tab_exo]:
            t.var_start.set(text)

    def update_jump_range(self, value):
        for t in [
            self.tab_neutron,
            self.tab_riches,
            self.tab_ammonia,
            self.tab_elw,
            self.tab_hmc,
            self.tab_exo,
            self.tab_trade,
        ]:
            if hasattr(t, "apply_jump_range_from_ship"):
                try:
                    t.apply_jump_range_from_ship(value)
                except Exception:
                    pass

    def _on_tab_changed(self, _event):
        self.hide_suggestions()

    def hide_suggestions(self):
        for t in [self.tab_neutron, self.tab_riches, self.tab_ammonia,
                  self.tab_elw, self.tab_hmc, self.tab_exo]:
            t.hide_suggestions()
        self.tab_trade.hide_suggestions()
