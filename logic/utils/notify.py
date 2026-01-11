import threading
import pyttsx3
import queue
from datetime import datetime
import config


# Globalna kolejka komunikatów dla GUI (Thread-Safe)
MSG_QUEUE = queue.Queue()


def powiedz(tekst, gui_ref=None):
    # Zamiast pisać bezpośrednio do gui_ref, wrzucamy do kolejki
    t = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{t}] {tekst}"
    
    # Drukuj w konsoli systemowej zawsze
    print(f"[RENATA]: {tekst}")
    
    # Wyślij do GUI przez kolejkę
    MSG_QUEUE.put(("log", full_msg))
    
    # Synteza mowy
    if config.get("voice_enabled", True):
        threading.Thread(target=_watek_mowy, args=(tekst,)).start()


def _watek_mowy(tekst):
    try:
        eng = pyttsx3.init()
        try:
            eng.setProperty('voice', eng.getProperty('voices')[0].id)
        except:
            pass
        eng.setProperty('rate', 165)
        eng.say(tekst)
        eng.runAndWait()
        eng.stop()
    except:
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
