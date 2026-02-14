from __future__ import annotations

import math
import re
from typing import Any, Dict

import config
from logic.utils import powiedz, MSG_QUEUE
from logic.spansh_client import client, spansh_error
from logic import spansh_payloads
from logic.rows_normalizer import normalize_trade_rows


_AGE_RE = re.compile(
    r"(?P<num>\d+)\s*(?P<unit>"
    r"second|seconds|sec|secs|s|"
    r"minute|minutes|min|mins|m|"
    r"hour|hours|hr|hrs|h|"
    r"day|days|d|"
    r"week|weeks|w|"
    r"month|months|"
    r"year|years|y|"
    r"sekunda|sekundy|sekund|sek|"
    r"minuta|minuty|minut|"
    r"godzina|godziny|godzin|godz|"
    r"dzien|dni|"
    r"tydzien|tygodnie|tygodni|"
    r"miesiac|miesiace|miesiecy|"
    r"rok|lata|lat"
    r")\b",
    flags=re.IGNORECASE,
)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\xa0", "").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except Exception:
        return None


def _clamp_0_100(value: float) -> int:
    return int(max(0.0, min(100.0, round(value))))


def _normalize_scores(values: list[float], *, inverse: bool = False) -> list[int]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [70 for _ in values]
    out: list[int] = []
    span = hi - lo
    for val in values:
        norm = (val - lo) / span
        if inverse:
            norm = 1.0 - norm
        out.append(_clamp_0_100(norm * 100.0))
    return out


def _parse_age_seconds(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"now", "just now", "teraz"}:
        return 0.0
    match = _AGE_RE.search(text)
    if not match:
        return None
    try:
        num = float(match.group("num"))
    except Exception:
        return None
    unit = (match.group("unit") or "").casefold()
    if unit in {"s", "sec", "secs", "second", "seconds", "sek", "sekunda", "sekundy", "sekund"}:
        return num
    if unit in {"m", "min", "mins", "minute", "minutes", "minuta", "minuty", "minut"}:
        return num * 60.0
    if unit in {"h", "hr", "hrs", "hour", "hours", "godz", "godzina", "godziny", "godzin"}:
        return num * 3600.0
    if unit in {"d", "day", "days", "dzien", "dni"}:
        return num * 86400.0
    if unit in {"w", "week", "weeks", "tydzien", "tygodnie", "tygodni"}:
        return num * 7.0 * 86400.0
    if unit in {"month", "months", "miesiac", "miesiace", "miesiecy"}:
        return num * 30.0 * 86400.0
    if unit in {"y", "year", "years", "rok", "lata", "lat"}:
        return num * 365.0 * 86400.0
    return None


def _trust_status_from_score(score: int) -> str:
    if score >= 75:
        return "Wysoka"
    if score >= 50:
        return "Srednia"
    return "Niska"


def _risk_status_from_score(score: int) -> str:
    if score >= 75:
        return "Niskie"
    if score >= 50:
        return "Srednie"
    return "Wysokie"


def _source_status_penalty(source_status: str) -> tuple[float, int]:
    key = (source_status or "").strip().upper()
    if key == "ONLINE_LIVE":
        return 0.0, +12
    if key == "CACHE_TTL_HIT":
        return 0.08, +3
    if key == "OFFLINE_CACHE_FALLBACK":
        return 0.35, -18
    if key == "ERROR_NO_DATA":
        return 0.5, -30
    return 0.15, -4


def _confidence_base(confidence: str) -> int:
    key = (confidence or "").strip().lower()
    if key == "high":
        return 84
    if key == "medium":
        return 64
    if key == "low":
        return 42
    return 55


