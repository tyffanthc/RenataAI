from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any


MVP_EVENT_CATEGORIES = {
    "MarketBuy": "Handel/Transakcje",
    "MarketSell": "Handel/Transakcje",
    "Docked": "Ciekawe miejsca/Stacje",
    "Undocked": "Ciekawe miejsca/Stacje",
    "FSDJump": "Eksploracja/Skoki",
    "Scan": "Eksploracja/Odkrycia",
    "SAAScanComplete": "Eksploracja/Odkrycia",
    "ProspectedAsteroid": "Gornictwo/Hotspoty",
}


def _as_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text else None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_mvp_journal_event(event_name: Any) -> bool:
    name = _as_text(event_name)
    if not name:
        return False
    return name in MVP_EVENT_CATEGORIES


def default_category_for_event(event_name: Any) -> str | None:
    name = _as_text(event_name)
    if not name:
        return None
    return MVP_EVENT_CATEGORIES.get(name)


def _common_location(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "system_name": _as_text(event.get("StarSystem")),
        "station_name": _as_text(event.get("StationName")),
        "body_name": _as_text(event.get("BodyName") or event.get("Body")),
    }


def _trade_payload(event_name: str, event: dict[str, Any]) -> dict[str, Any]:
    commodity = _as_text(event.get("Type") or event.get("Commodity"))
    amount = _as_int(event.get("Count") or event.get("Amount"))
    price_key = "BuyPrice" if event_name == "MarketBuy" else "SellPrice"
    price = _as_int(event.get(price_key) or event.get("Price"))
    total = amount * price if amount is not None and price is not None else None
    return {
        "commodity": commodity,
        "amount": amount,
        "price": price,
        "total": total,
        "station": _as_text(event.get("StationName")),
        "system": _as_text(event.get("StarSystem")),
    }


