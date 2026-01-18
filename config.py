from __future__ import annotations

import json
import os
from typing import Any, Dict

# --- ŚCIEŻKI / PLIKI ---------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")


def _default_log_dir() -> str:
    """
    Domyślna ścieżka do Journali Elite Dangerous.
    Bez szycia na sztywno 'C:\\Users\\Patryk', tylko z HOME.
    """
    home = os.path.expanduser("~")
    return os.path.join(
        home,
        "Saved Games",
        "Frontier Developments",
        "Elite Dangerous",
    )


# --- DOMYŚLNE PROGI DLA MAKLERA PRO (JACKPOT) -------------------------------

DEFAULT_JACKPOT_THRESHOLDS: Dict[str, int] = {
    "Gold": 7500,
    "Silver": 4000,
    "Platinum": 20000,
    "Palladium": 9000,
    "Tritium": 20000,
    "Agronomic Treatment": 1000,
}

# --- DOMYŚLNE USTAWIENIA (JSON) ---------------------------------------------

DEFAULT_SETTINGS: Dict[str, Any] = {
    # ŚCIEŻKI
    "log_dir": _default_log_dir(),

    # UI / język / motyw
    "language": "pl",
    "theme": "dark",

    # GŁOS / DŹWIĘK
    "voice_enabled": True,            # globalny TTS
    "landing_pad_speech": True,       # komunikaty do lądowania
    "route_progress_speech": True,    # 25/50/75% itp.

    # SCHOWEK / AUTO-COPY
    "auto_clipboard": True,           # auto-schowek (route)

    # SPANSH / SIEĆ
    "spansh_timeout": 20,
    "spansh_retries": 3,

    # UI / zachowanie
    "use_system_theme": True,
    "confirm_exit": True,
    "auto_detect_logs": True,

    # OSTRZEŻENIA I ASYSTENCI
    "fuel_warning": True,             # niski poziom paliwa
    "high_g_warning": True,           # wysokie g planety (future)
    "fuel_warning_threshold_pct": 15, # próg ostrzeżenia rezerwy paliwa (proc.)
    "fss_assistant": True,            # progi FSS
    "high_value_planets": True,       # ELW / WW / terraformowalne HMC
    "bio_assistant": True,            # 3+ sygnały biologiczne
    "trade_jackpot_speech": True,     # Makler PRO (jackpoty)
    "smuggler_alert": True,           # nielegalny ładunek

    # FUTURE / front-end
    "mining_accountant": False,
    "bounty_hunter": False,
    "preflight_limpets": True,
    "fdff_notifications": True,
    "read_system_after_jump": True,

    # MODULES DATA (JR-2)
    "modules_data_enabled": True,
    "modules_data_path": "renata_modules_data.json",
    "modules_data_autogen_enabled": True,
    "modules_data_debug": False,
    "modules_data_sources": {
        "fsd_url": "https://raw.githubusercontent.com/EDCD/coriolis-data/master/modules/standard/frame_shift_drive.json",
        "booster_url": "https://raw.githubusercontent.com/EDCD/coriolis-data/master/modules/internal/guardian_fsd_booster.json",
        "fallback_urls": [
            "https://raw.githubusercontent.com/EDCD/coriolis-data/master/dist/modules.json",
            "https://raw.githubusercontent.com/EDCD/coriolis-data/master/dist/modules.json.gz",
        ],
    },

    # SHIP STATE (JR)
    "ship_state_enabled": True,
    "ship_state_use_status_json": True,
    "ship_state_use_cargo_json": True,
    "ship_state_debug": False,

    # FIT RESOLVER (JR-3)
    "fit_resolver_enabled": True,
    "fit_resolver_debug": False,
    "fit_resolver_fail_on_missing": False,

    # JUMP RANGE ENGINE (JR-4)
    "jump_range_engine_enabled": True,
    "jump_range_engine_debug": False,
    "jump_range_rounding": 2,
    "jump_range_include_reservoir_mass": True,
    "jump_range_compute_on": "both",
    "jump_range_engineering_enabled": True,
    "jump_range_engineering_debug": False,
    "jump_range_validate_enabled": False,
    "jump_range_validate_debug": False,
    "jump_range_validate_tolerance_ly": 0.05,
    "jump_range_validate_log_only": True,

    # PLANNERS (JR-6)
    "planner_auto_use_ship_jump_range": True,
    "planner_allow_manual_range_override": True,
    "planner_fallback_range_ly": 30.0,

    # UI (JR-7)
    "ui_show_jump_range": True,
    "ui_jump_range_location": "both",
    "ui_jump_range_show_limit": True,
    "ui_jump_range_debug_details": False,

    # DEBUG
    "debug_autocomplete": False,
    "debug_cache": False,
    "debug_dedup": False,

    # PROGI DLA MAKLERA PRO (backend only – ale też lecą do JSONa)
    "jackpot_thresholds": DEFAULT_JACKPOT_THRESHOLDS,
}


