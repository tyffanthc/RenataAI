import threading
import pyttsx3
import queue
from datetime import datetime
import config
from logic.tts.text_preprocessor import prepare_tts


# Globalna kolejka komunikatów dla GUI (Thread-Safe)
MSG_QUEUE = queue.Queue()

_TTS_CATEGORY_MAP = {
    "MSG.NEXT_HOP": "nav",
    "MSG.NEXT_HOP_COPIED": "nav",
    "MSG.ROUTE_FOUND": "route",
    "MSG.ROUTE_COMPLETE": "route",
    "MSG.ROUTE_DESYNC": "route",
    "MSG.FUEL_CRITICAL": "alert",
    "MSG.DOCKED": "info",
    "MSG.UNDOCKED": "info",
    "MSG.FIRST_DISCOVERY": "explore",
    "MSG.SYSTEM_FULLY_SCANNED": "explore",
    "MSG.ELW_DETECTED": "explore",
    "MSG.FOOTFALL": "explore",
}

_TTS_DEFAULT_COOLDOWNS = {
    "nav": 20.0,
    "route": 15.0,
    "alert": 15.0,
    "explore": 30.0,
    "info": 20.0,
}


def _tts_category(message_id: str) -> str:
    return _TTS_CATEGORY_MAP.get(message_id, "info")


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
    if ctx.get("in_transit"):
        return False
    if _is_transit_mode() and _tts_category(message_id) == "nav":
        return False
    try:
        global_cd = float(config.get("tts.cooldown_global_sec", 8))
    except Exception:
        global_cd = 8.0
    if not DEBOUNCER.can_send("TTS_GLOBAL", global_cd):
        return False
    category = _tts_category(message_id)
    intent_cd = _get_category_cooldown(category)
    if not DEBOUNCER.can_send(
        f"TTS_INTENT:{message_id}",
        intent_cd,
        context=_intent_context(ctx),
    ):
        return False
    return True


def powiedz(tekst, gui_ref=None, *, message_id=None, context=None):
    # Zamiast pisać bezpośrednio do gui_ref, wrzucamy do kolejki
    t = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{t}] {tekst}"
    
    # Drukuj w konsoli systemowej zawsze
    print(f"[RENATA]: {tekst}")
    
    # Wyślij do GUI przez kolejkę
    MSG_QUEUE.put(("log", full_msg))
    
    # Synteza mowy (tylko przez Text Preprocessor)
    if config.get("voice_enabled", True) and message_id:
        if _should_speak_tts(str(message_id), context):
            tts_text = prepare_tts(str(message_id), context=context)
            if tts_text:
                threading.Thread(target=_watek_mowy, args=(tts_text,)).start()


def _watek_mowy(tekst):
    try:
        _speak_tts(tekst)
    except Exception:
        pass


def _speak_tts(tekst: str) -> None:
    engine = str(config.get("tts.engine", "auto")).strip().lower()
    if engine not in ("auto", "piper", "pyttsx3"):
        engine = "auto"

    if engine in ("auto", "piper"):
        try:
            from logic.tts import piper_tts

            if piper_tts.speak(tekst):
                return
        except Exception:
            if engine == "piper":
                return

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
