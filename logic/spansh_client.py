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
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import copy

import requests
import config

from logic.cache_store import CacheStore
from logic import spansh_payloads
from logic.spansh_payloads import SpanshPayload

from logic.utils.notify import powiedz, DEBOUNCER, MSG_QUEUE
from logic.utils.http_edsm import is_edsm_enabled
from logic.utils.renata_log import log_event, log_event_throttled
from logic.request_dedup import make_request_key, run_deduped


# --- Nagłówki HTTP używane do wszystkich zapytań SPANSH ---------------------

HEADERS: Dict[str, str] = {
    "User-Agent": (
        "RENATA/1.0 "
        "(R.E.N.A.T.A. - Route, Exploration & Navigation Assistant for Trading & Analysis; "
        "contact: tyffanthc@gmail.com)"
    ),
    "Accept": "application/json",
    "From": "tyffanthc@gmail.com",
}


@dataclass(frozen=True)
class _RouteRequestContext:
    mode: str
    endpoint_path: str
    url: str
    headers: Dict[str, str]
    payload_fields: List[Tuple[str, Any]]
    payload_dict: Dict[str, Any]
    cache_key: str
    ttl_seconds: int
    debug_payload: Dict[str, Any] | None


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
        self._debug_cache_payloads: Dict[str, Dict[str, Any]] = {}
        self._reload_config()

    def get_last_request(self) -> Dict[str, Any]:
        return copy.deepcopy(self._last_request or {})

    def _set_last_request(self, data: Dict[str, Any]) -> None:
        self._last_request = dict(data)

    def _spansh_debug_enabled(self) -> bool:
        return bool(
            config.get("features.spansh.debug_payload", False)
            or config.get("debug_logging", False)
            or config.get("debug_cache", False)
        )

    def _log_debug(self, msg: str, **fields: Any) -> None:
        if not self._spansh_debug_enabled():
            return
        log_event("SPANSH", msg, **fields)

    def _log_warn(self, key: str, msg: str, **fields: Any) -> None:
        log_event_throttled(key, 3000, "SPANSH", msg, **fields)

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
        use_edsm = is_edsm_enabled()

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
                self._log_warn(
                    "SPANSH:autocomplete_exception",
                    "autocomplete exception",
                    query=q,
                    attempt=attempt + 1,
                    error=f"{type(e).__name__}: {e}",
                )
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
                    self._log_warn(
                        "SPANSH:autocomplete_json_error",
                        "autocomplete json decode error",
                        query=q,
                        error=f"{type(e).__name__}: {e}",
                    )
                    return []

                names = self._extract_name_list(
                    data,
                    container_keys=("systems", "result"),
                    name_keys=("name", "system"),
                )

                self._log_debug("autocomplete response", query=q, results=len(names))
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
            self._log_warn(
                "SPANSH:autocomplete_http",
                "autocomplete http status",
                query=q,
                status_code=res.status_code,
            )
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
        if config.get("features.spansh.debug_payload", False):
            self._log_debug("stations request", url=url, params=params)

        for attempt in range(max(1, self.default_retries)):
            try:
                res = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.default_timeout,
                )
            except Exception as e:  # noqa: BLE001
                self._log_warn(
                    "SPANSH:stations_exception",
                    "stations request exception",
                    system=system,
                    query=q,
                    attempt=attempt + 1,
                    error=f"{type(e).__name__}: {e}",
                )
                return []

            if res.status_code == 200:
                try:
                    data = res.json()
                except Exception as e:  # noqa: BLE001
                    self._log_warn(
                        "SPANSH:stations_json_error",
                        "stations json decode error",
                        system=system,
                        query=q,
                        error=f"{type(e).__name__}: {e}",
                    )
                    return []

                names = self._extract_name_list(
                    data,
                    container_keys=("stations", "result", "bodies"),
                    name_keys=("name", "station", "body", "label"),
                    sort_names=True,
                    limit=200,
                )

                self._log_debug("stations response", system=system, query=q, results=len(names))
                return names

            self._log_warn(
                "SPANSH:stations_http",
                "stations http status",
                system=system,
                query=q,
                status_code=res.status_code,
            )
            if res.status_code in (400, 401, 403, 404):
                break

        return []

    def _extract_name_list(
        self,
        data: Any,
        *,
        container_keys: tuple[str, ...],
        name_keys: tuple[str, ...],
        sort_names: bool = False,
        limit: int | None = None,
    ) -> List[str]:
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = []
            for key in container_keys:
                candidate = data.get(key)
                if isinstance(candidate, list):
                    items = candidate
                    break
        else:
            items = []

        names: List[str] = []
        seen: set[str] = set()
        for item in items:
            name: Optional[str] = None
            if isinstance(item, str):
                name = item
            elif isinstance(item, dict):
                for key in name_keys:
                    value = item.get(key)
                    if value is not None and value != "":
                        name = str(value)
                        break
            else:
                name = str(item)

            if not name:
                continue
            name = str(name).strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)

        if sort_names:
            names = sorted(names, key=lambda item: item.lower())
        if limit is not None and limit > 0:
            names = names[:limit]
        return names

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
        try:
            poll_seconds = float(poll_seconds) if poll_seconds is not None else float(self.default_poll_interval)
        except Exception:
            poll_seconds = float(self.default_poll_interval)
        if poll_seconds <= 0:
            poll_seconds = float(self.default_poll_interval)

        try:
            polls = int(polls) if polls is not None else 60
        except Exception:
            polls = 60
        if polls <= 0:
            polls = 60

        ctx = self._build_route_context(mode, payload, referer, endpoint_path=endpoint_path)
        start_ts = time.monotonic()

        hit, cached = self._route_cache_lookup(ctx)
        if hit:
            self._record_route_telemetry(ctx, status="CACHE_HIT", start_ts=start_ts, response_ms=0)
            return cached

        try:
            result = run_deduped(
                ctx.cache_key,
                lambda: self._run_route_pipeline(
                    ctx,
                    gui_ref=gui_ref,
                    poll_seconds=poll_seconds,
                    polls=polls,
                ),
            )
        except Exception:
            self._record_route_telemetry(ctx, status="ERROR", start_ts=start_ts)
            return None

        if result is None:
            self._record_route_telemetry(ctx, status="ERROR", start_ts=start_ts)
            return None

        status = "SUCCESS"
        if isinstance(result, list) and not result:
            status = "EMPTY"
        self._record_route_telemetry(ctx, status=status, start_ts=start_ts)
        self._route_cache_store(ctx, result)
        return result

    def _build_route_context(
        self,
        mode: str,
        payload: Any,
        referer: str,
        *,
        endpoint_path: str | None,
    ) -> _RouteRequestContext:
        path = self._resolve_route_endpoint_path(mode, payload, endpoint_path=endpoint_path)
        url = f"{self.base_url}{path}"

        headers = self._headers(referer=referer)
        if config.get("features.spansh.form_urlencoded_enabled", True):
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        payload_fields = self._payload_to_fields(payload)
        payload_dict = self._fields_to_dict(payload_fields)
        norm_payload = [(k, self._normalize_payload_value(v)) for k, v in payload_fields]
        cache_key = make_request_key("spansh", path, {"mode": mode, "payload": norm_payload})

        debug_payload = None
        if config.get("debug_cache", False):
            try:
                debug_payload = self._fields_to_dict(norm_payload)
            except Exception:
                debug_payload = None

        ttl_seconds = 6 * 3600 if mode == "trade" else 7 * 24 * 3600
        return _RouteRequestContext(
            mode=mode,
            endpoint_path=path,
            url=url,
            headers=headers,
            payload_fields=payload_fields,
            payload_dict=payload_dict,
            cache_key=cache_key,
            ttl_seconds=ttl_seconds,
            debug_payload=debug_payload,
        )

    def _resolve_route_endpoint_path(
        self,
        mode: str,
        payload: Any,
        *,
        endpoint_path: str | None,
    ) -> str:
        resolved = endpoint_path
        if isinstance(payload, SpanshPayload):
            resolved = payload.endpoint_path
        if resolved:
            if not resolved.startswith("/"):
                resolved = f"/{resolved}"
            return resolved
        if mode in ("neutron", "route"):
            return "/route"
        return f"/{mode}/route"

    def _payload_to_fields(self, data: Any) -> List[Tuple[str, Any]]:
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

    def _fields_to_dict(self, fields: List[Tuple[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in fields:
            if key not in out:
                out[key] = value
                continue
            current = out[key]
            if isinstance(current, list):
                current.append(value)
            else:
                out[key] = [current, value]
        return out

    def _normalize_payload_value(self, value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, dict):
            return {k: self._normalize_payload_value(value[k]) for k in sorted(value.keys())}
        if isinstance(value, list):
            return [self._normalize_payload_value(v) for v in value]
        if isinstance(value, str):
            return value.strip()
        return value

    def _route_cache_lookup(self, ctx: _RouteRequestContext) -> tuple[bool, Any]:
        hit, cached, _meta = self.cache.get(ctx.cache_key)
        if config.get("debug_cache", False):
            self._debug_cache_log(
                ctx.mode,
                ctx.endpoint_path,
                ctx.cache_key,
                ctx.debug_payload,
                hit,
            )
        return bool(hit), cached

    def _run_route_pipeline(
        self,
        ctx: _RouteRequestContext,
        *,
        gui_ref: Any | None,
        poll_seconds: float,
        polls: int,
    ) -> Optional[Any]:
        if not DEBOUNCER.is_allowed("spansh_route", cooldown_sec=1.0, context=ctx.mode):
            spansh_error("Odczekaj chwilę przed kolejnym zapytaniem SPANSH.", gui_ref, context=ctx.mode)
            return None

        job = self._request_route_job(ctx, gui_ref=gui_ref)
        if not job:
            return None

        js = self._poll_results(
            job,
            mode=ctx.mode,
            gui_ref=gui_ref,
            poll_seconds=poll_seconds,
            polls=polls,
        )
        if js is None:
            return None
        return self._extract_route_result(js)

    def _request_route_job(self, ctx: _RouteRequestContext, *, gui_ref: Any | None) -> str | None:
        try:
            if config.get("features.spansh.form_urlencoded_enabled", True):
                response = requests.post(
                    ctx.url,
                    data=ctx.payload_fields,
                    headers=ctx.headers,
                    timeout=self.default_timeout,
                )
            else:
                response = requests.post(
                    ctx.url,
                    json=self._fields_to_dict(ctx.payload_fields),
                    headers=ctx.headers,
                    timeout=self.default_timeout,
                )
        except Exception as e:  # noqa: BLE001
            spansh_error(
                f"{ctx.mode.upper()}: wyjątek HTTP przy wysyłaniu joba ({e})",
                gui_ref,
                context=ctx.mode,
            )
            return None

        if response.status_code not in (200, 202):
            self._log_warn(
                f"SPANSH:route_http:{ctx.mode}",
                "route request http error",
                mode=ctx.mode,
                status_code=response.status_code,
                body=str(getattr(response, "text", ""))[:400],
            )
            spansh_error(
                f"{ctx.mode.upper()}: HTTP {response.status_code} przy wysyłaniu joba.",
                gui_ref,
                context=ctx.mode,
            )
            return None

        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("response is not an object")
            job = body.get("job")
        except Exception as e:  # noqa: BLE001
            spansh_error(
                f"{ctx.mode.upper()}: niepoprawny JSON przy tworzeniu joba ({e}).",
                gui_ref,
                context=ctx.mode,
            )
            return None

        if not job:
            spansh_error(
                f"{ctx.mode.upper()}: brak job ID w odpowiedzi.",
                gui_ref,
                context=ctx.mode,
            )
            return None
        return str(job)

    @staticmethod
    def _extract_route_result(js: Any) -> Any:
        if isinstance(js, dict):
            return js.get("result", [])
        return js

    def _record_route_telemetry(
        self,
        ctx: _RouteRequestContext,
        *,
        status: str,
        start_ts: float,
        response_ms: int | None = None,
    ) -> None:
        if response_ms is None:
            response_ms = int((time.monotonic() - start_ts) * 1000)
        self._set_last_request(
            {
                "timestamp": time.time(),
                "mode": ctx.mode,
                "endpoint": ctx.endpoint_path,
                "url": ctx.url,
                "payload": ctx.payload_dict,
                "status": status,
                "response_ms": response_ms,
            }
        )

    def _route_cache_store(self, ctx: _RouteRequestContext, result: Any) -> None:
        self.cache.set(
            ctx.cache_key,
            result,
            ctx.ttl_seconds,
            meta={"provider": "spansh", "endpoint": ctx.endpoint_path, "mode": ctx.mode},
        )

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
                                "distance_jumped",
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
                        "x": entry.get("x"),
                        "y": entry.get("y"),
                        "z": entry.get("z"),
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

    def _debug_cache_log(
        self,
        mode: str,
        path: str,
        cache_key: str,
        payload: Dict[str, Any] | None,
        hit: bool,
    ) -> None:
        label = "HIT" if hit else "MISS"
        try:
            payload_json = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True)
        except Exception:
            payload_json = "{}"
        self._log_debug(
            "cache lookup",
            mode=mode,
            path=path,
            label=label,
            cache_key=cache_key,
            payload=payload_json,
        )

        if payload is None:
            return
        debug_key = f"{mode}:{path}"
        prev = self._debug_cache_payloads.get(debug_key)
        if prev is not None:
            diff = []
            keys = set(prev.keys()) | set(payload.keys())
            for key in sorted(keys):
                if prev.get(key) != payload.get(key):
                    diff.append(f"{key}: {prev.get(key)!r} -> {payload.get(key)!r}")
            if diff:
                self._log_debug("cache payload diff", mode=mode, path=path, diff="; ".join(diff))
        self._debug_cache_payloads[debug_key] = payload


# Singleton – prosty, ale wystarczający na potrzeby Renaty v90
client = SpanshClient()
