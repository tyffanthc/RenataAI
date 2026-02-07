import config
import threading
import pandas as pd
from datetime import datetime

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
        self.spansh_milestones: list[str] = []
        self.spansh_milestone_index: int = 0
        self.spansh_milestone_mode: str | None = None
        # In-game route snapshot from NavRoute.json.
        self.nav_route = {
            "endpoint": None,
            "systems": [],
            "updated_at": None,
            "source": None,
        }
        self.inventory = config.STATE.get("inventory", {})

        # True only while MainLoop replays historical Journal lines at startup.
        # Used to suppress misleading live-style TTS during bootstrap.
        self.bootstrap_replay = False
        # True only after first live (non-bootstrap) system event from Journal.
        # Prevents showing stale bootstrap system context as "live" startup state.
        self.has_live_system_event = False

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

    def mark_live_system_event(self) -> None:
        with self.lock:
            self.has_live_system_event = True

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

    def set_spansh_milestones(
        self,
        milestones,
        *,
        mode: str | None = None,
        source: str = "spansh",
    ) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in milestones or []:
            raw = str(value or "").strip()
            if not raw:
                continue
            norm = " ".join(raw.split()).casefold()
            if norm in seen:
                continue
            seen.add(norm)
            normalized.append(raw)

        with self.lock:
            self.spansh_milestones = normalized
            self.spansh_milestone_index = 0
            self.spansh_milestone_mode = mode
            config.STATE["milestones"] = list(normalized)

        # Align active milestone with current system if we already start on a milestone.
        self.update_spansh_milestone_on_system(self.current_system)

        log_event_throttled(
            "state.spansh_milestones",
            1000,
            "STATE",
            f"Milestones loaded: {len(normalized)} mode={mode or '-'} source={source}",
        )

    def clear_spansh_milestones(self, *, source: str = "clear") -> None:
        with self.lock:
            self.spansh_milestones = []
            self.spansh_milestone_index = 0
            self.spansh_milestone_mode = None
            config.STATE["milestones"] = []
        log_event_throttled("state.spansh_milestones", 1000, "STATE", f"Milestones cleared ({source})")

    def get_active_spansh_milestone(self) -> str | None:
        with self.lock:
            if self.spansh_milestone_index < 0:
                return None
            if self.spansh_milestone_index >= len(self.spansh_milestones):
                return None
            return self.spansh_milestones[self.spansh_milestone_index]

    def update_spansh_milestone_on_system(self, system_name: str | None) -> bool:
        """
        Advance active milestone when current system matches current milestone.
        Returns True when index was advanced.
        """
        current = " ".join(str(system_name or "").strip().split()).casefold()
        if not current:
            return False

        advanced = False
        with self.lock:
            while self.spansh_milestone_index < len(self.spansh_milestones):
                milestone = self.spansh_milestones[self.spansh_milestone_index]
                milestone_norm = " ".join(str(milestone).strip().split()).casefold()
                if milestone_norm != current:
                    break
                self.spansh_milestone_index += 1
                advanced = True

        if advanced:
            active = self.get_active_spansh_milestone()
            log_event_throttled(
                "state.spansh_milestones",
                500,
                "STATE",
                f"Milestone reached, next={active or 'END'}",
            )
        return advanced

    def set_nav_route(self, endpoint=None, systems=None, *, source: str = "navroute") -> None:
        systems_list = list(systems or [])
        with self.lock:
            self.nav_route = {
                "endpoint": endpoint if endpoint else (systems_list[-1] if systems_list else None),
                "systems": systems_list,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "source": source,
            }
        log_event_throttled(
            "state.nav_route",
            1000,
            "STATE",
            f"NavRoute loaded: {len(systems_list)} systems endpoint={self.nav_route['endpoint']}",
        )

    def clear_nav_route(self, *, source: str = "navroute_clear") -> None:
        with self.lock:
            self.nav_route = {
                "endpoint": None,
                "systems": [],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "source": source,
            }
        log_event_throttled("state.nav_route", 1000, "STATE", "NavRoute cleared")


# Globalny stan aplikacji – importowany w innych modułach
app_state = AppState()
