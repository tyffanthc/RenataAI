import config
import threading
import pandas as pd
from datetime import datetime
import time

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

    _MODE_IDS = {"NORMAL", "EXPLORATION", "COMBAT", "MINING", "DOCKED"}
    _MODE_SOURCES = {"AUTO", "MANUAL", "RESTORED"}
    _MODE_TTL_DEFAULTS = {
        "COMBAT": 45.0,
        "EXPLORATION": 120.0,
        "MINING": 90.0,
    }
    _MODE_TTL_CONFIG_KEYS = {
        "COMBAT": "mode.ttl.combat_sec",
        "EXPLORATION": "mode.ttl.exploration_sec",
        "MINING": "mode.ttl.mining_sec",
    }
    _MODE_PRIORITY = {
        "COMBAT": 5,
        "DOCKED": 4,
        "EXPLORATION": 3,
        "MINING": 2,
        "NORMAL": 1,
    }

    _MODE_EXPLORATION_EVENTS = {
        "FSSDiscoveryScan",
        "FSSAllBodiesFound",
        "SAASignalsFound",
        "SAAScanComplete",
        "ScanOrganic",
        "CodexEntry",
        "Scan",
    }
    _MODE_MINING_EVENTS = {
        "ProspectedAsteroid",
        "MiningRefined",
        "AsteroidCracked",
        "AbrasionBlaster",
        "SubsurfaceDisplacement",
        "SeismicChargeDetonated",
    }
    _MODE_COMBAT_EVENTS = {
        "Interdicted",
        "Interdiction",
        "EscapeInterdiction",
        "UnderAttack",
        "HullDamage",
        "ShieldState",
    }
    _MODE_MINING_ITEM_HINTS = (
        "mininglaser",
        "abrasionblaster",
        "subsurfacedisplacementmissile",
        "seismicchargelauncher",
        "prospectorlimpetcontroller",
        "collectorlimpetcontroller",
        "refinery",
    )

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
        self.last_exploration_summary_signature = None
        self.last_cash_in_signature = None
        self.cash_in_skip_signature = None
        self.last_survival_rebuy_signature = None
        self.last_combat_awareness_signature = None

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
        saved_mode = str(config.STATE.get("route_mode", "idle") or "idle").strip().lower()
        if saved_mode not in {"awareness", "intent", "idle"}:
            saved_mode = "idle"
        saved_target = str(config.STATE.get("route_target", "") or "").strip() or None
        try:
            saved_progress = int(config.STATE.get("route_progress_percent", 0) or 0)
        except Exception:
            saved_progress = 0
        self.route_mode: str = saved_mode
        self.route_target: str | None = saved_target
        self.route_progress_percent: int = max(0, min(100, saved_progress))
        self.next_system: str | None = str(config.STATE.get("route_next_system", "") or "").strip() or None
        saved_route_profile = str(config.STATE.get("route_profile", "") or "").strip().upper()
        if saved_route_profile == "FAST":
            saved_route_profile = "FAST_NEUTRON"
        if saved_route_profile not in {"", "SAFE", "FAST_NEUTRON", "SECURE"}:
            saved_route_profile = ""
        self.route_profile: str = saved_route_profile
        self.is_off_route: bool = bool(config.STATE.get("route_is_off_route", False))
        self.inventory = config.STATE.get("inventory", {})

        # True only while MainLoop replays historical Journal lines at startup.
        # Used to suppress misleading live-style TTS during bootstrap.
        self.bootstrap_replay = False
        # True only after first live (non-bootstrap) system event from Journal.
        # Prevents showing stale bootstrap system context as "live" startup state.
        self.has_live_system_event = False

        # F7 mode detector (AUTO as default runtime source of truth for GUI + overlay).
        has_saved_mode = "mode_id" in config.STATE
        restored_mode = str(config.STATE.get("mode_id", "NORMAL") or "NORMAL").strip().upper()
        if restored_mode not in self._MODE_IDS:
            restored_mode = "NORMAL"
        restored_source = str(config.STATE.get("mode_source", "RESTORED") or "RESTORED").strip().upper()
        if restored_source not in self._MODE_SOURCES:
            restored_source = "RESTORED"
        if not has_saved_mode:
            restored_source = "AUTO"

        try:
            restored_conf = float(config.STATE.get("mode_confidence", 0.6))
        except Exception:
            restored_conf = 0.6
        restored_conf = max(0.0, min(1.0, restored_conf))

        now_ts = time.time()
        try:
            restored_since = float(config.STATE.get("mode_since", now_ts) or now_ts)
        except Exception:
            restored_since = now_ts
        if restored_since <= 0:
            restored_since = now_ts

        restored_ttl = config.STATE.get("mode_ttl")
        try:
            restored_ttl = float(restored_ttl) if restored_ttl is not None else None
        except Exception:
            restored_ttl = None
        if restored_ttl is not None and restored_ttl <= 0:
            restored_ttl = None

        self.mode_id: str = restored_mode
        self.mode_source: str = restored_source
        self.mode_confidence: float = restored_conf
        self.mode_since: float = restored_since
        self.mode_ttl: float | None = restored_ttl
        self.mode_overlay: str | None = None
        self.mode_combat_silence: bool = bool(self.mode_id == "COMBAT")

        self._mode_signal_docked: bool = bool(self.is_docked)
        self._mode_signal_combat_active: bool = False
        self._mode_signal_combat_last_ts: float = 0.0
        self._mode_signal_hardpoints_since: float | None = None
        self._mode_signal_exploration_active: bool = False
        self._mode_signal_exploration_last_ts: float = 0.0
        self._mode_signal_mining_active: bool = False
        self._mode_signal_mining_last_ts: float = 0.0
        self._mode_signal_mining_loadout: bool = False
        self._mode_last_emit_signature: str = ""

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

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _status_flag(status: dict, bit: int) -> bool:
        flags_val = AppState._safe_int((status or {}).get("Flags"))
        if flags_val is None:
            return False
        try:
            return bool(flags_val & (1 << bit))
        except Exception:
            return False

    @classmethod
    def _normalize_mode_id(cls, mode_id: str | None) -> str:
        norm = str(mode_id or "NORMAL").strip().upper() or "NORMAL"
        if norm not in cls._MODE_IDS:
            return "NORMAL"
        return norm

    @classmethod
    def _normalize_mode_source(cls, mode_source: str | None) -> str:
        norm = str(mode_source or "AUTO").strip().upper() or "AUTO"
        if norm not in cls._MODE_SOURCES:
            return "AUTO"
        return norm

    @staticmethod
    def _mode_confidence_hint(mode_id: str) -> float:
        if mode_id == "DOCKED":
            return 1.0
        if mode_id == "COMBAT":
            return 0.95
        if mode_id == "EXPLORATION":
            return 0.86
        if mode_id == "MINING":
            return 0.80
        return 0.60

    def _mode_snapshot_locked(self) -> dict:
        return {
            "mode_id": str(self.mode_id),
            "mode_source": str(self.mode_source),
            "mode_confidence": float(self.mode_confidence),
            "mode_since": float(self.mode_since),
            "mode_ttl": (float(self.mode_ttl) if self.mode_ttl is not None else None),
            "mode_overlay": (str(self.mode_overlay) if self.mode_overlay else None),
            "mode_combat_silence": bool(self.mode_combat_silence),
        }

    def _persist_mode_state_locked(self) -> None:
        config.STATE["mode_id"] = str(self.mode_id)
        config.STATE["mode_source"] = str(self.mode_source)
        config.STATE["mode_confidence"] = float(self.mode_confidence)
        config.STATE["mode_since"] = float(self.mode_since)
        if self.mode_ttl is None:
            config.STATE.pop("mode_ttl", None)
        else:
            config.STATE["mode_ttl"] = float(self.mode_ttl)

    def _emit_mode_state_locked(self, *, force: bool = False) -> dict:
        snapshot = self._mode_snapshot_locked()
        signature = (
            f"{snapshot['mode_id']}:{snapshot['mode_source']}:"
            f"{snapshot['mode_confidence']:.2f}:{int(snapshot['mode_since'])}:"
            f"{snapshot['mode_ttl'] if snapshot['mode_ttl'] is not None else '-'}:"
            f"{snapshot['mode_overlay'] if snapshot.get('mode_overlay') else '-'}:"
            f"{1 if snapshot.get('mode_combat_silence') else 0}"
        )
        if force or signature != self._mode_last_emit_signature:
            self._mode_last_emit_signature = signature
            utils.MSG_QUEUE.put(("mode_state", dict(snapshot)))
        return snapshot

    @classmethod
    def _detect_mining_loadout_from_modules(cls, modules: list[dict] | None) -> bool:
        if not isinstance(modules, list):
            return False
        for module in modules:
            if not isinstance(module, dict):
                continue
            item = str(module.get("Item") or "").strip().lower()
            slot = str(module.get("Slot") or "").strip().lower()
            text = f"{slot}|{item}"
            if any(hint in text for hint in cls._MODE_MINING_ITEM_HINTS):
                return True
        return False

    def _detect_mining_loadout_locked(self) -> bool:
        modules = []
        try:
            modules = list(getattr(self.ship_state, "modules", []) or [])
        except Exception:
            modules = []
        return self._detect_mining_loadout_from_modules(modules)

    def _resolve_mode_ttl_seconds_locked(self, mode_id: str) -> float | None:
        norm = self._normalize_mode_id(mode_id)
        default_ttl = self._MODE_TTL_DEFAULTS.get(norm)
        if default_ttl is None:
            return None

        cfg_key = self._MODE_TTL_CONFIG_KEYS.get(norm)
        raw_value = self.config.get(cfg_key, default_ttl) if cfg_key else default_ttl
        try:
            ttl = float(raw_value)
        except Exception:
            ttl = float(default_ttl)
        if ttl <= 0:
            ttl = float(default_ttl)
        return float(ttl)

    @staticmethod
    def _is_mode_signal_alive(last_signal_ts: float, ttl_seconds: float | None, now_ts: float) -> bool:
        if ttl_seconds is None or ttl_seconds <= 0:
            return False
        if last_signal_ts <= 0:
            return False
        return (now_ts - float(last_signal_ts)) <= float(ttl_seconds)

    def _apply_mode_safety_locked(self, *, auto_mode_id: str) -> bool:
        mode_norm = self._normalize_mode_id(self.mode_id)
        auto_norm = self._normalize_mode_id(auto_mode_id)
        source_norm = self._normalize_mode_source(self.mode_source)

        overlay_mode: str | None = None
        if source_norm == "MANUAL" and auto_norm == "COMBAT" and mode_norm != "COMBAT":
            overlay_mode = "COMBAT"

        combat_silence = bool(mode_norm == "COMBAT" or overlay_mode == "COMBAT")

        changed = False
        if overlay_mode != self.mode_overlay:
            changed = True
        if bool(combat_silence) != bool(self.mode_combat_silence):
            changed = True

        self.mode_overlay = overlay_mode
        self.mode_combat_silence = bool(combat_silence)
        return changed

    def _set_mode_locked(
        self,
        *,
        mode_id: str,
        mode_source: str = "AUTO",
        mode_confidence: float | None = None,
        mode_ttl: float | None = None,
    ) -> bool:
        norm_id = self._normalize_mode_id(mode_id)
        norm_source = self._normalize_mode_source(mode_source)
        if mode_confidence is None:
            mode_confidence = self._mode_confidence_hint(norm_id)
        try:
            conf = max(0.0, min(1.0, float(mode_confidence)))
        except Exception:
            conf = self._mode_confidence_hint(norm_id)
        ttl = None
        if mode_ttl is not None:
            try:
                ttl = float(mode_ttl)
            except Exception:
                ttl = None
            if ttl is not None and ttl <= 0:
                ttl = None

        changed = False
        if norm_id != self.mode_id or norm_source != self.mode_source:
            changed = True
            self.mode_since = time.time()
        if abs(float(conf) - float(self.mode_confidence)) > 0.02:
            changed = True
        if (ttl is None) != (self.mode_ttl is None):
            changed = True
        elif ttl is not None and self.mode_ttl is not None and abs(float(ttl) - float(self.mode_ttl)) > 0.1:
            changed = True

        self.mode_id = norm_id
        self.mode_source = norm_source
        self.mode_confidence = conf
        self.mode_ttl = ttl
        if changed:
            self._persist_mode_state_locked()
        return changed

    def _resolve_auto_mode_locked(self) -> tuple[str, float | None]:
        now_ts = time.time()
        combat_ttl = self._resolve_mode_ttl_seconds_locked("COMBAT")
        exploration_ttl = self._resolve_mode_ttl_seconds_locked("EXPLORATION")
        mining_ttl = self._resolve_mode_ttl_seconds_locked("MINING")

        combat_active = self._is_mode_signal_alive(
            self._mode_signal_combat_last_ts,
            combat_ttl,
            now_ts,
        )
        exploration_active = self._is_mode_signal_alive(
            self._mode_signal_exploration_last_ts,
            exploration_ttl,
            now_ts,
        )
        mining_active = bool(self._mode_signal_mining_loadout) and self._is_mode_signal_alive(
            self._mode_signal_mining_last_ts,
            mining_ttl,
            now_ts,
        )

        candidates = [("NORMAL", None)]
        if mining_active:
            candidates.append(("MINING", mining_ttl))
        if exploration_active:
            candidates.append(("EXPLORATION", exploration_ttl))
        if bool(self._mode_signal_docked):
            candidates.append(("DOCKED", None))
        if combat_active:
            candidates.append(("COMBAT", combat_ttl))

        candidates.sort(key=lambda item: self._MODE_PRIORITY.get(item[0], 0), reverse=True)
        return candidates[0]

    def _recompute_auto_mode_locked(self, *, source: str = "mode.auto") -> dict:
        auto_mode_id, auto_ttl = self._resolve_auto_mode_locked()
        if self.mode_source == "MANUAL":
            safety_changed = self._apply_mode_safety_locked(auto_mode_id=auto_mode_id)
            if safety_changed:
                snapshot = self._emit_mode_state_locked()
                log_event_throttled(
                    "state.mode",
                    250,
                    "STATE",
                    (
                        f"Mode id={snapshot['mode_id']} source={snapshot['mode_source']} "
                        f"overlay={snapshot.get('mode_overlay') or '-'} "
                        f"combat_silence={bool(snapshot.get('mode_combat_silence'))} "
                        f"trigger={source}"
                    ),
                )
                return snapshot
            return self._mode_snapshot_locked()

        mode_id, ttl = auto_mode_id, auto_ttl
        changed = self._set_mode_locked(
            mode_id=mode_id,
            mode_source="AUTO",
            mode_confidence=self._mode_confidence_hint(mode_id),
            mode_ttl=ttl,
        )
        safety_changed = self._apply_mode_safety_locked(auto_mode_id=auto_mode_id)
        if changed or safety_changed:
            snapshot = self._emit_mode_state_locked()
            log_event_throttled(
                "state.mode",
                250,
                "STATE",
                (
                    f"Mode id={snapshot['mode_id']} source={snapshot['mode_source']} "
                    f"confidence={snapshot['mode_confidence']:.2f} ttl={snapshot['mode_ttl']} "
                    f"overlay={snapshot.get('mode_overlay') or '-'} "
                    f"combat_silence={bool(snapshot.get('mode_combat_silence'))} "
                    f"trigger={source}"
                ),
            )
            return snapshot
        return self._mode_snapshot_locked()

    def get_mode_state_snapshot(self) -> dict:
        with self.lock:
            return dict(self._mode_snapshot_locked())

    def publish_mode_state(self, *, force: bool = False) -> dict:
        with self.lock:
            return dict(self._emit_mode_state_locked(force=force))

    def refresh_mode_state(self, *, source: str = "mode.tick") -> dict:
        with self.lock:
            return dict(self._recompute_auto_mode_locked(source=source))

    def set_mode_manual(self, mode_id: str, *, source: str = "mode.manual") -> dict:
        with self.lock:
            manual_mode = self._normalize_mode_id(mode_id)
            changed = self._set_mode_locked(
                mode_id=manual_mode,
                mode_source="MANUAL",
                mode_confidence=1.0,
                mode_ttl=None,
            )
            auto_mode_id, _ttl = self._resolve_auto_mode_locked()
            safety_changed = self._apply_mode_safety_locked(auto_mode_id=auto_mode_id)
            if changed or safety_changed:
                snapshot = self._emit_mode_state_locked(force=True)
                log_event_throttled(
                    "state.mode.manual",
                    250,
                    "STATE",
                    (
                        f"Manual mode={snapshot['mode_id']} overlay={snapshot.get('mode_overlay') or '-'} "
                        f"combat_silence={bool(snapshot.get('mode_combat_silence'))} source={source}"
                    ),
                )
                return dict(snapshot)
            return dict(self._mode_snapshot_locked())

    def set_mode_auto(self, *, source: str = "mode.auto.manual_release") -> dict:
        with self.lock:
            auto_mode_id, auto_ttl = self._resolve_auto_mode_locked()
            changed = self._set_mode_locked(
                mode_id=auto_mode_id,
                mode_source="AUTO",
                mode_confidence=self._mode_confidence_hint(auto_mode_id),
                mode_ttl=auto_ttl,
            )
            safety_changed = self._apply_mode_safety_locked(auto_mode_id=auto_mode_id)
            if changed or safety_changed:
                snapshot = self._emit_mode_state_locked(force=True)
                log_event_throttled(
                    "state.mode.auto",
                    250,
                    "STATE",
                    (
                        f"Auto mode={snapshot['mode_id']} overlay={snapshot.get('mode_overlay') or '-'} "
                        f"combat_silence={bool(snapshot.get('mode_combat_silence'))} source={source}"
                    ),
                )
                return dict(snapshot)
            return dict(self._mode_snapshot_locked())

    def update_mode_signal_from_status(self, status: dict | None, *, source: str = "status_json") -> dict:
        status_data = dict(status or {})
        now_ts = time.time()
        with self.lock:
            docked = bool(status_data.get("Docked")) or self._status_flag(status_data, 0)
            self._mode_signal_docked = bool(docked)
            if self.is_docked != bool(docked):
                self.is_docked = bool(docked)
                config.STATE["is_docked"] = self.is_docked

            in_danger = bool(status_data.get("InDanger")) or self._status_flag(status_data, 22)
            interdicted = bool(status_data.get("BeingInterdicted")) or self._status_flag(status_data, 23)
            under_attack = bool(status_data.get("UnderAttack"))
            hardpoints = bool(status_data.get("HardpointsDeployed")) or self._status_flag(status_data, 6)

            direct_combat_signal = bool(in_danger or interdicted or under_attack)
            if direct_combat_signal:
                self._mode_signal_combat_active = True
                self._mode_signal_combat_last_ts = now_ts
                self._mode_signal_hardpoints_since = None
            else:
                if hardpoints:
                    if self._mode_signal_hardpoints_since is None:
                        self._mode_signal_hardpoints_since = now_ts
                    if (now_ts - float(self._mode_signal_hardpoints_since)) >= 3.0:
                        self._mode_signal_combat_active = True
                        self._mode_signal_combat_last_ts = now_ts
                    else:
                        self._mode_signal_combat_active = False
                else:
                    self._mode_signal_hardpoints_since = None
                    self._mode_signal_combat_active = False
                if docked and not hardpoints:
                    # Docked state should clear stale combat hold from previous encounters.
                    self._mode_signal_combat_last_ts = 0.0

            focus = self._safe_int(status_data.get("GuiFocus"))
            in_exploration_focus = focus in {9, 10}
            self._mode_signal_exploration_active = bool(in_exploration_focus)
            if in_exploration_focus:
                self._mode_signal_exploration_last_ts = now_ts

            in_ring = bool(status_data.get("InRing")) or bool(status_data.get("InAsteroidRing"))
            detected_from_ship = self._detect_mining_loadout_locked()
            if detected_from_ship:
                self._mode_signal_mining_loadout = True
            self._mode_signal_mining_active = bool(in_ring)
            if in_ring and self._mode_signal_mining_loadout:
                self._mode_signal_mining_last_ts = now_ts

            return dict(self._recompute_auto_mode_locked(source=source))

    def update_mode_signal_from_journal(self, event: dict | None, *, source: str = "journal") -> dict:
        ev = dict(event or {})
        event_name = str(ev.get("event") or "").strip()
        if not event_name:
            return self.get_mode_state_snapshot()
        now_ts = time.time()
        with self.lock:
            if event_name == "Docked":
                self._mode_signal_docked = True
                self.is_docked = True
                config.STATE["is_docked"] = True
                self._mode_signal_combat_active = False
                self._mode_signal_combat_last_ts = 0.0
                self._mode_signal_hardpoints_since = None
            elif event_name == "Undocked":
                self._mode_signal_docked = False
                self.is_docked = False
                config.STATE["is_docked"] = False
            elif event_name in {"Died"}:
                self._mode_signal_combat_active = False
                self._mode_signal_combat_last_ts = 0.0
                self._mode_signal_hardpoints_since = None

            if event_name in self._MODE_COMBAT_EVENTS:
                self._mode_signal_combat_active = True
                self._mode_signal_combat_last_ts = now_ts
            if event_name in self._MODE_EXPLORATION_EVENTS:
                self._mode_signal_exploration_last_ts = now_ts
            if event_name in self._MODE_MINING_EVENTS:
                self._mode_signal_mining_last_ts = now_ts

            if event_name == "Loadout":
                modules = ev.get("Modules")
                self._mode_signal_mining_loadout = self._detect_mining_loadout_from_modules(modules)

            return dict(self._recompute_auto_mode_locked(source=source))

    def update_mode_signal_from_runtime(
        self,
        domain: str,
        payload: dict | None = None,
        *,
        source: str = "runtime",
    ) -> dict:
        domain_norm = str(domain or "").strip().lower()
        data = dict(payload or {})
        now_ts = time.time()
        with self.lock:
            if domain_norm in {"combat_awareness", "survival_rebuy"}:
                risk = str(data.get("risk_status") or "").strip().upper()
                in_combat = bool(data.get("in_combat"))
                if in_combat or ("HIGH" in risk) or ("CRIT" in risk):
                    self._mode_signal_combat_active = True
                    self._mode_signal_combat_last_ts = now_ts
            if domain_norm in {"exploration_summary", "fss", "exo"}:
                self._mode_signal_exploration_last_ts = now_ts
            if domain_norm in {"mining", "mining_awareness"}:
                self._mode_signal_mining_last_ts = now_ts
            if domain_norm == "ship_state":
                if "mining_loadout_detected" in data:
                    self._mode_signal_mining_loadout = bool(data.get("mining_loadout_detected"))
                if "in_ring" in data:
                    in_ring = bool(data.get("in_ring"))
                    self._mode_signal_mining_active = in_ring
                    if in_ring and self._mode_signal_mining_loadout:
                        self._mode_signal_mining_last_ts = now_ts
            return dict(self._recompute_auto_mode_locked(source=source))

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
        changed = False
        with self.lock:
            value = bool(is_docked)
            changed = (self.is_docked != value)
            self.is_docked = value
            config.STATE["is_docked"] = self.is_docked
            self._mode_signal_docked = self.is_docked
            if self.is_docked:
                self._mode_signal_combat_active = False
                self._mode_signal_combat_last_ts = 0.0
                self._mode_signal_hardpoints_since = None
        log_event_throttled("state.docked", 500, "STATE", f"Docked = {self.is_docked}")
        if changed:
            self.refresh_mode_state(source="set_docked")

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

    def get_route_awareness_snapshot(self) -> dict:
        with self.lock:
            return {
                "route_mode": self.route_mode,
                "route_target": self.route_target,
                "route_progress_percent": int(self.route_progress_percent),
                "next_system": self.next_system,
                "route_profile": self.route_profile,
                "is_off_route": bool(self.is_off_route),
            }

    def update_route_awareness(
        self,
        *,
        route_mode: str | None = None,
        route_target: str | None = None,
        route_progress_percent: int | None = None,
        next_system: str | None = None,
        route_profile: str | None = None,
        is_off_route: bool | None = None,
        source: str = "runtime",
    ) -> dict:
        changed = False
        with self.lock:
            if route_mode is not None:
                mode = str(route_mode).strip().lower()
                if mode not in {"awareness", "intent", "idle"}:
                    mode = "idle"
                if mode != self.route_mode:
                    self.route_mode = mode
                    changed = True

            if route_target is not None:
                target = str(route_target).strip() or None
                if target != self.route_target:
                    self.route_target = target
                    changed = True

            if route_progress_percent is not None:
                try:
                    progress = int(route_progress_percent)
                except Exception:
                    progress = self.route_progress_percent
                progress = max(0, min(100, progress))
                if progress != self.route_progress_percent:
                    self.route_progress_percent = progress
                    changed = True

            if next_system is not None:
                next_value = str(next_system).strip() or None
                if next_value != self.next_system:
                    self.next_system = next_value
                    changed = True

            if route_profile is not None:
                profile = str(route_profile or "").strip().upper()
                if profile == "FAST":
                    profile = "FAST_NEUTRON"
                if profile not in {"", "SAFE", "FAST_NEUTRON", "SECURE"}:
                    profile = ""
                if profile != self.route_profile:
                    self.route_profile = profile
                    changed = True

            if is_off_route is not None:
                off_route = bool(is_off_route)
                if off_route != self.is_off_route:
                    self.is_off_route = off_route
                    changed = True

            config.STATE["route_mode"] = self.route_mode
            config.STATE["route_target"] = self.route_target or ""
            config.STATE["route_progress_percent"] = int(self.route_progress_percent)
            config.STATE["route_next_system"] = self.next_system or ""
            config.STATE["route_profile"] = self.route_profile or ""
            config.STATE["route_is_off_route"] = bool(self.is_off_route)

            snapshot = {
                "route_mode": self.route_mode,
                "route_target": self.route_target,
                "route_progress_percent": int(self.route_progress_percent),
                "next_system": self.next_system,
                "route_profile": self.route_profile,
                "is_off_route": bool(self.is_off_route),
            }

        if changed:
            log_event_throttled(
                "state.route_awareness",
                500,
                "STATE",
                (
                    f"Route mode={snapshot['route_mode']} "
                    f"target={snapshot['route_target'] or '-'} "
                    f"progress={snapshot['route_progress_percent']} "
                    f"next={snapshot['next_system'] or '-'} "
                    f"profile={snapshot['route_profile'] or '-'} "
                    f"off_route={snapshot['is_off_route']} "
                    f"source={source}"
                ),
            )
        return snapshot

    def set_route_intent(
        self,
        target: str | None,
        *,
        source: str = "intent",
        route_profile: str | None = None,
    ) -> dict:
        normalized = str(target or "").strip()
        if not normalized:
            return self.update_route_awareness(
                route_mode="idle",
                route_target="",
                route_progress_percent=0,
                next_system="",
                route_profile="",
                is_off_route=False,
                source=source,
            )
        return self.update_route_awareness(
            route_mode="intent",
            route_target=normalized,
            route_progress_percent=0,
            next_system=normalized,
            route_profile=route_profile,
            is_off_route=False,
            source=source,
        )


# Globalny stan aplikacji – importowany w innych modułach
app_state = AppState()
