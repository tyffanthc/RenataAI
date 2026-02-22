from __future__ import annotations

import copy
import json
import os
import shutil
import threading
from contextlib import contextmanager
from typing import Any, Dict

from logic.context_state_contract import (
    contract_with_runtime_state,
    load_state_contract_file,
    migrate_state_contract_payload,
    restart_loss_audit_contract,
    runtime_state_from_contract,
    save_state_contract_file,
)

# --- ŚCIEŻKI / PLIKI ---------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SETTINGS_SOURCE_LOGGED = False
APP_VERSION = "v0.9.4"


def _renata_user_home_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "RenataAI")


def renata_user_home_dir() -> str:
    """
    Public helper for local user-owned data that should live in:
    C:\\Users\\<user>\\RenataAI
    (not in %%APPDATA%%).
    """
    path = _renata_user_home_dir()
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def renata_user_home_file(filename: str) -> str:
    return os.path.join(renata_user_home_dir(), str(filename or "").strip())


_LEGACY_USER_HOME_LOOSE_FILES = (
    "offline_station_index.json",
    "renata_modules_data.json",
    "renata_science_data.xlsx",
    "user_entries.jsonl",
    "user_entry_categories.json",
    "user_logbook.json",
)


def _migrate_loose_user_home_files_if_needed() -> None:
    """
    Moves legacy loose files from C:\\Users\\<user>\\* into C:\\Users\\<user>\\RenataAI\\*
    without touching %%APPDATA%% files.
    """
    home = os.path.expanduser("~")
    target_dir = renata_user_home_dir()
    for filename in _LEGACY_USER_HOME_LOOSE_FILES:
        try:
            src = os.path.join(home, filename)
            dst = os.path.join(target_dir, filename)
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            if not os.path.isfile(src):
                continue
            if os.path.exists(dst):
                continue
            shutil.move(src, dst)
            print(f"[CONFIG] Migrated user file to RenataAI: {filename}")
        except Exception:
            continue


SCIENCE_EXCEL_PATH = renata_user_home_file("renata_science_data.xlsx")


def _settings_path() -> str:
    override = os.getenv("RENATA_SETTINGS_PATH")
    if override:
        return override
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if appdata:
        return os.path.join(appdata, "RenataAI", "user_settings.json")
    return os.path.join(BASE_DIR, "user_settings.json")


def _state_path() -> str:
    override = os.getenv("RENATA_STATE_PATH")
    if override:
        return override
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if appdata:
        return os.path.join(appdata, "RenataAI", "app_state.json")
    return os.path.join(BASE_DIR, "app_state.json")


def _settings_source() -> str:
    if os.getenv("RENATA_SETTINGS_PATH"):
        return "override"
    if os.getenv("APPDATA") or os.getenv("LOCALAPPDATA"):
        return "appdata"
    return "legacy"


SETTINGS_FILE = _settings_path()
STATE_FILE = _state_path()


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