def build_sell_assist_decision_space(
    rows: list[dict],
    *,
    jump_range: float | None = None,
) -> dict[str, Any]:
    """
    Build FREE Sell Assist decision space (2-3 options + Pomijam) using:
    - price_score
    - time_score
    - risk_score
    - trust_score
    """
    if not rows:
        return {
            "mode": "empty",
            "advisory_only": True,
            "options": [],
            "skip_action": {"id": "skip", "label": "Pomijam"},
            "note": "Brak danych do oceny opcji.",
        }

    jr = _to_float(jump_range)
    if jr is None or jr <= 0:
        jr = 30.0

    candidates: list[dict[str, Any]] = []
    eta_values: list[float] = []
    profit_values: list[float] = []
    distance_values: list[float] = []
    jumps_values: list[float] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        total_profit = _to_float(row.get("total_profit"))
        profit_per_ton = _to_float(row.get("profit"))
        amount = _to_float(row.get("amount"))
        if total_profit is None and profit_per_ton is not None and amount is not None:
            total_profit = profit_per_ton * amount
        if total_profit is None:
            total_profit = 0.0

        distance_ly = _to_float(row.get("distance_ly"))
        if distance_ly is None or distance_ly < 0:
            distance_ly = 0.0

        jumps = _to_float(row.get("jumps"))
        if jumps is None or jumps <= 0:
            jumps = float(max(1, int(math.ceil(distance_ly / max(jr, 1.0)))))

        eta_minutes = max(1.0, (jumps * 1.8) + (distance_ly / 55.0) * 1.2)

        source_status = str(row.get("source_status") or "UNKNOWN")
        confidence = str(row.get("confidence") or "low")
        data_age_seconds = _to_float(row.get("data_age_seconds"))
        if data_age_seconds is None:
            ages = [
                _parse_age_seconds(row.get("updated_buy_ago")),
                _parse_age_seconds(row.get("updated_sell_ago")),
                _parse_age_seconds(row.get("updated_ago")),
            ]
            parsed = [age for age in ages if age is not None]
            data_age_seconds = max(parsed) if parsed else None

        source_risk_penalty, source_trust_adjust = _source_status_penalty(source_status)
        confidence_base = _confidence_base(confidence)
        freshness_penalty = 0.0
        freshness_trust_adjust = 0
        if data_age_seconds is not None:
            if data_age_seconds > 72 * 3600:
                freshness_penalty = 0.40
                freshness_trust_adjust = -28
            elif data_age_seconds > 24 * 3600:
                freshness_penalty = 0.25
                freshness_trust_adjust = -18
            elif data_age_seconds > 6 * 3600:
                freshness_penalty = 0.12
                freshness_trust_adjust = -8

        trust_score = _clamp_0_100(confidence_base + source_trust_adjust + freshness_trust_adjust)

        candidate = {
            "row_index": idx,
            "row": row,
            "total_profit": float(total_profit),
            "distance_ly": float(distance_ly),
            "jumps": float(jumps),
            "eta_minutes": float(eta_minutes),
            "_source_risk_penalty": float(source_risk_penalty),
            "_freshness_risk_penalty": float(freshness_penalty),
            "trust_score": int(trust_score),
        }
        candidates.append(candidate)
        profit_values.append(candidate["total_profit"])
        eta_values.append(candidate["eta_minutes"])
        distance_values.append(candidate["distance_ly"])
        jumps_values.append(candidate["jumps"])

    if not candidates:
        return {
            "mode": "empty",
            "advisory_only": True,
            "options": [],
            "skip_action": {"id": "skip", "label": "Pomijam"},
            "note": "Brak poprawnych danych po normalizacji.",
        }

    price_scores = _normalize_scores(profit_values, inverse=False)
    time_scores = _normalize_scores(eta_values, inverse=True)
    distance_norm = _normalize_scores(distance_values, inverse=False)
    jumps_norm = _normalize_scores(jumps_values, inverse=False)

    for i, candidate in enumerate(candidates):
        raw_risk = (
            0.42 * (distance_norm[i] / 100.0)
            + 0.33 * (jumps_norm[i] / 100.0)
            + 0.15 * candidate["_source_risk_penalty"]
            + 0.10 * candidate["_freshness_risk_penalty"]
        )
        raw_risk = max(0.0, min(1.0, raw_risk))
        risk_score = _clamp_0_100((1.0 - raw_risk) * 100.0)

        candidate["price_score"] = int(price_scores[i])
        candidate["time_score"] = int(time_scores[i])
        candidate["risk_score"] = int(risk_score)
        candidate["overall_score"] = int(
            round(
                (candidate["price_score"] * 0.35)
                + (candidate["time_score"] * 0.25)
                + (candidate["risk_score"] * 0.20)
                + (candidate["trust_score"] * 0.20)
            )
        )
        candidate.pop("_source_risk_penalty", None)
        candidate.pop("_freshness_risk_penalty", None)

    source_values = {str(c["row"].get("source_status") or "").strip().upper() for c in candidates}
    max_age_seconds = max(
        [
            _to_float(c["row"].get("data_age_seconds")) or 0.0
            for c in candidates
        ]
        or [0.0]
    )
    advisory_only = bool(
        "OFFLINE_CACHE_FALLBACK" in source_values
        or "ERROR_NO_DATA" in source_values
        or max_age_seconds >= 24 * 3600
    )

    target_options = 3 if len(candidates) >= 3 else 2
    strategy_defs = [
        ("Najszybciej", "fastest", lambda c: c["time_score"]),
        ("Najwyzszy zysk", "highest_price", lambda c: c["price_score"]),
        ("Najbezpieczniej", "safest", lambda c: c["risk_score"]),
        ("Kompromis", "balanced", lambda c: c["overall_score"]),
    ]

    options: list[dict[str, Any]] = []
    used_rows: set[int] = set()

    for title, strategy, key_fn in strategy_defs:
        if len(options) >= target_options:
            break
        pool = [cand for cand in candidates if cand["row_index"] not in used_rows]
        if not pool:
            pool = list(candidates)
        selected = max(pool, key=key_fn)
        used_rows.add(int(selected["row_index"]))
        row = selected["row"]
        option = {
            "option_id": f"sell_assist_{strategy}_{len(options) + 1}",
            "label": title,
            "strategy": strategy,
            "row_index": int(selected["row_index"]),
            "from_system": str(row.get("from_system") or "-"),
            "from_station": str(row.get("from_station") or "-"),
            "to_system": str(row.get("to_system") or "-"),
            "to_station": str(row.get("to_station") or "-"),
            "estimated_profit": int(round(selected["total_profit"])),
            "distance_ly": round(float(selected["distance_ly"]), 2),
            "eta_minutes": int(round(selected["eta_minutes"])),
            "risk_label": _risk_status_from_score(int(selected["risk_score"])),
            "trust_label": _trust_status_from_score(int(selected["trust_score"])),
            "source_status": str(row.get("source_status") or "UNKNOWN"),
            "confidence": str(row.get("confidence") or "low"),
            "scores": {
                "price_score": int(selected["price_score"]),
                "time_score": int(selected["time_score"]),
                "risk_score": int(selected["risk_score"]),
                "trust_score": int(selected["trust_score"]),
            },
            "reasoning": {
                "profit_text": f"{int(round(selected['total_profit']))} cr",
                "eta_text": f"{int(round(selected['eta_minutes']))} min",
                "distance_text": f"{round(float(selected['distance_ly']), 2)} ly",
                "risk_text": _risk_status_from_score(int(selected["risk_score"])),
                "trust_text": _trust_status_from_score(int(selected["trust_score"])),
            },
            "advisory_only": advisory_only,
        }
        options.append(option)

    if len(options) < 2 and candidates:
        base = options[0] if options else None
        if base is None:
            selected = max(candidates, key=lambda c: c["overall_score"])
            row = selected["row"]
            base = {
                "option_id": "sell_assist_balanced_1",
                "label": "Kompromis",
                "strategy": "balanced",
                "row_index": int(selected["row_index"]),
                "from_system": str(row.get("from_system") or "-"),
                "from_station": str(row.get("from_station") or "-"),
                "to_system": str(row.get("to_system") or "-"),
                "to_station": str(row.get("to_station") or "-"),
                "estimated_profit": int(round(selected["total_profit"])),
                "distance_ly": round(float(selected["distance_ly"]), 2),
                "eta_minutes": int(round(selected["eta_minutes"])),
                "risk_label": _risk_status_from_score(int(selected["risk_score"])),
                "trust_label": _trust_status_from_score(int(selected["trust_score"])),
                "source_status": str(row.get("source_status") or "UNKNOWN"),
                "confidence": str(row.get("confidence") or "low"),
                "scores": {
                    "price_score": int(selected["price_score"]),
                    "time_score": int(selected["time_score"]),
                    "risk_score": int(selected["risk_score"]),
                    "trust_score": int(selected["trust_score"]),
                },
                "reasoning": {
                    "profit_text": f"{int(round(selected['total_profit']))} cr",
                    "eta_text": f"{int(round(selected['eta_minutes']))} min",
                    "distance_text": f"{round(float(selected['distance_ly']), 2)} ly",
                    "risk_text": _risk_status_from_score(int(selected["risk_score"])),
                    "trust_text": _trust_status_from_score(int(selected["trust_score"])),
                },
                "advisory_only": advisory_only,
            }
            options.append(base)

        clone = dict(base)
        clone["option_id"] = f"{clone.get('option_id', 'sell_assist')}_alt"
        clone["label"] = "Alternatywa (te same dane)"
        clone["strategy"] = "fallback_alt"
        options.append(clone)

    if len(options) > 3:
        options = options[:3]

    mode = "fallback" if advisory_only else "standard"
    note = (
        "Dane sa stale/offline - traktuj ranking orientacyjnie."
        if advisory_only
        else "Ranking pokazuje trade-offy: czas, zysk, ryzyko i jakosc danych."
    )

    return {
        "mode": mode,
        "advisory_only": advisory_only,
        "options": options,
        "skip_action": {"id": "skip", "label": "Pomijam"},
        "note": note,
    }


