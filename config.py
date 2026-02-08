from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict

# --- ŚCIEŻKI / PLIKI ---------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SETTINGS_SOURCE_LOGGED = False
SCIENCE_EXCEL_PATH = "renata_science_data.xlsx"
APP_VERSION = "v0.9.2"


def _settings_path() -> str:
    override = os.getenv("RENATA_SETTINGS_PATH")
    if override:
        return override
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if appdata:
        return os.path.join(appdata, "RenataAI", "user_settings.json")
    return os.path.join(BASE_DIR, "user_settings.json")


def _settings_source() -> str:
    if os.getenv("RENATA_SETTINGS_PATH"):
        return "override"
    if os.getenv("APPDATA") or os.getenv("LOCALAPPDATA"):
        return "appdata"
    return "legacy"


SETTINGS_FILE = _settings_path()


def _migrate_settings_if_needed(target_path: str) -> bool:
    try:
        legacy_path = os.path.join(BASE_DIR, "user_settings.json")
        if not os.path.isfile(legacy_path):
            return False
        if os.path.isfile(target_path):
            return False
        target_dir = os.path.dirname(target_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(legacy_path, target_path)
        print(f"[CONFIG] Migrated settings to {target_path}")
        return True
    except Exception:
        return False


def _log_settings_source(source: str) -> None:
    global _SETTINGS_SOURCE_LOGGED
    if _SETTINGS_SOURCE_LOGGED:
        return
    _SETTINGS_SOURCE_LOGGED = True
    print(f"[CONFIG] Settings source={source}")


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
    "Gold": 7600,
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
    "tts.engine": "auto",             # auto | piper | pyttsx3
    "tts.piper_bin": "",
    "tts.piper_model_path": "",
    "tts.piper_config_path": "",
    # TTS-TUNING-01c: faster cadence with very short pauses.
    "tts.piper_length_scale": 0.80,
    "tts.piper_sentence_silence": 0.05,
    "tts.pyttsx3_rate": 190,
    "tts.pyttsx3_volume": 1.0,
    "tts.cooldown_global_sec": 8,
    "tts.cooldown_nav_sec": 20,
    "tts.cooldown_explore_sec": 30,
    "tts.cooldown_alert_sec": 15,
    "tts.cooldown_route_sec": 15,
    "features.tts.free_policy_enabled": False,
    "landing_pad_speech": True,       # komunikaty do lądowania
    "route_progress_speech": True,    # 25/50/75% itp.
    "exit_summary_enabled": True,     # podsumowanie po skanowaniu
    "voice_exit_summary": True,       # glosowe podsumowanie

    # SCHOWEK / AUTO-COPY
    "auto_clipboard": True,           # auto-schowek (route)
    "auto_clipboard_mode": "NEXT_HOP",
    "auto_clipboard_next_hop_trigger": "fsdjump",
    "auto_clipboard_next_hop_copy_on_route_ready": True,
    "auto_clipboard_next_hop_resync_policy": "nearest_forward",
    "auto_clipboard_next_hop_desync_confirm_jumps": 2,
    "auto_clipboard_next_hop_allow_manual_advance": True,
    "features.clipboard.next_hop_stepper": True,
    "debug_next_hop": False,

    # SPANSH / SIEĆ
    "spansh_timeout": 20,
    "spansh_retries": 3,
    "features.spansh.debug_payload": False,
    "features.spansh.form_urlencoded_enabled": True,
    "features.spansh.neutron_via_enabled": True,
    "features.spansh.neutron_overcharge_enabled": True,
    "features.spansh.trade_market_age_enabled": True,

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
    "science_data_path": SCIENCE_EXCEL_PATH,
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

    # TABLES (Spansh schemas)
    "features.tables.spansh_schema_enabled": True,
    "features.tables.normalized_rows_enabled": True,
    "features.tables.schema_renderer_enabled": True,
    "features.tables.column_picker_enabled": True,
    "features.tables.treeview_enabled": True,
    "features.tables.ui_badges_enabled": True,
    "features.tables.persist_sort_enabled": True,
    "tables_visible_columns": {},
    "tables_sort_state": {},
    "column_presets": {},
    "ui.popup_positions": {},
    "window_positions": {},
    "features.ui.neutron_via_compact": True,
    "features.ui.neutron_via_autocomplete": True,
    "features.ui.results_context_menu": True,
    "features.debug.panel": False,
    "features.debug.spansh_last_request": False,
    "features.ui.tabs.tourist_enabled": False,
    "features.ui.tabs.fleet_carrier_enabled": False,
    "features.ui.tabs.colonisation_enabled": False,
    "features.ui.tabs.galaxy_enabled": False,
    "features.providers.edsm_enabled": True,
    "features.providers.system_lookup_online": True,
    "features.trade.station_autocomplete_by_system": True,
    "features.trade.station_lookup_online": True,
    "features.trade.market_age_slider": True,

    # DEBUG
    "debug_autocomplete": False,
    "debug_cache": False,
    "debug_dedup": False,

    # PROGI DLA MAKLERA PRO (backend only – ale też lecą do JSONa)
    "jackpot_thresholds": DEFAULT_JACKPOT_THRESHOLDS,

    # LEGACY / UI ALIASES (utrzymanie zgodnosci)
    "log_path": "",
    "enable_sounds": False,
    "read_landing_pad": True,
    "route_progress_messages": True,
    "low_fuel_warning": True,
    "high_value_planet_alerts": True,
    "dss_bio3_assistant": True,
    "trade_jackpot_alerts": True,

    # Tabele (nowy format ustawien per schema)
    "tables": {},
}


class ConfigManager:
    """
    Centralny manager konfiguracji.
    Trzyma ustawienia w pamięci + w pliku JSON (user_settings.json).
    """

    def __init__(self, settings_path: str | None = None) -> None:
        self.settings_path = settings_path or SETTINGS_FILE
        self._settings: Dict[str, Any] = DEFAULT_SETTINGS.copy()
        migrated = _migrate_settings_if_needed(self.settings_path)
        source = "legacy_migrated" if migrated else _settings_source()
        _log_settings_source(source)
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
        settings_dir = os.path.dirname(self.settings_path)
        if settings_dir:
            os.makedirs(settings_dir, exist_ok=True)
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

    @property
    def exit_summary_enabled(self) -> bool:
        return bool(self.get("exit_summary_enabled", True))

    @property
    def voice_exit_summary(self) -> bool:
        return bool(self.get("voice_exit_summary", True))


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
