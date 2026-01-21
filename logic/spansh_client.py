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
from typing import Any, Dict, List, Optional, Tuple
import copy

import requests
import config

from logic.cache_store import CacheStore
from logic import spansh_payloads
from logic.spansh_payloads import SpanshPayload

from logic.utils.notify import powiedz, DEBOUNCER, MSG_QUEUE
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
    _emit_spansh_status(message, context=context)


def _emit_spansh_status(message: str, *, context: str | None) -> None:
    if not context:
        return
    ui_targets = {
        "neutron": "neu",
        "riches": "rtr",
        "ammonia": "amm",
        "elw": "rtr",
        "hmc": "rtr",
        "exomastery": "rtr",
        "trade": "trade",
    }
    target = ui_targets.get(context)
    if not target:
        return
    text = "Blad zapytania do Spansh."
    msg = (message or "").lower()
    if "timeout" in msg or "timed out" in msg:
        text = "Timeout - sprobuj ponownie."
    MSG_QUEUE.put((f"status_{target}", (text, "#ff5555")))


def resolve_planner_jump_range(
    requested_range: Any,
    *,
    gui_ref: Any | None = None,
    context: str | None = None,
) -> Optional[float]:
    if not config.get("planner_auto_use_ship_jump_range", True):
        try:
            return float(requested_range) if requested_range is not None else None
        except Exception:
            return None

    if requested_range is not None and config.get("planner_allow_manual_range_override", True):
        try:
            return float(requested_range)
        except Exception:
            return None

    try:
        from app.state import app_state

        jr = getattr(app_state.ship_state, "jump_range_current_ly", None)
    except Exception:
        jr = None

    if jr is not None:
        try:
            return float(jr)
        except Exception:
            return None

    try:
        fallback = float(config.get("planner_fallback_range_ly", 30.0))
    except Exception:
        fallback = 30.0

    if DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context=context or "spansh"):
        try:
            from gui import common as gui_common  # type: ignore

            gui_common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source=f"spansh.{context}" if context else "spansh",
                notify_overlay=True,
            )
        except Exception:
            MSG_QUEUE.put(("log", "[WARN] JR_NOT_READY_FALLBACK: Jump range fallback"))

    return fallback


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
        self.cache = CacheStore(namespace="spansh", provider="spansh")
        self._last_request: Dict[str, Any] = {}
        self._reload_config()
        use_edsm = bool(config.get("features.providers.edsm_enabled", False))

    def get_last_request(self) -> Dict[str, Any]:
        return copy.deepcopy(self._last_request or {})

    def _set_last_request(self, data: Dict[str, Any]) -> None:
        self._last_request = dict(data)

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
                if use_edsm:
                    try:
                        from logic.utils.http_edsm import edsm_systems_suggest
                        return edsm_systems_suggest(q)
                    except Exception:
                        return []
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
                if names:
                    return names
                if use_edsm:
                    try:
                        from logic.utils.http_edsm import edsm_systems_suggest
                        return edsm_systems_suggest(q)
                    except Exception:
                        return []
                return []

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
        payload: Any,
        referer: str,
        gui_ref: Any | None = None,
        poll_seconds: Optional[float] = None,
        polls: Optional[int] = None,
        endpoint_path: str | None = None,
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

        def _payload_to_fields(data: Any) -> List[Tuple[str, Any]]:
            if isinstance(data, SpanshPayload):
                return list(data.form_fields)
            if isinstance(data, list):
                return list(data)
            if isinstance(data, dict):
                fields: List[Tuple[str, Any]] = []
                for key, value in data.items():
                    if value is None:
                        continue
                    if isinstance(value, list):
                        for item in value:
                            if item is None:
                                continue
                            fields.append((key, item))
                    else:
                        fields.append((key, value))
                return fields
            return []

        def _fields_to_dict(fields: List[Tuple[str, Any]]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for key, value in fields:
                if key not in out:
                    out[key] = value
                else:
                    current = out[key]
                    if isinstance(current, list):
                        current.append(value)
                    else:
                        out[key] = [current, value]
            return out

        # neutron plotter ma inny path niż pozostałe
        if isinstance(payload, SpanshPayload):
            endpoint_path = payload.endpoint_path

        if endpoint_path:
            if not endpoint_path.startswith("/"):
                endpoint_path = f"/{endpoint_path}"
            path = endpoint_path
        elif mode in ("neutron", "route"):
            path = "/route"
        else:
            path = f"/{mode}/route"

        url = f"{self.base_url}{path}"
        headers = self._headers(referer=referer)
        if config.get("features.spansh.form_urlencoded_enabled", True):
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        def _normalize(value: Any) -> Any:
            if isinstance(value, float):
                return round(value, 4)
            if isinstance(value, dict):
                return {k: _normalize(value[k]) for k in sorted(value.keys())}
            if isinstance(value, list):
                return [_normalize(v) for v in value]
            if isinstance(value, str):
                return value.strip()
            return value

        payload_fields = _payload_to_fields(payload)
        norm_payload = [(k, _normalize(v)) for k, v in payload_fields]
        payload_dict = _fields_to_dict(payload_fields)
        cache_key = make_request_key(
            "spansh",
            path,
            {"mode": mode, "payload": norm_payload},
        )

        ttl_seconds = 7 * 24 * 3600
        start_ts = time.monotonic()
        if mode == "trade":
            ttl_seconds = 6 * 3600

        hit, cached, _meta = self.cache.get(cache_key)
        if hit:
            self._set_last_request({
                "timestamp": time.time(),
                "mode": mode,
                "endpoint": path,
                "url": url,
                "payload": payload_dict,
                "status": "CACHE_HIT",
                "response_ms": 0,
            })
            return cached

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

            try:
                if config.get("features.spansh.form_urlencoded_enabled", True):
                    r = requests.post(
                        url,
                        data=payload_fields,
                        headers=headers,
                        timeout=self.default_timeout,
                    )
                else:
                    r = requests.post(
                        url,
                        json=_fields_to_dict(payload_fields),
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
            result = run_deduped(cache_key, _do_request)
        except Exception:
            self._set_last_request({
                "timestamp": time.time(),
                "mode": mode,
                "endpoint": path,
                "url": url,
                "payload": payload_dict,
                "status": "ERROR",
                "response_ms": int((time.monotonic() - start_ts) * 1000),
            })
            return None

        if result is None:
            self._set_last_request({
                "timestamp": time.time(),
                "mode": mode,
                "endpoint": path,
                "url": url,
                "payload": payload_dict,
                "status": "ERROR",
                "response_ms": int((time.monotonic() - start_ts) * 1000),
            })
            return None

        if result is not None:
            status = "SUCCESS"
            if isinstance(result, list) and not result:
                status = "EMPTY"
            self._set_last_request({
                "timestamp": time.time(),
                "mode": mode,
                "endpoint": path,
                "url": url,
                "payload": payload_dict,
                "status": status,
                "response_ms": int((time.monotonic() - start_ts) * 1000),
            })
            self.cache.set(
                cache_key,
                result,
                ttl_seconds,
                meta={"provider": "spansh", "endpoint": path, "mode": mode},
            )

        return result

    def neutron_route(
        self,
        start: str,
        cel: str,
        zasieg: float,
        eff: float,
        gui_ref: Any | None = None,
        *,
        return_details: bool = False,
        supercharge_mode: str | None = None,
        via: List[str] | None = None,
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

        payload = spansh_payloads.build_neutron_payload(
            start=start,
            cel=cel,
            jump_range=zasieg,
            eff=eff,
            supercharge_mode=supercharge_mode,
            via=via,
        )

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
                if isinstance(val, dict):
                    for nested_key in ("value", "distance", "remaining", "ly"):
                        nested_val = val.get(nested_key)
                        if nested_val is not None and nested_val != "":
                            return nested_val
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
                                "dist",
                                "distance_ly",
                                "distance_to_next",
                                "distance_to_next_ly",
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
                                "remaining_to_destination_ly",
                                "remaining_to_destination",
                                "distance_left",
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
