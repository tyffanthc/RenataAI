from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from logic.journal_entry_mapping import default_category_for_event

_CAPTAIN_EVENT_WHITELIST = {
    # Trade / market
    "MarketBuy",
    "MarketSell",
    # Navigation
    "Location",
    "FSDJump",
    "CarrierJump",
    "Docked",
    "Undocked",
    # Exploration
    "Scan",
    "SAAScanComplete",
    "SAASignalsFound",
    "FSSDiscoveryScan",
    "FSSAllBodiesFound",
    "ScanOrganic",
    "CodexEntry",
    "SellExplorationData",
    "SellOrganicData",
    # Mining
    "ProspectedAsteroid",
}

_TECH_PREFIXES = ("APP", "WARN", "OK", "STATE", "CLIPBOARD")


def _as_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


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


def is_captain_journal_event(event_name: Any) -> bool:
    name = _as_text(event_name)
    if not name:
        return False
    if name.startswith("["):
        return False
    upper = name.upper()
    if any(upper.startswith(prefix) for prefix in _TECH_PREFIXES):
        return False
    return name in _CAPTAIN_EVENT_WHITELIST


def _format_summary(event_name: str, ev: dict[str, Any]) -> str:
    if event_name in {"MarketBuy", "MarketSell"}:
        verb = "Kupno" if event_name == "MarketBuy" else "Sprzedaz"
        commodity = _as_text(ev.get("Type") or ev.get("Commodity"))
        amount = _as_int(ev.get("Count") or ev.get("Amount"))
        price_key = "BuyPrice" if event_name == "MarketBuy" else "SellPrice"
        price = _as_int(ev.get(price_key) or ev.get("Price"))
        parts: list[str] = []
        if commodity:
            parts.append(commodity)
        if amount is not None:
            parts.append(f"{amount} t")
        if price is not None:
            parts.append(f"po {price} cr")
        if parts:
            return f"{verb}: {' | '.join(parts)}"
        return verb

    if event_name in {"FSDJump", "CarrierJump"}:
        target = _as_text(ev.get("StarSystem")) or "?"
        jump_dist = _as_float(ev.get("JumpDist"))
        if jump_dist is not None:
            return f"Skok do {target} ({jump_dist:.1f} ly)"
        return f"Skok do {target}"

    if event_name == "Location":
        system = _as_text(ev.get("StarSystem")) or "?"
        station = _as_text(ev.get("StationName"))
        if station:
            return f"Pozycja: {system} / {station}"
        return f"Pozycja: {system}"

    if event_name == "Docked":
        station = _as_text(ev.get("StationName")) or "?"
        return f"Zadokowano: {station}"

    if event_name == "Undocked":
        return "Odlot ze stacji"

    if event_name in {"Scan", "SAAScanComplete"}:
        body = _as_text(ev.get("BodyName") or ev.get("Body")) or "cialo"
        return f"Skan: {body}"

    if event_name == "SAASignalsFound":
        body = _as_text(ev.get("BodyName") or ev.get("Body")) or "cialo"
        bio = _as_int(ev.get("BioSignals") or ev.get("SignalsFound"))
        if bio is not None:
            return f"Sygnaly na {body}: {bio}"
        return f"Sygnaly na {body}"

    if event_name == "FSSDiscoveryScan":
        count = _as_int(ev.get("BodyCount"))
        if count is not None:
            return f"FSS: wykryto {count} cial"
        return "FSS: discovery scan"

    if event_name == "FSSAllBodiesFound":
        return "FSS: wszystkie ciala znalezione"

    if event_name == "ProspectedAsteroid":
        commodity = _as_text(ev.get("Content") or ev.get("Material"))
        percentage = _as_float(ev.get("ContentPercent") or ev.get("Percent"))
        if commodity and percentage is not None:
            return f"Prospekt: {commodity} {percentage:.1f}%"
        if commodity:
            return f"Prospekt: {commodity}"
        return "Prospekt asteroidy"

    if event_name == "ScanOrganic":
        species = _as_text(ev.get("Species_Localised") or ev.get("Species") or ev.get("Name"))
        if species:
            return f"Exobio: {species}"
        return "Exobio: scan organic"

    if event_name == "CodexEntry":
        name = _as_text(ev.get("Name_Localised") or ev.get("Name"))
        if name:
            return f"Codex: {name}"
        return "Codex entry"

    if event_name == "SellExplorationData":
        return "Sprzedaz danych eksploracji"

    if event_name == "SellOrganicData":
        return "Sprzedaz danych exobio"

    return event_name


def _build_chips(event_name: str, ev: dict[str, Any]) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []

    def add(kind: str, value: Any) -> None:
        text = _as_text(value)
        if text:
            chips.append({"kind": kind, "value": text})

    add("EVENT", event_name)
    add("SYSTEM", ev.get("StarSystem"))
    add("STATION", ev.get("StationName"))
    add("BODY", ev.get("BodyName") or ev.get("Body"))
    add("COMMODITY", ev.get("Type") or ev.get("Commodity"))

    amount = _as_int(ev.get("Count") or ev.get("Amount"))
    if amount is not None:
        chips.append({"kind": "AMOUNT", "value": str(amount)})

    price = _as_int(ev.get("BuyPrice") or ev.get("SellPrice") or ev.get("Price"))
    if price is not None:
        chips.append({"kind": "PRICE", "value": str(price)})

    return chips


def build_logbook_feed_item(event: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    event_name = _as_text(event.get("event"))
    if not is_captain_journal_event(event_name):
        return None

    timestamp = _as_text(event.get("timestamp")) or _now_iso()
    system_name = _as_text(event.get("StarSystem")) or None
    station_name = _as_text(event.get("StationName")) or None
    body_name = _as_text(event.get("BodyName") or event.get("Body")) or None

    return {
        "timestamp": timestamp,
        "event_name": event_name,
        "system_name": system_name,
        "station_name": station_name,
        "body_name": body_name,
        "summary": _format_summary(event_name, event),
        "chips": _build_chips(event_name, event),
        "default_category": default_category_for_event(event_name),
        "raw_event": dict(event),
    }
