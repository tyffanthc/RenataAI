import config
import threading
import pandas as pd

from logic import utils
from logic.config import RenataConfig
from logic.science_data import load_science_data
from logic.system_value_engine import SystemValueEngine
from logic.exit_summary import ExitSummaryGenerator  
from logic.ship_state import ShipState


class AppState:
    """
    Centralny stan Renaty.
    Trzyma pozycję gracza, ustawienia i dane tras.
    """

    def __init__(self):
        self.lock = threading.Lock()

        # --- Podstawowe dane o stanie gry ---
        self.current_system = config.STATE.get("sys", "Unknown")
        self.current_station = config.STATE.get("station", None)
        # Czy jesteśmy aktualnie zadokowani (runtime'owo)
        self.is_docked = bool(config.STATE.get("is_docked", False))

        # --- Konfiguracja (EPIC 5) ---
        self.config = RenataConfig()

        # --- Próba załadowania danych naukowych ---
        try:
            exobio_df, carto_df = load_science_data("renata_science_data.xlsx")
        except Exception as e:
            print("[ERROR] Nie udało się załadować danych naukowych:", e)
            # Fallback: puste DataFrame'y, żeby aplikacja się nie wywalała
            exobio_df, carto_df = pd.DataFrame(), pd.DataFrame()

        # --- System Value Engine (EPIC 1–4) ---
        self.system_value_engine = SystemValueEngine((exobio_df, carto_df))

        # --- Exit Summary Generator (EPIC 2–4) ---
        self.exit_summary = ExitSummaryGenerator(self.system_value_engine)

        # --- Ship state (JR-1) ---
        self.ship_state = ShipState()

        # --- Ostatnie wygenerowane summary (EPIC 5) ---
        self.last_exit_summary_text = None

        # --- GUI wstrzyknie tu panel eksploracji (EPIC 5) ---
        self.exploration_panel = None

        # --- Pozostałe dane gry / nawigacji ---
        self.route = config.STATE.get("trasa", [])
        self.route_index = config.STATE.get("idx", 0)
        self.route_details = config.STATE.get("rtr_data", {})
        self.milestones = config.STATE.get("milestones", [])
        self.inventory = config.STATE.get("inventory", {})

    def set_system(self, system_name):
        if not system_name:
            return
        with self.lock:
            self.current_system = system_name
            config.STATE["sys"] = system_name
        utils.MSG_QUEUE.put(("start_label", system_name))
        utils.MSG_QUEUE.put(("log", f"[STATE] System = {system_name}"))

    def set_station(self, station_name):
        if not station_name:
            return
        with self.lock:
            self.current_station = station_name
            config.STATE["station"] = station_name
        utils.MSG_QUEUE.put(("log", f"[STATE] Station = {station_name}"))

    def set_docked(self, is_docked: bool):
        """
        Ustawia flagę dokowania na podstawie eventów Docked/Undocked.
        """
        with self.lock:
            self.is_docked = bool(is_docked)
            config.STATE["is_docked"] = self.is_docked
        utils.MSG_QUEUE.put(("log", f"[STATE] Docked = {self.is_docked}"))

    def set_inventory(self, inv_dict):
        with self.lock:
            self.inventory = inv_dict
            config.STATE["inventory"] = dict(inv_dict)


# Globalny stan aplikacji – importowany w innych modułach
app_state = AppState()
