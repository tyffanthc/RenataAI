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
import config


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

        tab_defs = [
            {
                "title": ui.TAB_SPANSH_TOURIST,
                "flag_key": "features.ui.tabs.tourist_enabled",
                "builder_real": None,
            },
            {
                "title": ui.TAB_SPANSH_FLEET,
                "flag_key": "features.ui.tabs.fleet_carrier_enabled",
                "builder_real": None,
            },
            {
                "title": ui.TAB_SPANSH_COLONISATION,
                "flag_key": "features.ui.tabs.colonisation_enabled",
                "builder_real": None,
            },
            {
                "title": ui.TAB_SPANSH_GALAXY,
                "flag_key": "features.ui.tabs.galaxy_enabled",
                "builder_real": None,
            },
        ]
        for tab_def in tab_defs:
            self._add_optional_tab(tab_def)

    def _add_placeholder(self, title):
        fr = ttk.Frame(self.nb)
        ttk.Label(fr, text=ui.PLACEHOLDER_TITLE, font=("Arial", 14, "bold")).pack(pady=(40, 8))
        ttk.Label(fr, text=ui.PLACEHOLDER_LINE_1, font=("Arial", 11)).pack()
        ttk.Label(fr, text=ui.PLACEHOLDER_LINE_2, font=("Arial", 11)).pack(pady=(4, 0))
        self.nb.add(fr, text=title)

    def _add_enabled_placeholder(self, title: str) -> None:
        fr = ttk.Frame(self.nb)
        ttk.Label(fr, text=ui.PLACEHOLDER_ENABLED_TITLE, font=("Arial", 14, "bold")).pack(pady=(40, 8))
        ttk.Label(fr, text=ui.PLACEHOLDER_ENABLED_LINE_1, font=("Arial", 11)).pack()
        ttk.Label(fr, text=ui.PLACEHOLDER_ENABLED_LINE_2, font=("Arial", 11)).pack(pady=(4, 0))
        self.nb.add(fr, text=title)

    def _add_optional_tab(self, tab_def: dict) -> None:
        title = tab_def.get("title")
        flag_key = tab_def.get("flag_key")
        builder_real = tab_def.get("builder_real")
        if config.get(flag_key, False):
            if builder_real is not None:
                builder_real()
            else:
                self._add_enabled_placeholder(title)
        else:
            self._add_placeholder(title)

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
