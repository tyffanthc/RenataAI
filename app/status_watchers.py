import os
import time
import json

from logic.utils import powiedz
from logic.events.files import status_path, market_path, cargo_path, navroute_path
from logic.utils.renata_log import log_event_throttled


class BaseWatcher:
    """
    WspĂłlna logika poll() dla StatusWatcher i MarketWatcher.
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
            log_event_throttled(
                f"watcher.{self._label}",
                2000,
                f"WATCHER-{self._label}",
                msg,
            )

    def _load_json_safely(self):
        """
        PrĂłbuje wczytaÄ‡ JSON, ale nie robi TTS, jedynie pojedynczy log.
        """
        if not os.path.isfile(self._path):
            self._log_once("Plik watchera chwilowo niedostepny.")
            return None

        try:
            mtime = os.path.getmtime(self._path)
        except Exception as e:
            self._log_once("Plik watchera chwilowo niedostepny (mtime).")
            return None

        if self._last_mtime == mtime:
            return None  # brak zmian

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Update mtime only after successful parse. Otherwise a transient
            # JSONDecodeError (file being rewritten) would mark this version as
            # "already seen" and the next poll would skip a valid retry.
            self._last_mtime = mtime
            return data
        except json.JSONDecodeError as e:
            # Typical transient case: file is currently being rewritten by ED.
            if getattr(e, "pos", None) == 0:
                self._log_once("Plik chwilowo niegotowy (trwa zapis).")
            else:
                self._log_once("Plik chwilowo nieczytelny (niepelny JSON).")
            return None
        except OSError as e:
            self._log_once("Odczyt chwilowo nieudany (I/O).")
            return None
        except Exception as e:
            self._log_once("Niekrytyczny problem odczytu JSON.")
            return None

    def _log_dispatch_soft_failure(self, event_kind: str) -> None:
        kind = str(event_kind or "update").strip().lower() or "update"
        label = str(self._label or "WATCHER").strip().upper() or "WATCHER"
        log_event_throttled(
            f"WATCHER_DISPATCH_{label}_{kind.upper()}",
            120_000,
            "WARN",
            f"{label} watcher: dispatch {kind} failed",
            context=f"watcher.{label.lower()}.dispatch:{kind}",
        )


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

        # Czyste API â†’ przekazujemy dict
        try:
            self._handler.on_status_update(data, self._gui_ref)
        except Exception:
            self._log_dispatch_soft_failure("status_update")


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
            self._log_dispatch_soft_failure("market_update")


class CargoWatcher(BaseWatcher):
    def __init__(self, handler, gui_ref, app_state, config):
        super().__init__(
            path=cargo_path(),
            handler=handler,
            gui_ref=gui_ref,
            app_state=app_state,
            config=config,
            poll_interval=config.get("status_poll_interval", 0.5),
            label="CARGO"
        )

    def poll(self):
        if not self._should_poll():
            return

        data = self._load_json_safely()
        if data is None:
            return

        try:
            self._handler.on_cargo_update(data, self._gui_ref)
        except Exception:
            self._log_dispatch_soft_failure("cargo_update")


class NavRouteWatcher(BaseWatcher):
    def __init__(self, handler, gui_ref, app_state, config):
        super().__init__(
            path=navroute_path(),
            handler=handler,
            gui_ref=gui_ref,
            app_state=app_state,
            config=config,
            poll_interval=config.get("status_poll_interval", 0.5),
            label="NAVROUTE",
        )

    def poll(self):
        if not self._should_poll():
            return

        data = self._load_json_safely()
        if data is None:
            return

        try:
            self._handler.on_navroute_update(data, self._gui_ref)
        except Exception:
            self._log_dispatch_soft_failure("navroute_update")