def _migrate_state_if_needed(target_path: str) -> bool:
    try:
        legacy_path = os.path.join(BASE_DIR, "app_state.json")
        if os.path.abspath(legacy_path) == os.path.abspath(target_path):
            return False
        if not os.path.isfile(legacy_path):
            return False
        if os.path.isfile(target_path):
            return False
        target_dir = os.path.dirname(target_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(legacy_path, target_path)
        print(f"[CONFIG] Migrated state to {target_path}")
        return True
    except Exception:
        return False


def _log_settings_source(source: str) -> None:
    global _SETTINGS_SOURCE_LOGGED
    if _SETTINGS_SOURCE_LOGGED:
        return
    _SETTINGS_SOURCE_LOGGED = True
    print(f"[CONFIG] Settings source={source}")


def _migrate_legacy_local_path_setting(settings: Dict[str, Any], key: str, filename: str) -> bool:
    """
    Repoint legacy loose-file locations to ~/RenataAI/<filename>.
    Only touches:
    - bare filenames (legacy repo-relative / cwd-relative)
    - absolute paths in user home root (C:\\Users\\<user>\\<filename>)
    Leaves APPDATA and custom directories untouched.
    """
    current = settings.get(key)
    if not isinstance(current, str):
        return False

    raw = current.strip()
    if not raw:
        return False

    target = renata_user_home_file(filename)
    home_root_legacy = os.path.join(os.path.expanduser("~"), filename)

    def _norm(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    is_bare = raw.casefold() == filename.casefold()
    is_home_root_legacy = _norm(raw) == _norm(home_root_legacy)
    already_target = _norm(raw) == _norm(target)

    if already_target:
        return False
    if not (is_bare or is_home_root_legacy):
        return False

    settings[key] = target
    return True


def _migrate_legacy_dump_download_path_setting(settings: Dict[str, Any]) -> bool:
    key = "cash_in.dump_download_path"
    current = settings.get(key)
    if not isinstance(current, str):
        return False
    raw = current.strip()
    if not raw:
        return False

    target = renata_user_home_file("galaxy_stations.json.gz")
    home_root_legacy = os.path.join(os.path.expanduser("~"), "galaxy_stations.json.gz")
    appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")

    def _norm(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    old_candidates = {home_root_legacy}
    if appdata:
        old_candidates.add(os.path.join(appdata, "RenataAI", "data", "cash_in", "galaxy_stations.json.gz"))
        old_candidates.add(os.path.join(appdata, "RenataAI", "data", "galaxy_stations.json.gz"))
    if raw.casefold() == "galaxy_stations.json.gz":
        settings[key] = target
        return True
    try:
        if _norm(raw) == _norm(target):
            return False
        if any(_norm(raw) == _norm(candidate) for candidate in old_candidates):
            settings[key] = target
            return True
    except Exception:
        return False
    return False


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

DEFAULT_RISK_VALUE_THRESHOLDS: Dict[str, Dict[str, int]] = {
    "exploration": {
        "low": 50_000_000,
        "med": 100_000_000,
        "high": 150_000_000,
        "very_high": 200_000_000,
        "critical": 250_000_000,
    },
    "exobio": {
        "low": 100_000_000,
        "med": 250_000_000,
        "high": 500_000_000,
        "very_high": 750_000_000,
        "critical": 1_000_000_000,
    },
}

DEFAULT_CARGO_VALUE_FALLBACK_PRICES: Dict[str, int] = {
    "Gold": 38_000,
    "Silver": 24_000,
    "Palladium": 52_000,
    "Platinum": 68_000,
    "Tritium": 46_000,
    "Agronomic Treatment": 3_500,
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
    "tts_enabled": True,              # alias preferencji dla globalnego TTS
    "verbosity": "normal",            # preference layer mirror
    "trade_choice_bias": "balanced",  # preference layer mirror
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
    # FREE/PUB default profile (PRO is opt-in via explicit capability override).
    "plan.profile": "FREE",
    "features.tts.free_policy_enabled": True,
    "capabilities.voice_stt": False,
    "capabilities.ui_extended_tabs": False,
    "capabilities.settings_full": False,
    "capabilities.tts_advanced_policy": False,
    "landing_pad_speech": True,       # komunikaty do lądowania
    "route_progress_speech": True,    # 25/50/75% itp.
    "exit_summary_enabled": True,     # podsumowanie po skanowaniu
    "voice_exit_summary": True,       # glosowe podsumowanie
    "cash_in.station_candidates_lookup_enabled": False,
    "cash_in.station_candidates_limit": 24,
    "cash_in.cross_system_discovery_enabled": True,
    "cash_in.cross_system_radius_ly": 120.0,
    "cash_in.cross_system_max_systems": 12,
    "cash_in.swr_cache_enabled": True,
    "cash_in.swr_cache_fresh_ttl_sec": 900.0,
    "cash_in.swr_cache_stale_ttl_sec": 21600.0,
    "cash_in.swr_cache_max_items": 64,
    "cash_in.local_known_fallback_enabled": True,
    "cash_in.local_known_fallback_ttl_sec": 86400.0,
    "cash_in.local_known_fallback_max_items": 256,
    "cash_in.offline_index_fallback_enabled": True,
    "cash_in.offline_index_path": renata_user_home_file("offline_station_index.json"),
    "cash_in.offline_index_non_carrier_only": True,
    "cash_in.offline_index_confidence_med_age_days": 30,
    "cash_in.dump_download_url": "https://downloads.spansh.co.uk/galaxy_stations.json.gz",
    "cash_in.dump_download_path": renata_user_home_file("galaxy_stations.json.gz"),
    "cash_in.avoid_carriers_for_uc": True,
    "cash_in.carrier_ok_for_fast_mode": True,
    "cash_in.show_tariff_meta": True,
    "cash_in.hutton_guard_ls_threshold": 500_000,
    "cash_in.hutton_guard_score_penalty": 18,
    "cash_in.startjump_callout_enabled": True,
    "cash_in.startjump_callout_cooldown_sec": 35.0,
    "cash_in.hotkey_enabled": True,
    "cash_in.hotkey_binding": "Ctrl+Shift+C",
    "cash_in.persist_route_profile_to_route_state": False,
    "providers.edsm.resilience.circuit_breaker_ttl_sec": 600.0,
    "providers.edsm.resilience.retry.max_attempts": 4,
    "providers.edsm.resilience.retry.base_delay_sec": 1.0,
    "providers.edsm.resilience.retry.max_delay_sec": 8.0,
    "providers.edsm.resilience.retry.jitter_sec": 0.35,
    "survival_rebuy_awareness_enabled": True,  # F4 survival/rebuy awareness
    "combat_awareness_enabled": True,  # F5 combat awareness baseline
    "dispatcher.f4_voice_priority_window_sec": 12.0,
    "dispatcher.priority_matrix_window_sec": 10.0,
    "dispatcher.priority_escalation_enabled": True,
    "dispatcher.priority_escalation_window_sec": 20.0,
    "dispatcher.class_cooldown.combat": 0.0,
    "dispatcher.class_cooldown.f4": 0.0,
    "dispatcher.class_cooldown.exploration": 0.0,
    "dispatcher.class_cooldown.navigation": 0.0,
    "dispatcher.class_cooldown.general": 0.0,
    # F7 mode system TTL policy (seconds, AUTO detector).
    "mode.ttl.combat_sec": 45.0,
    "mode.ttl.exploration_sec": 120.0,
    "mode.ttl.mining_sec": 90.0,
    # F10 anti-spam persistence TTL/limits.
    "anti_spam.persist_min_interval_sec": 2.0,
    "anti_spam.debouncer.ttl_sec": 900.0,
    "anti_spam.debouncer.max_keys": 800,
    "anti_spam.route_milestone.ttl_sec": 1800.0,
    "anti_spam.route_milestone.max_routes": 24,
    "anti_spam.trade_jackpot.ttl_sec": 1200.0,
    "anti_spam.trade_jackpot.max_stations": 256,
    "anti_spam.trade_jackpot.max_items": 1024,
    "anti_spam.smuggler_warned.ttl_sec": 1200.0,
    "anti_spam.smuggler_warned.max_targets": 512,
    # F7 risk/rebuy value thresholds (credits).
    "risk.threshold.exploration.low_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exploration"]["low"],
    "risk.threshold.exploration.med_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exploration"]["med"],
    "risk.threshold.exploration.high_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exploration"]["high"],
    "risk.threshold.exploration.very_high_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exploration"]["very_high"],
    "risk.threshold.exploration.critical_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exploration"]["critical"],
    "risk.threshold.exobio.low_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exobio"]["low"],
    "risk.threshold.exobio.med_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exobio"]["med"],
    "risk.threshold.exobio.high_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exobio"]["high"],
    "risk.threshold.exobio.very_high_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exobio"]["very_high"],
    "risk.threshold.exobio.critical_cr": DEFAULT_RISK_VALUE_THRESHOLDS["exobio"]["critical"],
    # F7 cargo value-at-risk estimator.
    "risk.cargo.default_unit_price_cr": 20_000,
    "risk.cargo.floor_factor.market": 0.85,
    "risk.cargo.floor_factor.cache": 0.70,
    "risk.cargo.floor_factor.fallback": 0.55,
    "risk.cargo.fallback_prices": DEFAULT_CARGO_VALUE_FALLBACK_PRICES,

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
    "high_g_warning_threshold_g": 2.0,  # prog ostrzezenia high-g (Earth G)
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
    "modules_data_path": renata_user_home_file("renata_modules_data.json"),
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
        paths_migrated = False
        paths_migrated = _migrate_legacy_local_path_setting(
            merged, "science_data_path", "renata_science_data.xlsx"
        ) or paths_migrated
        paths_migrated = _migrate_legacy_local_path_setting(
            merged, "modules_data_path", "renata_modules_data.json"
        ) or paths_migrated
        paths_migrated = _migrate_legacy_local_path_setting(
            merged, "cash_in.offline_index_path", "offline_station_index.json"
        ) or paths_migrated
        paths_migrated = _migrate_legacy_dump_download_path_setting(merged) or paths_migrated
        self._settings = merged
        if paths_migrated:
            try:
                self._write_file()
                print("[CONFIG] Migrated legacy local file paths to ~/RenataAI")
            except Exception:
                pass

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

        if "voice_enabled" in new_data and "tts_enabled" not in new_data:
            updated["tts_enabled"] = bool(updated.get("voice_enabled", True))
        if "tts_enabled" in new_data and "voice_enabled" not in new_data:
            updated["voice_enabled"] = bool(updated.get("tts_enabled", True))

        self._settings = updated
        self._write_file()

        preference_patch: Dict[str, Any] = {}
        if "voice_enabled" in new_data or "tts_enabled" in new_data:
            preference_patch["tts_enabled"] = bool(updated.get("voice_enabled", True))
        if "verbosity" in new_data:
            preference_patch["verbosity"] = updated.get("verbosity")
        if "trade_choice_bias" in new_data:
            preference_patch["trade_choice_bias"] = updated.get("trade_choice_bias")

        if preference_patch:
            try:
                update_preferences(preference_patch)
            except Exception:
                pass

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
_migrate_loose_user_home_files_if_needed()
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