def oblicz_trade(
    start_system: str,
    start_station: str,
    capital: int,
    max_hop: float,
    cargo: int,
    max_hops: int,
    max_dta: int,
    max_age: float | None,
    flags: Dict[str, Any],
    gui_ref: Any | None = None,
) -> tuple[list[str], list[dict]]:
    """
    Logika Trade Plannera oparta o SPANSH /api/trade/route.

    Parametry (z GUI):
        start_system - system startowy
        start_station - stacja startowa
        capital      - kapital [Cr]
        max_hop      - max hop distance [LY]
        cargo        - ladownosc [t]
        max_hops     - max liczba skokow
        max_dta      - max distance to arrival [ls]
        max_age      - max wiek danych [dni], None = brak limitu (forever)
        flags        - slownik z checkboxow

    Zwraca:
        (route, rows) - trasa + wiersze tabeli.
    """
    try:
        system = (start_system or "").strip()
        station = (start_station or "").strip()

        if system and not station:
            raw = system
            parts: list[str] = []

            if "/" in raw:
                parts = [p.strip() for p in raw.split("/", 1)]
            elif "," in raw:
                parts = [p.strip() for p in raw.split(",", 1)]

            if parts:
                if parts[0]:
                    system = parts[0]
                if len(parts) > 1 and parts[1]:
                    station = parts[1]

        if not system:
            spansh_error(
                "TRADE: brak systemu startowego.",
                gui_ref,
                context="trade",
            )
            return [], []

        if not station:
            spansh_error(
                "TRADE: wybierz stacje startowa - SPANSH Trade wymaga system+station.",
                gui_ref,
                context="trade",
            )
            return [], []

        powiedz(
            (
                f"API TRADE: {system} / {station}, kapital={capital} Cr, "
                f"hop={max_hop} LY, ladownosc={cargo} t, max hops={max_hops}"
            ),
            gui_ref,
        )

        payload = spansh_payloads.build_trade_payload(
            start_system=system,
            start_station=station,
            capital=capital,
            max_hop=max_hop,
            cargo=cargo,
            max_hops=max_hops,
            max_dta=max_dta,
            max_age=max_age,
            flags=flags,
        )
        if config.get("features.spansh.debug_payload", False):
            MSG_QUEUE.put(("log", f"[SPANSH TRADE PAYLOAD] {payload.form_fields}"))

        result = client.route(
            mode="trade",
            payload=payload,
            referer="https://spansh.co.uk/trade",
            gui_ref=gui_ref,
        )

        if not result:
            return [], []

        getter = getattr(client, "get_last_request", None)
        if callable(getter):
            last_request = getter() or {}
        else:
            last_request = {}
        external_meta = {
            "source_status": last_request.get("source_status"),
            "confidence": last_request.get("confidence"),
            "confidence_score": last_request.get("confidence_score"),
            "data_age": last_request.get("data_age"),
            "data_age_seconds": last_request.get("data_age_seconds"),
            "is_offline_fallback": bool(last_request.get("is_offline_fallback", False)),
        }
        route, rows = normalize_trade_rows(result, external_meta=external_meta)

        if not rows:
            spansh_error(
                "TRADE: SPANSH nie zwrocil zadnych propozycji.",
                gui_ref,
                context="trade",
            )
            return [], []

        return route, rows

    except Exception as e:  # noqa: BLE001
        powiedz(f"TRADE error: {e}", gui_ref)
        return [], []
