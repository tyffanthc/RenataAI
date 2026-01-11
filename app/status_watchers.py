import os
import time
import json

from logic.utils import MSG_QUEUE, powiedz
from logic.events.files import status_path, market_path


class BaseWatcher:
    """
    Wspólna logika poll() dla StatusWatcher i MarketWatcher.
    """
    def __init__(self, path, handler, gui_ref, app_state, config, poll_interval, label):
        self._path = path
        self._handler = handler
        self._gui_ref = gui_ref
        self._app_state = app_state
        self._config = config
        self._poll_interval = poll_interval
        self._label = label

        self._last_mtime = None
        self._last_error = None
        self._last_poll_ts = 0.0

    def _should_poll(self):
        now = time.time()
        if now - self._last_poll_ts < self._poll_interval:
            return False
        self._last_poll_ts = now
        return True

    def _log_once(self, msg):
        if msg != self._last_error:
            self._last_error = msg
            MSG_QUEUE.put(("log", f"[WATCHER-{self._label}] {msg}"))

    def _load_json_safely(self):
        """
        Próbuje wczytać JSON, ale nie robi TTS, jedynie pojedynczy log.
        """
        if not os.path.isfile(self._path):
            self._log_once(f"Plik nie istnieje: {self._path}")
            return None

        try:
            mtime = os.path.getmtime(self._path)
        except Exception as e:
            self._log_once(f"Nie mogę pobrać mtime: {e}")
            return None

        if self._last_mtime == mtime:
            return None  # brak zmian

        self._last_mtime = mtime

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self._log_once(f"Błąd JSON/I/O: {e}")
            return None


class StatusWatcher(BaseWatcher):
    def __init__(self, handler, gui_ref, app_state, config):
        super().__init__(
            path=status_path(),
            handler=handler,
            gui_ref=gui_ref,
            app_state=app_state,
            config=config,
            poll_interval=config.get("status_poll_interval", 0.5),
            label="STATUS"
        )

    def poll(self):
        if not self._should_poll():
            return

        data = self._load_json_safely()
        if data is None:
            return

        # Czyste API → przekazujemy dict
        try:
            self._handler.on_status_update(data, self._gui_ref)
        except Exception:
            pass


class MarketWatcher(BaseWatcher):
    def __init__(self, handler, gui_ref, app_state, config):
        super().__init__(
            path=market_path(),
            handler=handler,
            gui_ref=gui_ref,
            app_state=app_state,
            config=config,
            poll_interval=config.get("market_poll_interval", 1.0),
            label="MARKET"
        )

    def poll(self):
        if not self._should_poll():
            return

        data = self._load_json_safely()
        if data is None:
            return

        try:
            self._handler.on_market_update(data, self._gui_ref)
        except Exception:
            pass
