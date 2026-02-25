import threading
import pyttsx3
import queue
from datetime import datetime
from typing import Any, Callable
import config
from logic.tts.text_preprocessor import prepare_tts
from logic.capabilities import CAP_TTS_ADVANCED_POLICY, CAP_VOICE_STT, has_capability
from logic.event_insight_mapping import get_tts_policy_spec
from logic.utils.renata_log import log_event_throttled


# Globalna kolejka komunikatów dla GUI (Thread-Safe)
MSG_QUEUE = queue.Queue()

_TTS_DEFAULT_COOLDOWNS = {
    "nav": 20.0,
    "route": 15.0,
    "alert": 15.0,
    "explore": 30.0,
    "info": 20.0,
}


def _tts_category(message_id: str) -> str:
    return get_tts_policy_spec(message_id).category


def _tts_intent(message_id: str) -> str:
    return get_tts_policy_spec(message_id).intent


def _tts_cooldown_policy(message_id: str, context: dict | None = None) -> str:
    ctx = context or {}
    override = str(ctx.get("tts_cooldown_policy", "")).strip().upper()
    if override in {"NORMAL", "BYPASS_GLOBAL", "ALWAYS_SAY"}:
        return override
    return str(get_tts_policy_spec(message_id).cooldown_policy or "NORMAL").strip().upper()


def _get_category_cooldown(category: str) -> float:
    cfg_key = f"tts.cooldown_{category}_sec"
    try:
        return float(config.get(cfg_key, _TTS_DEFAULT_COOLDOWNS.get(category, 20.0)))
    except Exception:
        return _TTS_DEFAULT_COOLDOWNS.get(category, 20.0)


def _intent_context(context: dict | None) -> str | None:
    if not context:
        return None
    for key in ("system", "station", "body", "target"):
        value = context.get(key)
        if value:
            return str(value)
    return None


def _is_transit_mode() -> bool:
    try:
        from app.route_manager import route_manager  # type: ignore

        return bool(getattr(route_manager, "route", []))
    except Exception:
        return False


def _should_speak_tts(message_id: str, context: dict | None) -> bool:
    ctx = context or {}
    if ctx.get("force_tts"):
        return True
    if ctx.get("suppress_tts"):
        return False
    confidence = str(ctx.get("confidence", "")).strip().lower()
    if confidence in ("low", "mid", "uncertain", "maybe"):
        return False

    intent = _tts_intent(message_id)
    category = _tts_category(message_id)
    cooldown_policy = _tts_cooldown_policy(message_id, ctx)

    if has_capability(CAP_TTS_ADVANCED_POLICY):
        return _should_speak_legacy(
            message_id,
            ctx,
            intent=intent,
            category=category,
            cooldown_policy=cooldown_policy,
        )

    if intent == "silent":
        return False
    if ctx.get("in_transit"):
        return False
    if _is_transit_mode() and category == "nav":
        return False

    if cooldown_policy not in {"BYPASS_GLOBAL", "ALWAYS_SAY"}:
        try:
            global_cd = float(config.get("tts.cooldown_global_sec", 8))
        except Exception:
            global_cd = 8.0
        if not DEBOUNCER.can_send("TTS_GLOBAL", global_cd):
            return False

    if intent == "critical" or cooldown_policy == "ALWAYS_SAY":
        return True

    intent_cd = _get_category_cooldown(category)
    if not DEBOUNCER.can_send(
        f"TTS_INTENT:{message_id}",
        intent_cd,
        context=_intent_context(ctx),
    ):
        return False
    return True


def _should_speak_legacy(
    message_id: str,
    ctx: dict,
    *,
    intent: str,
    category: str,
    cooldown_policy: str,
) -> bool:
    if ctx.get("in_transit"):
        return False
    if _is_transit_mode() and category == "nav":
        return False

    if cooldown_policy not in {"BYPASS_GLOBAL", "ALWAYS_SAY"}:
        try:
            global_cd = float(config.get("tts.cooldown_global_sec", 8))
        except Exception:
            global_cd = 8.0
        if not DEBOUNCER.can_send("TTS_GLOBAL", global_cd):
            return False

    if intent == "critical" or cooldown_policy == "ALWAYS_SAY":
        return True

    intent_cd = _get_category_cooldown(category)
    if not DEBOUNCER.can_send(
        f"TTS_INTENT:{message_id}",
        intent_cd,
        context=_intent_context(ctx),
    ):
        return False
    return True


