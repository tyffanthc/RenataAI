import time
import os
import glob
from collections import deque

from logic.event_handler import handler
from logic.utils import powiedz, MSG_QUEUE
from logic.insight_dispatcher import emit_insight
from app.state import app_state
import config

from app.status_watchers import StatusWatcher, MarketWatcher, CargoWatcher, NavRouteWatcher
from logic.utils.renata_log import log_event_throttled


class MainLoop:
    """
    Czyta Elite Dangerous Journal.
    """

    def __init__(self, gui_ref, log_dir):
        self.gui_ref = gui_ref
        self.log_dir = log_dir

        # Watchery Status + Market
        self.status_watcher = StatusWatcher(
            handler, gui_ref, app_state, config
        )
        self.market_watcher = MarketWatcher(
            handler, gui_ref, app_state, config
        )
        self.cargo_watcher = CargoWatcher(
            handler, gui_ref, app_state, config
        )
        self.navroute_watcher = NavRouteWatcher(
            handler, gui_ref, app_state, config
        )

        self._last_error_msg = None  # anti-spam
        self._startup_waiting_logged = False

        try:
            if hasattr(handler, "log_dir"):
                handler.log_dir = log_dir
        except Exception:
            log_event_throttled(
                "MAINLOOP_HANDLER_LOGDIR_SET_FAILED",
                120_000,
                "WARN",
                "MainLoop: failed to set handler.log_dir",
                context="main_loop.handler.log_dir",
            )

    def _emit_runtime_critical(self, raw_text: str, *, component: str) -> None:
        text = str(raw_text or "").strip()
        if not text:
            return
        try:
            emit_insight(
                text,
                gui_ref=self.gui_ref,
                message_id="MSG.RUNTIME_CRITICAL",
                source="main_loop",
                event_type="RUNTIME_FAILURE",
                context={
                    "raw_text": text,
                    "system": str(getattr(app_state, "current_system", "") or "").strip() or "unknown",
                    "component": str(component or "").strip() or "runtime",
                },
                priority="P0_CRITICAL",
                dedup_key=f"runtime_critical:{component}",
                cooldown_scope="entity",
                cooldown_seconds=120.0,
            )
        except Exception:
            log_event_throttled(
                "MAINLOOP_RUNTIME_CRITICAL_EMIT_FAILED",
                120_000,
                "WARN",
                "MainLoop: runtime critical insight emit failed",
                context=f"main_loop.runtime_critical.emit:{component}",
            )
            return

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        powiedz(f"Podpinam się pod logi ED: {self.log_dir}", self.gui_ref)

        while True:
            path = self._find_latest_file()

            if not path:
                powiedz(
                    "Nie widzę Journal.*.log w LOG_DIR. Czekam na nowy log...",
                    self.gui_ref,
                )
                self._emit_runtime_critical(
                    "Brak aktywnego pliku journala. Czekam na dane z gry.",
                    component="journal_stream",
                )
                time.sleep(2)
                continue

            powiedz(f"Używam logu: {os.path.basename(path)}", self.gui_ref)

            self._bootstrap_state(path)
            self._tail_file(path)

    # ------------------------------------------------------------------ #
    def _bootstrap_state(self, path, max_lines: int = 8000) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                # Keep only the tail needed for bootstrap to avoid loading the whole Journal into RAM.
                lines = list(deque(f, maxlen=max_lines))
        except FileNotFoundError:
            self._log_error("Bootstrap: Journal zniknął przed odczytem - spróbuję ponownie.")
            return
        except Exception as e:
            self._log_error(f"Bootstrap error: {e}")
            return

        try:
            from logic.events import exploration_bio_events

            exploration_bio_events.bootstrap_exobio_state_from_journal_lines(
                lines,
                max_lines=max_lines,
            )
        except Exception as e:
            self._log_error(f"Bootstrap exobio recovery error: {e}")
        try:
            from logic.events import exploration_value_recovery

            recovery_stats = exploration_value_recovery.bootstrap_system_value_from_journal_lines(
                lines,
                max_lines=max_lines,
            )
            if isinstance(recovery_stats, dict):
                diag_lines = list(recovery_stats.get("diagnostics") or [])
                if diag_lines:
                    MSG_QUEUE.put(("log", "[BOOTSTRAP] Value recovery: " + " | ".join(str(x) for x in diag_lines)))
        except Exception as e:
            self._log_error(f"Bootstrap value recovery error: {e}")

        app_state.bootstrap_replay = True

        for line in reversed(lines):
            if '"event":"Loadout"' in line:
                try:
                    handler.handle_event(line, self.gui_ref)
                    powiedz("Bootstrap: ustawiono statek z Loadout.", self.gui_ref)
                except Exception as e:
                    self._log_error(f"Bootstrap loadout error: {e}")
                break

        for line in reversed(lines):
            if (
                '"event":"Location"' in line
                or '"event":"FSDJump"' in line
                or '"event":"CarrierJump"' in line
            ):
                try:
                    handler.handle_event(line, self.gui_ref)
                    powiedz("Bootstrap: ustawiono aktualny system z logu.", self.gui_ref)
                except Exception as e:
                    self._log_error(f"Bootstrap handler error: {e}")
                app_state.bootstrap_replay = False
                return

        self._announce_waiting_for_system()
        app_state.bootstrap_replay = False

    # ------------------------------------------------------------------ #
    def _tail_file(self, path) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)

                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.3)

                        # Poll status/market/cargo even when Journal is idle.
                        # Exobio distance cues depend on live Status.json updates.
                        self.status_watcher.poll()
                        self.market_watcher.poll()
                        self.cargo_watcher.poll()
                        self.navroute_watcher.poll()

                        newer = self._find_latest_file()
                        if newer and newer != path:
                            powiedz(
                                f"Znalazłem nowszy log: {os.path.basename(newer)} - przełączam się.",
                                self.gui_ref,
                            )
                            return
                        continue

                    try:
                        handler.handle_event(line, self.gui_ref)
                    except Exception as e:
                        self._log_error(f"[EventHandler error] {e}")

                    # *** NOWE POLLOWANIE WATCHERĂ“W ***
                    self.status_watcher.poll()
                    self.market_watcher.poll()
                    self.cargo_watcher.poll()
                    self.navroute_watcher.poll()

        except FileNotFoundError:
            self._log_error("Tail: Journal został usunięty - szukam nowego pliku.")
            self._emit_runtime_critical(
                "Utracono strumien journala. Szukam nowego pliku.",
                component="journal_stream",
            )
        except Exception as e:
            self._log_error(f"[BŁĄD MainLoop/tail] {e}")
            self._emit_runtime_critical(
                "Błąd krytyczny czytania journala. Sprawdź panel statusu.",
                component="journal_stream",
            )
            time.sleep(1)

    # ------------------------------------------------------------------ #
    def _find_latest_file(self):
        try:
            if not self.log_dir or not os.path.isdir(self.log_dir):
                return None

            pattern = os.path.join(self.log_dir, "Journal.*.log")
            files = [p for p in glob.glob(pattern) if os.path.isfile(p)]
            if not files:
                return None

            files.sort(key=os.path.getmtime, reverse=True)
            return files[0]
        except Exception as e:
            self._log_error(f"[Journal] Błąd wyszukiwania: {e}")
            return None

    # ------------------------------------------------------------------ #
    def _log_error(self, msg: str) -> None:
        if not msg or msg == self._last_error_msg:
            return
        self._last_error_msg = msg
        powiedz(msg, self.gui_ref)

    def _announce_waiting_for_system(self) -> None:
        if self._startup_waiting_logged:
            return
        self._startup_waiting_logged = True
        powiedz(
            "Oczekiwanie na dane z gry (Location/FSDJump).",
            self.gui_ref,
        )
