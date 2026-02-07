import config
import threading
import pandas as pd

from logic import utils
from logic.science_data import load_science_data
from logic.system_value_engine import SystemValueEngine
from logic.exit_summary import ExitSummaryGenerator  
from logic.ship_state import ShipState
from logic.utils.renata_log import log_event_throttled


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

        # --- Konfiguracja runtime (centralny ConfigManager) ---
        self.config = config.config

        # --- Próba załadowania danych naukowych ---
        try:
            science_path = str(config.get("science_data_path", config.SCIENCE_EXCEL_PATH) or config.SCIENCE_EXCEL_PATH)
            exobio_df, carto_df = load_science_data(science_path)
        except Exception as e:
            print("[ERROR] Nie udało się załadować danych naukowych:", e)
            # Fallback: puste DataFrame'y, żeby aplikacja się nie wywalała
            exobio_df, carto_df = pd.DataFrame(), pd.DataFrame()

        # --- System Value Engine (EPIC 1–4) ---
        self.system_value_engine = SystemValueEngine((exobio_df, carto_df))
        try:
            self.system_value_engine.set_current_system(self.current_system)
        except Exception:
            pass

        # --- Exit Summary Generator (EPIC 2–4) ---
        self.exit_summary = ExitSummaryGenerator(self.system_value_engine)

        # --- Ship state (JR-1) ---
        self.ship_state = ShipState()

        # --- Ostatnie wygenerowane summary (EPIC 5) ---
        self.last_exit_summary_text = None

        # --- GUI wstrzyknie tu panel eksploracji (EPIC 5) ---
        self.exploration_panel = None

        # --- Dane modułów (JR-2) ---
        self.modules_data_loaded = False
        self.modules_data = None

        # --- Pozostałe dane gry / nawigacji ---
        self.route = config.STATE.get("trasa", [])
        self.route_index = config.STATE.get("idx", 0)
        self.route_details = config.STATE.get("rtr_data", {})
        self.milestones = config.STATE.get("milestones", [])
        self.inventory = config.STATE.get("inventory", {})

        # True only while MainLoop replays historical Journal lines at startup.
        # Used to suppress misleading live-style TTS during bootstrap.
        self.bootstrap_replay = False

    def set_system(self, system_name):
        if not system_name:
            return
        with self.lock:
            self.current_system = system_name
            config.STATE["sys"] = system_name
            try:
                self.system_value_engine.set_current_system(system_name)
            except Exception:
                pass
        utils.MSG_QUEUE.put(("start_label", system_name))
        log_event_throttled("state.system", 500, "STATE", f"System = {system_name}")

    def set_station(self, station_name):
        if not station_name:
            return
        with self.lock:
            self.current_station = station_name
            config.STATE["station"] = station_name
        log_event_throttled("state.station", 500, "STATE", f"Station = {station_name}")

    def set_docked(self, is_docked: bool):
        """
        Ustawia flagę dokowania na podstawie eventów Docked/Undocked.
        """
        with self.lock:
            self.is_docked = bool(is_docked)
            config.STATE["is_docked"] = self.is_docked
        log_event_throttled("state.docked", 500, "STATE", f"Docked = {self.is_docked}")

    def set_inventory(self, inv_dict):
        with self.lock:
            self.inventory = inv_dict
            config.STATE["inventory"] = dict(inv_dict)


# Globalny stan aplikacji – importowany w innych modułach
app_state = AppState()