class _PersistentStateDict(dict):
    """
    Legacy-compatible runtime dict with write-through persistence.
    """

    def __init__(self, *args, on_change=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_change = on_change
        self._suspend_depth = 0

    @contextmanager
    def suspend_callbacks(self):
        self._suspend_depth += 1
        try:
            yield self
        finally:
            self._suspend_depth = max(0, self._suspend_depth - 1)

    def _emit_change(self) -> None:
        if self._suspend_depth > 0:
            return
        if callable(self._on_change):
            self._on_change(dict(self))

    def __setitem__(self, key, value):
        changed = (key not in self) or (self.get(key) != value)
        super().__setitem__(key, value)
        if changed:
            self._emit_change()

    def __delitem__(self, key):
        existed = key in self
        super().__delitem__(key)
        if existed:
            self._emit_change()

    def pop(self, key, default=None):
        existed = key in self
        value = super().pop(key, default)
        if existed:
            self._emit_change()
        return value

    def clear(self) -> None:
        if not self:
            return
        super().clear()
        self._emit_change()

    def setdefault(self, key, default=None):
        if key in self:
            return self[key]
        value = super().setdefault(key, default)
        self._emit_change()
        return value

    def update(self, *args, **kwargs):
        before = dict(self)
        super().update(*args, **kwargs)
        if before != dict(self):
            self._emit_change()

    def replace_all(self, payload: Dict[str, Any], *, notify: bool = False) -> None:
        with self.suspend_callbacks():
            super().clear()
            super().update(payload or {})
        if notify:
            self._emit_change()


_STATE_LOCK = threading.RLock()
_STATE_WRITE_ERROR_LOGGED = False


def _load_state_contract() -> Dict[str, Any]:
    _migrate_state_if_needed(STATE_FILE)
    contract = load_state_contract_file(STATE_FILE)
    normalized = migrate_state_contract_payload(contract)
    try:
        save_state_contract_file(STATE_FILE, normalized)
    except Exception:
        pass
    return normalized


def _persist_runtime_state_snapshot(snapshot: Dict[str, Any]) -> None:
    global _STATE_CONTRACT, _STATE_WRITE_ERROR_LOGGED
    with _STATE_LOCK:
        candidate = contract_with_runtime_state(_STATE_CONTRACT, snapshot or {})
        _STATE_CONTRACT = candidate
        try:
            save_state_contract_file(STATE_FILE, candidate)
            _STATE_WRITE_ERROR_LOGGED = False
        except Exception as exc:
            if not _STATE_WRITE_ERROR_LOGGED:
                _STATE_WRITE_ERROR_LOGGED = True
                print(f"[CONFIG] State persistence error: {exc}")


_STATE_CONTRACT = _load_state_contract()
STATE = _PersistentStateDict(
    runtime_state_from_contract(_STATE_CONTRACT),
    on_change=_persist_runtime_state_snapshot,
)


def get_state_contract() -> Dict[str, Any]:
    with _STATE_LOCK:
        return copy.deepcopy(migrate_state_contract_payload(_STATE_CONTRACT))


def _deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = copy.deepcopy(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out.get(key) or {}, value)
            continue
        out[key] = copy.deepcopy(value)
    return out


def save_state_contract(contract_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist layered state contract and refresh legacy config.STATE snapshot.
    """
    global _STATE_CONTRACT, _STATE_WRITE_ERROR_LOGGED
    normalized = migrate_state_contract_payload(contract_payload)
    with _STATE_LOCK:
        _STATE_CONTRACT = normalized
        try:
            save_state_contract_file(STATE_FILE, normalized)
            _STATE_WRITE_ERROR_LOGGED = False
        except Exception as exc:
            if not _STATE_WRITE_ERROR_LOGGED:
                _STATE_WRITE_ERROR_LOGGED = True
                print(f"[CONFIG] State persistence error: {exc}")
        STATE.replace_all(runtime_state_from_contract(_STATE_CONTRACT), notify=False)
        return copy.deepcopy(_STATE_CONTRACT)


def get_ui_state(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    contract = get_state_contract()
    value = contract.get("ui_state")
    if not isinstance(value, dict):
        value = {}
    if isinstance(default, dict):
        return _deep_merge_dict(default, value)
    return copy.deepcopy(value)


def save_ui_state(ui_state: Dict[str, Any]) -> Dict[str, Any]:
    contract = get_state_contract()
    contract["ui_state"] = dict(ui_state or {}) if isinstance(ui_state, dict) else {}
    saved = save_state_contract(contract)
    out = saved.get("ui_state")
    return copy.deepcopy(out) if isinstance(out, dict) else {}


def update_ui_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    base = get_ui_state(default={})
    merged = _deep_merge_dict(base, patch if isinstance(patch, dict) else {})
    return save_ui_state(merged)


def get_domain_state(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    contract = get_state_contract()
    value = contract.get("domain_state")
    if not isinstance(value, dict):
        value = {}
    if isinstance(default, dict):
        return _deep_merge_dict(default, value)
    return copy.deepcopy(value)


def save_domain_state(domain_state: Dict[str, Any]) -> Dict[str, Any]:
    contract = get_state_contract()
    contract["domain_state"] = dict(domain_state or {}) if isinstance(domain_state, dict) else {}
    saved = save_state_contract(contract)
    out = saved.get("domain_state")
    return copy.deepcopy(out) if isinstance(out, dict) else {}


def update_domain_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    base = get_domain_state(default={})
    merged = _deep_merge_dict(base, patch if isinstance(patch, dict) else {})
    return save_domain_state(merged)


def get_last_context(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    domain = get_domain_state(default={})
    out = {
        "last_route": copy.deepcopy(domain.get("last_route"))
        if isinstance(domain.get("last_route"), dict)
        else {},
        "last_commodity": copy.deepcopy(domain.get("last_commodity"))
        if isinstance(domain.get("last_commodity"), dict)
        else {},
        "last_plan_id": str(domain.get("last_plan_id") or ""),
    }
    if isinstance(default, dict):
        return _deep_merge_dict(default, out)
    return out


def update_last_context(
    *,
    last_route: Dict[str, Any] | None = None,
    last_commodity: Dict[str, Any] | None = None,
    last_plan_id: Any = None,
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if last_route is not None:
        patch["last_route"] = copy.deepcopy(last_route) if isinstance(last_route, dict) else {}
    if last_commodity is not None:
        patch["last_commodity"] = (
            copy.deepcopy(last_commodity) if isinstance(last_commodity, dict) else {}
        )
    if last_plan_id is not None:
        patch["last_plan_id"] = str(last_plan_id or "")
    if patch:
        update_domain_state(patch)
    return get_last_context()


def get_anti_spam_state(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    contract = get_state_contract()
    value = contract.get("anti_spam_state")
    if not isinstance(value, dict):
        value = {}
    if isinstance(default, dict):
        return _deep_merge_dict(default, value)
    return copy.deepcopy(value)


def save_anti_spam_state(anti_spam_state: Dict[str, Any]) -> Dict[str, Any]:
    contract = get_state_contract()
    contract["anti_spam_state"] = (
        dict(anti_spam_state or {}) if isinstance(anti_spam_state, dict) else {}
    )
    saved = save_state_contract(contract)
    out = saved.get("anti_spam_state")
    return copy.deepcopy(out) if isinstance(out, dict) else {}


def update_anti_spam_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    base = get_anti_spam_state(default={})
    merged = _deep_merge_dict(base, patch if isinstance(patch, dict) else {})
    return save_anti_spam_state(merged)


_PREFERENCES_DEFAULTS: Dict[str, Any] = {
    "verbosity": "normal",
    "trade_choice_bias": "balanced",
    "tts_enabled": True,
}
_PREFERENCES_ALLOWED_VERBOSITY = {"low", "normal", "high"}
_PREFERENCES_ALLOWED_TRADE_BIAS = {"balanced", "profit", "safety", "speed"}


def _normalize_preference_verbosity(value: Any) -> str:
    norm = str(value or "").strip().lower()
    if norm in _PREFERENCES_ALLOWED_VERBOSITY:
        return norm
    return str(_PREFERENCES_DEFAULTS["verbosity"])


def _normalize_preference_trade_bias(value: Any) -> str:
    norm = str(value or "").strip().lower()
    if norm in _PREFERENCES_ALLOWED_TRADE_BIAS:
        return norm
    return str(_PREFERENCES_DEFAULTS["trade_choice_bias"])


def _normalize_preference_tts_enabled(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def _normalize_preferences_payload(
    payload: Any,
    *,
    fill_defaults: bool,
) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    out: Dict[str, Any] = dict(_PREFERENCES_DEFAULTS) if fill_defaults else {}

    if fill_defaults or "verbosity" in source:
        out["verbosity"] = _normalize_preference_verbosity(source.get("verbosity", out.get("verbosity")))

    if fill_defaults or "trade_choice_bias" in source:
        out["trade_choice_bias"] = _normalize_preference_trade_bias(
            source.get("trade_choice_bias", out.get("trade_choice_bias"))
        )

    if fill_defaults or "tts_enabled" in source:
        default_tts = bool(out.get("tts_enabled", True))
        out["tts_enabled"] = _normalize_preference_tts_enabled(
            source.get("tts_enabled", default_tts),
            default=default_tts,
        )

    return out


def _apply_preferences_to_runtime_settings(preferences: Any, *, explicit_only: bool) -> Dict[str, Any]:
    runtime_settings = getattr(config, "_settings", None)  # type: ignore[attr-defined]
    if not isinstance(runtime_settings, dict):
        return _normalize_preferences_payload(preferences, fill_defaults=True)

    incoming = preferences if isinstance(preferences, dict) else {}
    resolved = _normalize_preferences_payload(incoming, fill_defaults=True)
    if explicit_only:
        keys_to_apply = {
            key for key in ("verbosity", "trade_choice_bias", "tts_enabled")
            if key in incoming
        }
    else:
        keys_to_apply = {"verbosity", "trade_choice_bias", "tts_enabled"}

    if "verbosity" in keys_to_apply:
        runtime_settings["verbosity"] = str(resolved["verbosity"])

    if "trade_choice_bias" in keys_to_apply:
        runtime_settings["trade_choice_bias"] = str(resolved["trade_choice_bias"])

    if "tts_enabled" in keys_to_apply:
        tts_enabled = bool(resolved["tts_enabled"])
        runtime_settings["tts_enabled"] = tts_enabled
        runtime_settings["voice_enabled"] = tts_enabled

    return resolved


def get_preferences(default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    contract = get_state_contract()
    raw = contract.get("preferences")
    resolved = _normalize_preferences_payload(raw, fill_defaults=True)
    if isinstance(default, dict):
        return _deep_merge_dict(default, resolved)
    return copy.deepcopy(resolved)


def save_preferences(preferences: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_preferences_payload(preferences, fill_defaults=True)
    contract = get_state_contract()
    contract["preferences"] = copy.deepcopy(normalized)
    save_state_contract(contract)
    _apply_preferences_to_runtime_settings(normalized, explicit_only=False)
    return copy.deepcopy(normalized)


def update_preferences(patch: Dict[str, Any]) -> Dict[str, Any]:
    base = get_preferences(default={})
    patch_norm = _normalize_preferences_payload(patch, fill_defaults=False)
    merged = dict(base)
    merged.update(patch_norm)
    return save_preferences(merged)


def _bootstrap_preferences_from_state_contract() -> None:
    try:
        with _STATE_LOCK:
            raw = (_STATE_CONTRACT or {}).get("preferences", {})
        if isinstance(raw, dict) and raw:
            _apply_preferences_to_runtime_settings(raw, explicit_only=True)
    except Exception:
        pass


def persist_runtime_state() -> Dict[str, Any]:
    """
    Force flush of current legacy runtime state into layered contract.
    """
    _persist_runtime_state_snapshot(dict(STATE))
    return get_state_contract()


def get_restart_loss_audit() -> Dict[str, Dict[str, str]]:
    return restart_loss_audit_contract()


_bootstrap_preferences_from_state_contract()

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