def _trade_draft(event_name: str, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
    payload = _trade_payload(event_name, event)
    commodity = payload.get("commodity") or "towar"
    place = payload.get("station") or payload.get("system") or "unknown"
    action = "Kupno" if event_name == "MarketBuy" else "Sprzedaz"
    body_lines = [
        f"Event: {event_name}",
        f"Towar: {commodity}",
        f"Ilosc: {payload.get('amount') if payload.get('amount') is not None else '-'} t",
        f"Cena: {payload.get('price') if payload.get('price') is not None else '-'} cr",
        f"Suma: {payload.get('total') if payload.get('total') is not None else '-'} cr",
        f"System: {payload.get('system') or '-'}",
        f"Stacja: {payload.get('station') or '-'}",
    ]
    return {
        "category_path": default_category_for_event(event_name),
        "title": f"{action} - {commodity} @ {place}",
        "body": "\n".join(body_lines),
        "tags": ["trade", "market", event_name.lower()],
        "entry_type": "trade_transaction",
        "location": _common_location(event),
        "source": {
            "kind": "journal_event",
            "event_name": event_name,
            "event_time": timestamp,
        },
        "payload": {
            "trade": payload,
            "journal_event": copy.deepcopy(event),
        },
    }


def _docked_draft(event_name: str, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
    station = _as_text(event.get("StationName")) or "unknown station"
    system = _as_text(event.get("StarSystem")) or "unknown system"
    is_docked = event_name == "Docked"
    verb = "Dokowanie" if is_docked else "Odlot"
    body_lines = [
        f"Event: {event_name}",
        f"System: {system}",
        f"Stacja: {station}",
    ]
    return {
        "category_path": default_category_for_event(event_name),
        "title": f"{verb} - {station}",
        "body": "\n".join(body_lines),
        "tags": ["navigation", "station", "docked" if is_docked else "undocked"],
        "entry_type": "station_visit",
        "location": _common_location(event),
        "source": {
            "kind": "journal_event",
            "event_name": event_name,
            "event_time": timestamp,
        },
        "payload": {
            "navigation": {
                "state": "docked" if is_docked else "undocked",
                "system": system,
                "station": station,
            },
            "journal_event": copy.deepcopy(event),
        },
    }


def _jump_draft(event: dict[str, Any], timestamp: str) -> dict[str, Any]:
    system = _as_text(event.get("StarSystem")) or "unknown system"
    jump_dist = _as_float(event.get("JumpDist"))
    fuel_used = _as_float(event.get("FuelUsed"))
    body_lines = [
        "Event: FSDJump",
        f"System docelowy: {system}",
        f"Dystans: {f'{jump_dist:.2f} ly' if jump_dist is not None else '-'}",
        f"Zuzyte paliwo: {f'{fuel_used:.2f} t' if fuel_used is not None else '-'}",
    ]
    return {
        "category_path": default_category_for_event("FSDJump"),
        "title": f"Skok FSD - {system}",
        "body": "\n".join(body_lines),
        "tags": ["exploration", "navigation", "jump"],
        "entry_type": "jump_log",
        "location": _common_location(event),
        "source": {
            "kind": "journal_event",
            "event_name": "FSDJump",
            "event_time": timestamp,
        },
        "payload": {
            "jump": {
                "target_system": system,
                "jump_dist_ly": jump_dist,
                "fuel_used_t": fuel_used,
            },
            "journal_event": copy.deepcopy(event),
        },
    }


def _scan_draft(event_name: str, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
    body_name = _as_text(event.get("BodyName") or event.get("Body")) or "unknown body"
    system = _as_text(event.get("StarSystem")) or "unknown system"
    body_type = _as_text(event.get("PlanetClass") or event.get("StarType") or event.get("BodyType"))
    signals = _as_int(event.get("SignalsFound") or event.get("BioSignals"))
    body_lines = [
        f"Event: {event_name}",
        f"System: {system}",
        f"Body: {body_name}",
        f"Typ ciala: {body_type or '-'}",
        f"Sygnały: {signals if signals is not None else '-'}",
    ]
    tags = ["exploration", "scan"]
    if event_name == "SAAScanComplete":
        tags.append("dss")
    return {
        "category_path": default_category_for_event(event_name),
        "title": f"{event_name} - {body_name}",
        "body": "\n".join(body_lines),
        "tags": tags,
        "entry_type": "exploration_scan",
        "location": _common_location(event),
        "source": {
            "kind": "journal_event",
            "event_name": event_name,
            "event_time": timestamp,
        },
        "payload": {
            "exploration": {
                "system": system,
                "body": body_name,
                "body_type": body_type,
                "signals": signals,
            },
            "journal_event": copy.deepcopy(event),
        },
    }


def _prospected_asteroid_draft(event: dict[str, Any], timestamp: str) -> dict[str, Any]:
    commodity = _as_text(event.get("Content") or event.get("Material")) or "unknown"
    percent = _as_float(event.get("ContentPercent") or event.get("Percent"))
    body_name = _as_text(event.get("BodyName") or event.get("Body"))
    system = _as_text(event.get("StarSystem"))
    body_lines = [
        "Event: ProspectedAsteroid",
        f"Commodity: {commodity}",
        f"Concentration: {f'{percent:.1f}%' if percent is not None else '-'}",
        f"System: {system or '-'}",
        f"Body/Ring: {body_name or '-'}",
    ]
    return {
        "category_path": default_category_for_event("ProspectedAsteroid"),
        "title": f"ProspectedAsteroid - {commodity}",
        "body": "\n".join(body_lines),
        "tags": ["mining", "prospecting", "asteroid"],
        "entry_type": "mining_hotspot",
        "location": _common_location(event),
        "source": {
            "kind": "journal_event",
            "event_name": "ProspectedAsteroid",
            "event_time": timestamp,
        },
        "payload": {
            "mining": {
                "commodity": commodity,
                "concentration_percent": percent,
                "system": system,
                "body_or_ring": body_name,
            },
            "journal_event": copy.deepcopy(event),
        },
    }


def build_mvp_entry_draft(event: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    event_name = _as_text(event.get("event"))
    if not is_mvp_journal_event(event_name):
        return None

    timestamp = _as_text(event.get("timestamp")) or _now_iso()

    if event_name in {"MarketBuy", "MarketSell"}:
        return _trade_draft(event_name, event, timestamp)
    if event_name in {"Docked", "Undocked"}:
        return _docked_draft(event_name, event, timestamp)
    if event_name == "FSDJump":
        return _jump_draft(event, timestamp)
    if event_name in {"Scan", "SAAScanComplete"}:
        return _scan_draft(event_name, event, timestamp)
    if event_name == "ProspectedAsteroid":
        return _prospected_asteroid_draft(event, timestamp)
    return None