class ConfigManager:
    """
    Centralny manager konfiguracji.
    Trzyma ustawienia w pamięci + w pliku JSON (user_settings.json).
    """

    def __init__(self, settings_path: str | None = None) -> None:
        self.settings_path = settings_path or SETTINGS_FILE
        self._settings: Dict[str, Any] = DEFAULT_SETTINGS.copy()
        self._load()

    # --- I/O JSON -----------------------------------------------------------

    def _load(self) -> None:
        """
        Próbuje wczytać user_settings.json.
        Jeśli plik nie istnieje lub jest uszkodzony – zapisuje domyślne.
        """
        if not os.path.exists(self.settings_path):
            self._settings = DEFAULT_SETTINGS.copy()
            self._write_file()
            return

        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            # uszkodzony JSON – nadpisujemy domyślnym
            self._settings = DEFAULT_SETTINGS.copy()
            self._write_file()
            return

        if not isinstance(data, dict):
            self._settings = DEFAULT_SETTINGS.copy()
            self._write_file()
            return

        # merge: wszystko co znamy z DEFAULT_SETTINGS + nadpisane z pliku
        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)
        self._settings = merged

    def _write_file(self) -> None:
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=4, ensure_ascii=False)

    # --- API PUBLICZNE ------------------------------------------------------

    def save(self, new_data: Dict[str, Any]) -> None:
        """
        Nadpisuje ustawienia i zrzuca je do pliku JSON.
        new_data – słownik z kluczami takimi jak w DEFAULT_SETTINGS.
        """
        if not isinstance(new_data, dict):
            raise ValueError("ConfigManager.save() expects a dict")

        updated = self._settings.copy()
        for key, value in new_data.items():
            updated[key] = value

        self._settings = updated
        self._write_file()

    def get(self, key: str, default: Any | None = None) -> Any:
        """
        Zwraca wartość ustawienia.
        Jeśli nie ma w runtime, próbuje z DEFAULT_SETTINGS, potem default.
        """
        if default is None:
            default = DEFAULT_SETTINGS.get(key)
        return self._settings.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        """
        Całe ustawienia jako dict – np. dla SettingsTab.
        """
        return self._settings.copy()

    @property
    def log_dir(self) -> str:
        """Wygodny alias na katalog Journal – preferowany sposób dostępu."""
        return self.get("log_dir", _default_log_dir())

    @property
    def LOG_DIR(self) -> str:
        """Alias kompatybilny ze starym kodem (UPPERCASE)."""
        return self.log_dir


# Globalna instancja używana w całej aplikacji:
config = ConfigManager()

# --- Funkcje pomocnicze dla starego stylu importu -------------------------

def get(key, default=None):
    """
    Umożliwia użycie:
        import config
        config.get("log_dir")
    pod spodem deleguje do instancji ConfigManagera.
    """
    return config.get(key, default)


def save(new_data: dict) -> None:
    """
    Umożliwia użycie:
        import config
        config.save({...})
    """
    return config.save(new_data)


# --- POZOSTAŁE STARE RZECZY Z CONFIG.PY (BACKEND STATE) --------------------
# Zostawiamy, żeby nie rozwalić innych modułów, które tego używają.

DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

STATE = {
    "sys": "Nieznany",
    "trasa": [],
    "rtr_data": {},
    "idx": 0,
    "receptura": None,
    "inventory": {},
    "ciala_tot": 0,
    "ciala_odk": 0,
    "milestones": []
}

RECEPTURY = {
    "FSD V5": {"arsenic": 10, "dataminedwakeexceptions": 10, "chemicalmanipulators": 10},
    "Thrusters Dirty V5": {"pharmaceuticalisolators": 10, "cadmium": 10, "conductiveceramics": 10},
    "Shields V5": {"improvisedcomponents": 5, "militarygradealloys": 5, "shieldemitters": 10},
    "Guardian Booster": {"focuscrystals": 24, "guardianmoduleblueprint": 1, "guardianpowercell": 21},
}

CENNIK = {
    "Earthlike body": 3200000,
    "Water world": 900000,
    "Ammonia world": 1500000,
    "High metal content body": 150000,
    "Terraformable": 1500000,
}


# --- BACKWARDS-COMPAT: LOG_DIR / SETTINGS -----------------------------------
# Dzięki temu stary kod typu:
#   from config import LOG_DIR, SETTINGS
# nadal działa, ale pod spodem korzysta z ConfigManagera.

def __getattr__(name: str) -> Any:
    if name == "LOG_DIR":
        # Uwaga: preferuj config.get("log_dir") albo config.LOG_DIR w nowym kodzie.
        return config.log_dir
    if name == "SETTINGS":
        # Snapshot ustawień tylko do ODCZYTU (nie jest live-view).
        return config.as_dict()
    raise AttributeError(f"module 'config' has no attribute '{name}'")
