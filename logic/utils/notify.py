import threading
import pyttsx3
import queue
from datetime import datetime
from typing import Any, Callable
import config
from logic.tts.text_preprocessor import prepare_tts
from logic.capabilities import CAP_TTS_ADVANCED_POLICY, CAP_VOICE_STT, has_capability
from logic.event_insight_mapping import get_tts_policy_spec


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
    except Exception:
        pass


_TTS_ENGINE_LOGGED = False


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
            pass
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
        pass


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
    def __init__(self):
        self._last = {}
        self._lock = threading.Lock()

    def can_send(self, key: str, cooldown_sec: float, context: str | None = None) -> bool:
        """
        key     – typ komunikatu, np. 'LOW_FUEL', 'MAKLAR_JACKPOT', 'FSS_50'
        context – np. system/stacja, żeby rozróżnić miejsca
        """
        import time

        now = time.time()
        full_key = (key, context) if context is not None else key

        with self._lock:
            last = self._last.get(full_key, 0)
            if now - last < cooldown_sec:
                return False
            self._last[full_key] = now
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


def is_voice_stt_available() -> bool:
    return has_capability(CAP_VOICE_STT)


def _queue_log_line(text: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    MSG_QUEUE.put(("log", f"[{timestamp}] {text}"))


def execute_voice_stt_action(
    action: Callable[[], Any] | None = None,
    *,
    fallback_message: str = "Tryb glosowy STT niedostepny w tym profilu. Uzyj UI/hotkey.",
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
                pass
        return False, None

    if action is None:
        return True, None

    try:
        return True, action()
    except Exception as exc:
        print(f"[VOICE_STT] action failed: {type(exc).__name__}: {exc}")
        _queue_log_line("Akcja glosowa STT chwilowo niedostepna. Uzyj UI/hotkey.")
        return False, None