def powiedz(tekst, gui_ref=None, *, message_id=None, context=None, force: bool = False):
    # Zamiast pisać bezpośrednio do gui_ref, wrzucamy do kolejki
    t = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{t}] {tekst}"
    
    # Drukuj w konsoli systemowej zawsze
    print(f"[RENATA]: {tekst}")
    
    # Wyślij do GUI przez kolejkę
    MSG_QUEUE.put(("log", full_msg))

    ctx = context or {}
    summary_payload = ctx.get("summary_payload")
    if isinstance(summary_payload, dict):
        MSG_QUEUE.put(("exploration_summary", summary_payload))
    cash_in_payload = ctx.get("cash_in_payload")
    if isinstance(cash_in_payload, dict):
        MSG_QUEUE.put(("cash_in_assistant", cash_in_payload))
    survival_payload = ctx.get("survival_payload")
    if isinstance(survival_payload, dict):
        MSG_QUEUE.put(("survival_rebuy", survival_payload))
    combat_payload = ctx.get("combat_payload")
    if isinstance(combat_payload, dict):
        MSG_QUEUE.put(("combat_awareness", combat_payload))
    
    # Synteza mowy (tylko przez Text Preprocessor)
    if config.get("voice_enabled", True) and message_id:
        if force or _should_speak_tts(str(message_id), context):
            tts_text = prepare_tts(str(message_id), context=context)
            if tts_text:
                threading.Thread(target=_watek_mowy, args=(tts_text,)).start()


def _watek_mowy(tekst):
    try:
        _speak_tts(tekst)
    except Exception as exc:
        _log_notify_soft_failure(
            "tts_thread",
            f"TTS: blad syntezy mowy ({type(exc).__name__}).",
        )


_TTS_ENGINE_LOGGED = False


def _log_notify_soft_failure(key: str, text: str, *, cooldown_sec: float = 5.0) -> None:
    try:
        debouncer = globals().get("DEBOUNCER")
        if debouncer is not None:
            try:
                if not debouncer.can_send(f"NOTIFY_SOFT_{key}", float(cooldown_sec)):
                    return
            except Exception:
                try:
                    log_event_throttled(
                        "notify:soft_failure_debouncer",
                        5.0,
                        "notify soft-failure debouncer check failed",
                        key=key,
                    )
                except Exception:
                    return
        _queue_log_line(text)
    except Exception:
        try:
            print(text)
        except Exception:
            return


def _log_tts_engine(line: str) -> None:
    global _TTS_ENGINE_LOGGED
    if _TTS_ENGINE_LOGGED:
        return
    print(line)
    _TTS_ENGINE_LOGGED = True


def _speak_tts(tekst: str) -> None:
    engine = str(config.get("tts.engine", "auto")).strip().lower()
    if engine not in ("auto", "piper", "pyttsx3"):
        engine = "auto"

    if engine in ("auto", "piper"):
        try:
            from logic.tts import piper_tts
            selected = piper_tts.select_piper_paths(use_appdata=(engine == "auto"))
            if selected:
                _log_tts_engine(
                    f"TTS engine selected=piper source={selected.source}"
                )
                if piper_tts.speak(tekst, paths=selected):
                    return
            else:
                if engine == "auto":
                    _log_tts_engine("TTS engine selected=pyttsx3 reason=piper_not_found")
        except Exception:
            _log_notify_soft_failure(
                "tts_piper_path",
                "TTS Piper: blad inicjalizacji lub odtwarzania.",
            )
            if engine == "piper":
                return

        if engine == "piper":
            _log_tts_engine("TTS engine selected=pyttsx3 reason=piper_not_found")
            return

    if engine == "pyttsx3":
        _log_tts_engine("TTS engine selected=pyttsx3 source=settings")

    _speak_pyttsx3(tekst)


def _speak_pyttsx3(tekst: str) -> None:
    try:
        eng = pyttsx3.init()
        try:
            eng.setProperty("voice", eng.getProperty("voices")[0].id)
        except Exception:
            _log_notify_soft_failure(
                "pyttsx3_voice",
                "TTS: nie udalo sie ustawic glosu pyttsx3 (fallback domyslny).",
            )
        try:
            rate = int(config.get("tts.pyttsx3_rate", 155))
        except Exception:
            rate = 155
        try:
            volume = float(config.get("tts.pyttsx3_volume", 1.0))
        except Exception:
            volume = 1.0
        eng.setProperty("rate", rate)
        eng.setProperty("volume", volume)
        eng.say(tekst)
        eng.runAndWait()
        eng.stop()
    except Exception:
        _log_notify_soft_failure(
            "tts_pyttsx3",
            "TTS pyttsx3: blad syntezy mowy.",
        )


