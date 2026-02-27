# app/route_manager.py

from __future__ import annotations

import threading
from typing import Callable, Iterable, Optional, Any

from logic.utils.renata_log import log_event, log_event_throttled


class RouteManager:
    """Centralny menedżer tras dla Renaty.

    Dwie odpowiedzialności:

    1) Nawigacja po JUŻ WYZNACZONEJ TRASIE
       - trzymanie listy systemów,
       - bieżący indeks,
       - prosty log do MSG_QUEUE.

    2) Cienka warstwa uruchamiania jobów tras (D2-A)
       - startuje wątki robocze dla tras (neutron, riches, trade itd.),
       - trzyma prosty stan *busy* / *current_mode*,
       - sygnalizuje do logów początek i koniec obliczania trasy.

    Uwaga: RouteManager *nie* zna szczegółów SPANSH, payloadów ani JSON-ów.
    Worker przekazany do start_route_thread odpowiada za:
    - rozmowę ze SpanshClientem / backendem,
    - ustawienie trasy przez set_route(...),
    - aktualizację GUI (MSG_QUEUE, listboxy itd.).
    """

    # ---------------------------------------------------------
    #  Konstruktor
    # ---------------------------------------------------------

    def __init__(self, *, route_job_timeout_s: float = 120.0) -> None:
        # Nawigacja po trasie
        self.lock = threading.Lock()
        self.route: list[str] = []
        self.route_type: Optional[str] = None
        self.current_index: int = 0

        # Lifecycle jobów tras (D2-A)
        self._busy: bool = False
        self._current_mode: Optional[str] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._active_job_token: int = 0
        self._route_job_timeout_s: float = max(0.0, float(route_job_timeout_s or 0.0))

    # ---------------------------------------------------------
    #  API: zarządzanie trasą (nawigacja)
    # ---------------------------------------------------------

    def set_route(self, route_list: Iterable[str], route_type: str) -> None:
        """Ustawia nową trasę i resetuje indeks.

        :param route_list: iterowalna lista nazw systemów (str)
        :param route_type: np. 'neutron', 'riches', 'ammonia', 'trade'
        """
        route_list = list(route_list or [])

        with self.lock:
            self.route = route_list
            self.route_type = route_type
            self.current_index = 0

        log_event(
            "PLANNER",
            "route_set",
            route_type=route_type,
            route_len=len(route_list),
        )

    def clear_route(self) -> None:
        """Czyści aktualną trasę i resetuje stan nawigacji."""
        with self.lock:
            self.route = []
            self.route_type = None
            self.current_index = 0

        log_event("PLANNER", "route_cleared")

    def get_next_system(self, current_system: Optional[str]) -> Optional[str]:
        """Zwraca kolejny system na trasie, NIE zmieniając current_index.

        Logika:
        - jeśli trasa jest pusta → None
        - jeśli current_system jest na trasie → zwraca system po nim
        - jeśli current_system nie jest na trasie → zwraca system z current_index
        - jeśli jesteśmy na końcu trasy → None
        """
        with self.lock:
            if not self.route:
                return None

            # Domyślnie bierzemy to, gdzie jesteśmy wg current_index
            idx = self.current_index

            if current_system:
                try:
                    idx = self.route.index(current_system) + 1
                except ValueError:
                    # current_system nie ma na trasie – zostajemy przy current_index
                    log_event_throttled(
                        "route_manager_current_system_not_in_route",
                        15.0,
                        "INFO",
                        "route_manager current_system not found on route; using current_index",
                        current_system=current_system,
                        current_index=self.current_index,
                        route_len=len(self.route),
                        route_type=self.route_type or "",
                    )

            if idx < len(self.route):
                return self.route[idx]

            return None

    def advance_route(self, current_system: Optional[str]) -> Optional[str]:
        """Przesuwa current_index do przodu i zwraca nowy 'next system'.

        Logika:
        - jeśli current_system jest na trasie → current_index := index(current_system) + 1
        - jeśli current_system nie jest na trasie → current_index += 1 (jeśli się da)
        - jeśli trasa pusta lub jesteśmy za końcem → None
        """
        with self.lock:
            if not self.route:
                return None

            if current_system:
                try:
                    self.current_index = self.route.index(current_system) + 1
                except ValueError:
                    # current_system nie ma na trasie – idziemy o 1 do przodu, jeśli możemy
                    if self.current_index < len(self.route):
                        self.current_index += 1
            else:
                if self.current_index < len(self.route):
                    self.current_index += 1

            # clamp + sprawdzenie końca trasy
            if self.current_index >= len(self.route):
                log_event("PLANNER", "route_end")
                # reset route state after completion
                self.route = []
                self.route_type = None
                self.current_index = 0
                return None

            next_sys = self.route[self.current_index]

        log_event("PLANNER", "route_next_system", next_system=next_sys)
        return next_sys

    # ---------------------------------------------------------
    #  API: lifecycle jobów tras (threading / busy)
    # ---------------------------------------------------------

    def is_busy(self) -> bool:
        """Zwraca True, jeśli *jakikolwiek* job trasy jest w toku.

        Uwaga: to prosta flaga, nie ma tu zarządzania kolejką jobów.
        """
        with self.lock:
            return self._busy

    def current_mode(self) -> Optional[str]:
        """Zwraca tryb aktualnie liczonej trasy (np. 'neutron', 'riches') lub None."""
        with self.lock:
            return self._current_mode

    def start_route_thread(
        self,
        mode: str,
        target: Callable[..., Any],
        *,
        args: tuple = (),
        gui_ref: Any | None = None,
    ) -> bool:
        """Uruchamia job trasy w osobnym wątku.

        - *nie* zna szczegółów SPANSH,
        - odpowiada tylko za:
          • ustawienie flag busy / current_mode,
          • wystartowanie wątku,
          • zalogowanie początku i końca joba.

        Docelowy worker (target) powinien:
        - wywołać backend (SpanshClient / logika routes),
        - ustawić trasę przez set_route(...),
        - wrzucić odpowiednie komunikaty do MSG_QUEUE / zaktualizować GUI.
        """

        _ = gui_ref
        mode_text = str(mode or "").strip() or "unknown"

        with self.lock:
            if self._busy:
                log_event_throttled(
                    "route_job_start_rejected_busy",
                    5000,
                    "PLANNER",
                    "route job start rejected because another job is busy",
                    requested_mode=mode_text,
                    busy_mode=str(self._current_mode or ""),
                )
                return False
            self._busy = True
            self._current_mode = mode_text
            self._active_job_token += 1
            job_token = int(self._active_job_token)

        def _runner(token: int, mode_name: str) -> None:
            try:
                target(*args)
            except Exception as exc:
                log_event_throttled(
                    "route_job_worker_exception",
                    2000,
                    "PLANNER",
                    "route job worker raised exception",
                    mode=mode_name,
                    error=f"{type(exc).__name__}: {exc}",
                )
            finally:
                # Koniec joba – reset stanu busy
                should_emit_done = False
                with self.lock:
                    if self._active_job_token == token:
                        self._busy = False
                        self._current_mode = None
                        self._worker_thread = None
                        should_emit_done = True
                if should_emit_done:
                    log_event("PLANNER", "route_job_done", mode=mode_name)


        # Prosty log dla diagnostyki (nie zmienia UX zakładek)
        log_event("PLANNER", "route_job_start", mode=mode_text)
        t = threading.Thread(
            target=_runner,
            args=(job_token, mode_text),
            daemon=True,
            name=f"route_job:{mode_text}:{job_token}",
        )
        t.start()

        with self.lock:
            self._worker_thread = t
        self._start_route_job_watchdog(mode=mode_text, token=job_token, worker=t)
        return True

    def _start_route_job_watchdog(self, *, mode: str, token: int, worker: threading.Thread) -> None:
        timeout_s = float(self._route_job_timeout_s or 0.0)
        if timeout_s <= 0.0:
            return

        def _watchdog() -> None:
            try:
                worker.join(timeout=timeout_s)
            except Exception:
                return
            if not worker.is_alive():
                return
            with self.lock:
                if self._active_job_token != token:
                    return
                self._busy = False
                self._current_mode = None
                self._worker_thread = None
            log_event_throttled(
                "route_job_timeout",
                2000,
                "PLANNER",
                "route job exceeded timeout and was detached from busy state",
                mode=mode,
                timeout_s=timeout_s,
            )

        threading.Thread(
            target=_watchdog,
            daemon=True,
            name=f"route_watchdog:{mode}:{token}",
        ).start()

    def cancel_route(self) -> None:
        """Placeholder pod ewentualne anulowanie trasy w przyszłości.

        Aktualnie nie ma bezpiecznego sposobu na przerwanie wątku obliczeń
        (standardowe ograniczenie Pythona), więc metoda jedynie loguje zamiast
        próbować ubijać wątek na siłę.
        """
        log_event("PLANNER", "route_cancel_ignored")


# Globalny, współdzielony menedżer dla całej aplikacji
route_manager = RouteManager()
