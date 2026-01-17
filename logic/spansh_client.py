"""
Warstwa HTTP do wszystkich zapytań SPANSH.

Zasady:
- JEDYNE miejsce w projekcie, gdzie robimy requests.* na spansh.co.uk.
- Wspólny HEADERS (używany także przez inne moduły, np. generate_renata_science_data).
- Konfiguracja timeout / retries / poll interval brana z user_settings.json
  (klucze: spansh_timeout, spansh_retries).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests
import config

from logic.utils.notify import powiedz, DEBOUNCER
from logic.request_dedup import make_request_key, run_deduped


# --- Nagłówki HTTP używane do wszystkich zapytań SPANSH ---------------------

HEADERS: Dict[str, str] = {
    "User-Agent": (
        "RENATA/1.0 "
        "(R.E.N.A.T.A. - Route Engine & Navigation Automated Trade Assistant; "
        "contact: tyffanthc@gmail.com)"
    ),
    "Accept": "application/json",
    "From": "tyffanthc@gmail.com",
}


# --- Wspólny helper do obsługi błędów SPANSH --------------------------------


def spansh_error(message: str, gui_ref: Any | None = None, *, context: str | None = None) -> None:
    """
    Standaryzowany helper do zgłaszania błędów SPANSH.

    - Używa globalnego DEBOUNCER, żeby nie floodować GUI/tts identycznymi komunikatami.
    - Wszystkie błędy HTTP/SPANSH z warstwy backendowej powinny przechodzić przez to miejsce.
    """
    key = "spansh_error"
    if context:
        key = f"{key}:{context}"

    # delikatny cooldown – ten sam błąd max raz na kilka sekund
    if not DEBOUNCER.is_allowed(key, cooldown_sec=5.0, context=context):
        return

    powiedz(message, gui_ref)


class SpanshClient:
    """
    Wspólny klient do wszystkich jobów Spansh:
    - POST /api/<mode>/route          (riches/ammonia/elw/hmc/exomastery/trade)
    - POST /api/route                 (neutron plotter)
    - GET  /api/results/<job>         (polling jobów)
    - GET  /api/systems               (autocomplete systemów)
    - GET  /api/stations              (autocomplete stacji – D3b)

    Wartości timeout / retries / poll interval są konfigurowalne przez GUI.
    """

    def __init__(self) -> None:
        # domyślne wartości; zostaną nadpisane w _reload_config()
        self.base_url: str = "https://spansh.co.uk/api"
        self.default_timeout: float = 20.0
        self.default_retries: int = 3
        self.default_poll_interval: float = 2.0
        self._reload_config()

    # ------------------------------------------------------------------ public

    def systems_suggest(self, q: str) -> List[str]:
        """
        Autocomplete systemów:
        -> GET /api/systems?q=<tekst>
        Zwraca listę nazw systemów (unikalnych).
        """
        q = (q or "").strip()
        if q.startswith("-"):
            q = q[1:].strip()

        if not q:
            return []

        # prosty anti-spam – jeśli użytkownik trzyma klawisz, nie spamujemy API
        if not DEBOUNCER.is_allowed(
            key="spansh_autocomplete",
            cooldown_sec=0.8,
            context=q.lower(),
        ):
            return []

        self._reload_config()

        url = f"{self.base_url}/systems"
        headers = self._headers(referer="https://spansh.co.uk")

        for attempt in range(max(1, self.default_retries)):
            try:
                res = requests.get(
                    url,
                    params={"q": q},
                    headers=headers,
                    timeout=self.default_timeout,
                )
            except Exception as e:  # noqa: BLE001
                # Autocomplete traktujemy łagodnie – log tylko do konsoli.
                print(f"[Spansh] Autocomplete exception ({q!r}): {e}")
                return []

            if res.status_code == 200:
                try:
                    data = res.json()
                except Exception as e:  # noqa: BLE001
                    print(f"[Spansh] Autocomplete JSON error ({q!r}): {e}")
                    return []

                names: List[str] = []

                # Spansh historycznie zwracał zarówno listy dictów jak i inne formaty.
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("system")
                        else:
                            name = str(item)
                        if name and name not in names:
                            names.append(str(name))
                elif isinstance(data, dict):
                    # e.g. {"systems": [...]} – na wszelki wypadek
                    systems = data.get("systems") or data.get("result") or []
                    for item in systems:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("system")
                        else:
                            name = str(item)
                        if name and name not in names:
                            names.append(str(name))

                print(f"[Spansh] '{q}' → {len(names)} wyników")
                return names

            # inne kody HTTP – dla autocomplete nie robimy retry w nieskończoność
            print(f"[Spansh] HTTP {res.status_code} dla '{q}' (autocomplete)")
            if res.status_code in (400, 401, 403, 404):
                break

        return []

    def stations_for_system(self, system: str, q: Optional[str] = None) -> List[str]:
        """
        Autocomplete STACJI dla danego systemu (D3b):
        -> GET /api/stations?system=<system>[&q=<prefix>]

        Zwraca listę nazw stacji (unikalnych, ograniczoną do kilkudziesięciu pozycji).
        """
        system = (system or "").strip()
        if not system:
            return []

        q = (q or "").strip()

        # Anti-spam – debouncer z kontekstem (system + prefix)
        ctx = f"{system.lower()}|{q.lower()}" if q else system.lower()
        if not DEBOUNCER.is_allowed(
            key="spansh_stations",
            cooldown_sec=0.8,
            context=ctx,
        ):
            return []

        self._reload_config()

        url = f"{self.base_url}/stations"
        params: Dict[str, Any] = {"system": system}
        if q:
            params["q"] = q

        headers = self._headers(referer="https://spansh.co.uk/trade")

        for attempt in range(max(1, self.default_retries)):
            try:
                res = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.default_timeout,
                )
            except Exception as e:  # noqa: BLE001
                print(f"[Spansh] Stations exception ({system!r}, {q!r}): {e}")
                return []

            if res.status_code == 200:
                try:
                    data = res.json()
                except Exception as e:  # noqa: BLE001
                    print(f"[Spansh] Stations JSON error ({system!r}, {q!r}): {e}")
                    return []

                names: List[str] = []

                # Spansh może zwracać listę dictów lub dict z polem 'stations' / 'result'
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("stations") or data.get("result") or data.get("bodies") or []
                else:
                    items = []

                for item in items:
                    name: Optional[str] = None
                    if isinstance(item, str):
                        name = item
                    elif isinstance(item, dict):
                        name = (
                            item.get("name")
                            or item.get("station")
                            or item.get("body")
                            or item.get("label")
                        )

                    if not name:
                        continue

                    if name not in names:
                        names.append(str(name))

                # Bezpieczny limit – żeby nie zalewać listboxa setkami pozycji
                if len(names) > 50:
                    names = names[:50]

                print(f"[Spansh] stations '{system}' ('{q}') → {len(names)} wyników")
                return names

            print(
                f"[Spansh] HTTP {res.status_code} dla stations(system={system!r}, q={q!r})"
            )
            if res.status_code in (400, 401, 403, 404):
                break

        return []

    def route(
        self,
        mode: str,
        payload: Dict[str, Any],
        referer: str,
        gui_ref: Any | None = None,
        poll_seconds: Optional[float] = None,
        polls: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Ogólny klient jobowy:
        - riches / ammonia / elw / hmc / exomastery / trade
        - neutron (przez specjalny path)

        Zwraca js.get("result", ...) lub None jeśli błąd.
        """
        self._reload_config()

        poll_seconds = poll_seconds or self.default_poll_interval
        polls = polls or 60

        # neutron plotter ma inny path niż pozostałe
        if mode in ("neutron", "route"):
            path = "/route"
        else:
            path = f"/{mode}/route"

        url = f"{self.base_url}{path}"
        headers = self._headers(referer=referer)

        dedup_key = make_request_key(
            "spansh",
            path,
            {"mode": mode, "payload": payload},
        )

        # --- Job request ------------------------------------------------------
        # SPANSH oczekuje form-data (application/x-www-form-urlencoded),
        # a nie JSON. Dodatkowo niektóre pola (np. body_types) mogą
        # występować wielokrotnie — wtedy payload trzymamy jako listę.

        def _do_request() -> Optional[Any]:
            # Anti-spam dla tras — jeżeli ktoś spamuje przyciskiem,
            # nie odpalamy wielu jobów naraz.
            if not DEBOUNCER.is_allowed("spansh_route", cooldown_sec=1.0, context=mode):
                spansh_error("Odczekaj chwilę przed kolejnym zapytaniem SPANSH.", gui_ref, context=mode)
                return None

            data: List[tuple[str, Any]] = []
            for key, value in payload.items():
                if isinstance(value, list):
                    for item in value:
                        data.append((key, item))
                else:
                    data.append((key, value))

            try:
                r = requests.post(
                    url,
                    data=data,
                    headers=headers,
                    timeout=self.default_timeout,
                )
            except Exception as e:  # noqa: BLE001
                spansh_error(
                    f"{mode.upper()}: wyjątek HTTP przy wysyłaniu joba ({e})",
                    gui_ref,
                    context=mode,
                )
                return None

            if r.status_code not in (200, 202):
                # prosty debug do loga konsoli — widzimy treść błędu z SPANSH
                try:
                    print(f"[Spansh] {mode} HTTP {r.status_code} body: {r.text}")
                except Exception:
                    pass

                spansh_error(
                    f"{mode.upper()}: HTTP {r.status_code} przy wysyłaniu joba.",
                    gui_ref,
                    context=mode,
                )
                return None

            try:
                job = r.json().get("job")
            except Exception as e:  # noqa: BLE001
                spansh_error(
                    f"{mode.upper()}: niepoprawny JSON przy tworzeniu joba ({e}).",
                    gui_ref,
                    context=mode,
                )
                return None

            if not job:
                spansh_error(
                    f"{mode.upper()}: brak job ID w odpowiedzi.",
                    gui_ref,
                    context=mode,
                )
                return None

            # --- Polling ---------------------------------------------------------

            js = self._poll_results(job, mode=mode, gui_ref=gui_ref, poll_seconds=poll_seconds, polls=polls)
            if js is None:
                return None

            # Standard: w JSON-ie jest pole "result"
            if isinstance(js, dict):
                return js.get("result", [])
            return js

        try:
            return run_deduped(dedup_key, _do_request)
        except Exception:
            return None

    def neutron_route(
        self,
        start: str,
        cel: str,
        zasieg: float,
        eff: float,
        gui_ref: Any | None = None,
        *,
        return_details: bool = False,
    ) -> List[str] | tuple[List[str], List[dict[str, Any]]]:
        """
        Wersja dedykowana dla Neutron Plottera.

        Zachowuje zachowanie starego oblicz_spansh, ale przenosi HTTP do klienta
        i respektuje ustawienia timeout / retries.
        """
        start = (start or "").strip()
        cel = (cel or "").strip()

        if not start or not cel:
            spansh_error("NEUTRON: brak systemu startowego lub docelowego.", gui_ref, context="neutron")
            return []

        payload = {
            "efficiency": str(eff),
            "range": str(zasieg),
            "from": start,
            "to": cel,
        }

        # neutron używa /api/route
        result = self.route(
            mode="neutron",
            payload=payload,
            referer="https://spansh.co.uk/plotter",
            gui_ref=gui_ref,
        )
        if not result:
            return ([], []) if return_details else []

        # Spansh dla plottera zwykle zwraca result.system_jumps: [...]
        if isinstance(result, dict):
            jumps = result.get("system_jumps", [])
        else:
            jumps = result

        def _pick(entry: dict[str, Any], keys: list[str]) -> Any:
            for key in keys:
                val = entry.get(key)
                if val is not None and val != "":
                    return val
            return None

        systems: List[str] = []
        details: List[dict[str, Any]] = []
        for entry in jumps or []:
            if isinstance(entry, dict):
                name = _pick(entry, ["system", "name", "system_name"])
                details.append(
                    {
                        "system": name,
                        "distance": _pick(
                            entry,
                            [
                                "distance",
                                "distance_ly",
                                "distance_to_next",
                                "distance_to_arrival",
                                "distance_to_next_jump",
                                "distance_to_next_system",
                            ],
                        ),
                        "remaining": _pick(
                            entry,
                            [
                                "remaining",
                                "remaining_distance",
                                "remaining_ly",
                                "remaining_distance_ly",
                                "remaining_to_destination",
                                "distance_remaining",
                            ],
                        ),
                        "neutron": _pick(
                            entry,
                            [
                                "neutron",
                                "is_neutron",
                                "neutron_star",
                                "neutron_jump",
                            ],
                        ),
                        "jumps": _pick(
                            entry,
                            [
                                "jumps",
                                "jump_count",
                                "jumps_remaining",
                            ],
                        ),
                    }
                )
            else:
                name = str(entry)
            if name:
                systems.append(str(name))

        if return_details:
            return systems, details
        return systems

    # ----------------------------------------------------------------- helpers

    def _reload_config(self) -> None:
        """
        Ładuje ustawienia SPANSH z configu.

        user_settings.json:
          - spansh_timeout  -> sekundy
          - spansh_retries  -> liczba ponowień przy problemach HTTP
        """
        try:
            cfg = config.SETTINGS  # snapshot słownika
        except Exception:  # noqa: BLE001
            cfg = {}

        try:
            timeout_raw = cfg.get("spansh_timeout", 20)
            retries_raw = cfg.get("spansh_retries", 3)

            self.default_timeout = float(timeout_raw) if timeout_raw not in (None, "") else 20.0
            self.default_retries = int(retries_raw) if retries_raw not in (None, "") else 3
        except Exception:  # noqa: BLE001
            self.default_timeout = 20.0
            self.default_retries = 3

        # Dla przejrzystości trzymamy też base_url i poll_interval jako pola.
        self.base_url = cfg.get("spansh_base_url", "https://spansh.co.uk/api")
        # Poll interval raczej nie będzie konfigurowany, ale trzymamy w jednym miejscu.
        self.default_poll_interval = 2.0

    def _poll_results(
        self,
        job: str,
        *,
        mode: str,
        gui_ref: Any | None,
        poll_seconds: float,
        polls: int,
    ) -> Optional[Any]:
        """
        Polling wyniku joba:
        GET /api/results/<job>
        """
        url = f"{self.base_url}/results/{job}"
        headers = self._headers(referer="https://spansh.co.uk")

        for _ in range(polls):
            try:
                r = requests.get(
                    url,
                    headers=headers,
                    timeout=self.default_timeout,
                )
            except Exception as e:  # noqa: BLE001
                spansh_error(f"{mode.upper()}: wyjątek przy pobieraniu wyników ({e}).", gui_ref, context=mode)
                return None

            if r.status_code == 202:

                time.sleep(poll_seconds)

                continue


            if r.status_code != 200:
                spansh_error(f"{mode.upper()}: HTTP {r.status_code} przy pobieraniu wyników.", gui_ref, context=mode)
                return None

            try:
                js = r.json()
            except Exception as e:  # noqa: BLE001
                spansh_error(f"{mode.upper()}: niepoprawny JSON w wynikach ({e}).", gui_ref, context=mode)
                return None

            status = js.get("status")
            if status in ("queued", "running"):
                time.sleep(poll_seconds)
                continue

            if status != "ok":
                spansh_error(f"{mode.upper()}: status joba = {status!r}.", gui_ref, context=mode)
                return None

            return js

        spansh_error(f"{mode.upper()}: timeout pollingu wyników.", gui_ref, context=mode)
        return None

    def _headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """
        Buduje nagłówki dla zapytań SPANSH:
        - bazuje na globalnym HEADERS (User-Agent R.E.N.A.T.A.)
        - opcjonalnie dokleja Referer, jeśli podany
        """
        headers = dict(HEADERS)  # kopia, żeby nie mutować globalnego dict
        if referer:
            headers["Referer"] = referer
        return headers


# Singleton – prosty, ale wystarczający na potrzeby Renaty v90
client = SpanshClient()