class NotificationDebouncer:
    """
    Prosty anty-spam dla komunikatów głosowych / logów.

    Trzyma w pamięci czas ostatniego wysłania komunikatu dla danego klucza
    (opcjonalnie z kontekstem: np. systemem, stacją) i pozwala ponownie
    wysłać komunikat dopiero po upływie określonego cooldownu.

    Typowe zastosowania w RenataAI:
    - LOW_FUEL: logic/events/fuel_events.py
      if DEBOUNCER.can_send("LOW_FUEL", 300, context=system_name):
          powiedz("Warning. Fuel reserves critical.", gui_ref)

    - FSS progi odkrycia (25/50/75/100%): logic/events/exploration_fss_events.py
      if DEBOUNCER.can_send("FSS_50", 120, context=system_name):
          powiedz("Połowa systemu przeskanowana.", gui_ref)

    Uwaga:
    - NotificationDebouncer nie zastępuje istniejących flag anty-spam
      w logice gameplay (np. FSS_25_WARNED, LOW_FUEL_WARNED) – działa
      jako dodatkowy bezpiecznik na wypadek glitchy w danych.
    """
    _STATE_SCHEMA_VERSION = 1
    _STATE_SECTION = "dispatcher_debouncer_windows"

    def __init__(self):
        self._last = {}
        self._lock = threading.Lock()
        self._loaded_from_contract = False
        self._last_persist_ts = 0.0

    @staticmethod
    def _retention_ttl_sec() -> float:
        try:
            return max(30.0, float(config.get("anti_spam.debouncer.ttl_sec", 900.0)))
        except Exception:
            return 900.0

    @staticmethod
    def _max_keys() -> int:
        try:
            return max(64, int(config.get("anti_spam.debouncer.max_keys", 800)))
        except Exception:
            return 800

    @staticmethod
    def _persist_min_interval_sec() -> float:
        try:
            return max(0.5, float(config.get("anti_spam.persist_min_interval_sec", 2.0)))
        except Exception:
            return 2.0

    @staticmethod
    def _normalize_key(full_key: Any) -> tuple[str, str | None] | None:
        if isinstance(full_key, tuple) and len(full_key) == 2:
            key = str(full_key[0] or "").strip()
            context_raw = full_key[1]
            context = str(context_raw).strip() if context_raw is not None else None
            if not key:
                return None
            return key, (context if context else None)
        key = str(full_key or "").strip()
        if not key:
            return None
        return key, None

    @staticmethod
    def _as_full_key(key: str, context: str | None) -> Any:
        return (key, context) if context is not None else key

    @staticmethod
    def _as_timestamp(value: Any) -> float | None:
        try:
            ts = float(value)
        except Exception:
            return None
        if ts <= 0:
            return None
        return ts

    def _prune_unlocked(self, now: float | None = None) -> bool:
        import time

        changed = False
        ts_now = float(now if now is not None else time.time())
        ttl = self._retention_ttl_sec()
        if ttl > 0:
            stale_before = ts_now - ttl
            stale_keys = [
                full_key
                for full_key, last_ts in list(self._last.items())
                if self._as_timestamp(last_ts) is None or float(last_ts) < stale_before
            ]
            for full_key in stale_keys:
                self._last.pop(full_key, None)
                changed = True

        max_keys = self._max_keys()
        if len(self._last) > max_keys:
            ordered = sorted(self._last.items(), key=lambda item: float(item[1]))
            for full_key, _ in ordered[: max(0, len(self._last) - max_keys)]:
                self._last.pop(full_key, None)
                changed = True
        return changed

    def _snapshot_unlocked(self, now: float | None = None) -> dict[str, Any]:
        import time

        ts_now = float(now if now is not None else time.time())
        self._prune_unlocked(ts_now)
        entries: list[dict[str, Any]] = []
        for full_key, last_ts in self._last.items():
            normalized = self._normalize_key(full_key)
            ts = self._as_timestamp(last_ts)
            if not normalized or ts is None:
                continue
            key, context = normalized
            row: dict[str, Any] = {"key": key, "last_ts": ts}
            if context is not None:
                row["context"] = context
            entries.append(row)
        entries.sort(key=lambda row: float(row.get("last_ts") or 0.0), reverse=True)
        return {
            "schema_version": self._STATE_SCHEMA_VERSION,
            "updated_at": int(ts_now),
            "entries": entries[: self._max_keys()],
        }

    def export_state(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def import_state(self, payload: dict[str, Any], *, replace: bool = True) -> int:
        import time

        if not isinstance(payload, dict):
            return 0

        loaded: dict[Any, float] = {}
        entries = payload.get("entries", [])
        if isinstance(entries, list):
            for row in entries:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("key") or "").strip()
                if not key:
                    continue
                raw_ctx = row.get("context")
                context = str(raw_ctx).strip() if raw_ctx is not None else None
                if context == "":
                    context = None
                ts = self._as_timestamp(row.get("last_ts"))
                if ts is None:
                    continue
                loaded[self._as_full_key(key, context)] = ts
        elif isinstance(entries, dict):
            for raw_key, raw_ts in entries.items():
                key = str(raw_key or "").strip()
                ts = self._as_timestamp(raw_ts)
                if key and ts is not None:
                    loaded[key] = ts

        with self._lock:
            if replace:
                self._last = {}
            self._last.update(loaded)
            self._prune_unlocked(time.time())
            self._loaded_from_contract = True
            return len(self._last)

    def load_from_contract(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._loaded_from_contract and not force:
                return {"loaded": False, "reason": "already_loaded", "keys": len(self._last)}

        payload: dict[str, Any] = {}
        try:
            anti_spam_state = config.get_anti_spam_state(default={})
            raw = anti_spam_state.get(self._STATE_SECTION) if isinstance(anti_spam_state, dict) else {}
            if isinstance(raw, dict):
                payload = raw
        except Exception:
            payload = {}

        if not payload:
            with self._lock:
                self._loaded_from_contract = True
            return {"loaded": False, "reason": "no_payload", "keys": 0}

        keys = self.import_state(payload, replace=True)
        return {"loaded": bool(keys), "reason": "ok", "keys": keys}

    def persist_to_contract(self, *, force: bool = False) -> bool:
        import time

        with self._lock:
            now = time.time()
            if (not force) and (self._last_persist_ts > 0.0):
                if (now - self._last_persist_ts) < self._persist_min_interval_sec():
                    return False
            payload = self._snapshot_unlocked(now)
            self._last_persist_ts = now

        try:
            config.update_anti_spam_state({self._STATE_SECTION: payload})
            return True
        except Exception:
            return False

    def reset(self, *, persist: bool = False) -> None:
        with self._lock:
            self._last = {}
            self._loaded_from_contract = False
            self._last_persist_ts = 0.0
        if persist:
            self.persist_to_contract(force=True)

    def can_send(self, key: str, cooldown_sec: float, context: str | None = None) -> bool:
        """
        key     – typ komunikatu, np. 'LOW_FUEL', 'MAKLAR_JACKPOT', 'FSS_50'
        context – np. system/stacja, żeby rozróżnić miejsca
        """
        import time

        self.load_from_contract()
        now = time.time()
        full_key = (key, context) if context is not None else key

        changed = False
        with self._lock:
            if self._prune_unlocked(now):
                changed = True
            last = self._last.get(full_key, 0)
            if now - last < cooldown_sec:
                return False
            self._last[full_key] = now
            changed = True

        if changed:
            self.persist_to_contract()
        return True

    def is_allowed(self, key: str, cooldown_sec: float, context: str | None = None) -> bool:
        """
        Alias na can_send używany przez inne moduły (np. SpanshClient).

        Sprawdza, czy minął cooldown dla danego klucza/kontekstu
        i jeśli tak – od razu aktualizuje stan wewnętrzny.
        """
        return self.can_send(key, cooldown_sec, context=context)


# Globalny debouncer do użycia w całej aplikacji
DEBOUNCER = NotificationDebouncer()
DEBOUNCER.load_from_contract(force=True)


def is_voice_stt_available() -> bool:
    return has_capability(CAP_VOICE_STT)


def _queue_log_line(text: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    MSG_QUEUE.put(("log", f"[{timestamp}] {text}"))


def execute_voice_stt_action(
    action: Callable[[], Any] | None = None,
    *,
    fallback_message: str = "Tryb głosowy STT niedostępny w tym profilu. Użyj UI/hotkey.",
    on_unavailable: Callable[[], None] | None = None,
) -> tuple[bool, Any | None]:
    """
    Centralny gate dla voice/STT.

    FREE:
    - zwraca (False, None),
    - publikuje bezpieczny fallback do logu/GUI,
    - nie rzuca wyjatku.

    PRO:
    - uruchamia `action` (jesli przekazane),
    - zwraca (True, wynik) lub (True, None), gdy action nie podano.
    """
    if not is_voice_stt_available():
        _queue_log_line(fallback_message)
        if callable(on_unavailable):
            try:
                on_unavailable()
            except Exception:
                _log_notify_soft_failure(
                    "stt_on_unavailable_callback",
                    "STT fallback callback failed.",
                )
        return False, None

    if action is None:
        return True, None

    try:
        return True, action()
    except Exception as exc:
        print(f"[VOICE_STT] action failed: {type(exc).__name__}: {exc}")
        _queue_log_line("Akcja głosowa STT chwilowo niedostępna. Użyj UI/hotkey.")
        return False, None
