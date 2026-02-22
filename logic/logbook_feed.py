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
    "SupercruiseEntry",
    "SupercruiseExit",
    "ApproachBody",
    "Touchdown",
    "Liftoff",
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
    # Incidents / combat / interdiction
    "Interdicted",
    "EscapeInterdiction",
    "Interdiction",
    "UnderAttack",
    "HullDamage",
    "ShieldState",
    "Died",
}

_TECH_PREFIXES = ("WARN", "OK", "STATE", "CLIPBOARD")


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


def _format_credits(value: Any) -> str | None:
    amount = _as_int(value)
    if amount is None:
        return None
    return f"{amount} cr"


def _format_hull_percent(ev: dict[str, Any]) -> str | None:
    raw = ev.get("Health")
    val = _as_float(raw)
    if val is None:
        return None
    if val <= 1.0:
        percent = int(round(max(0.0, min(1.0, val)) * 100.0))
    else:
        percent = int(round(max(0.0, min(100.0, val))))
    return f"{percent}%"


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


def classify_logbook_event(event_name: Any) -> str:
    name = _as_text(event_name)
    if not name:
        return "TECH"

    if name in {"Location", "FSDJump", "CarrierJump", "SupercruiseEntry", "SupercruiseExit", "ApproachBody", "Touchdown", "Liftoff"}:
        return "Nawigacja"
    if name in {"Docked", "Undocked"}:
        return "Stacja"
    if name in {"Scan", "SAAScanComplete", "SAASignalsFound", "FSSDiscoveryScan", "FSSAllBodiesFound", "CodexEntry", "SellExplorationData"}:
        return "Eksploracja"
    if name in {"ScanOrganic", "SellOrganicData"}:
        return "Exobio"
    if name in {"MarketBuy", "MarketSell"}:
        return "Handel"
    if name in {"ProspectedAsteroid"}:
        return "Eksploracja"
    if name in {"Interdicted", "EscapeInterdiction", "HullDamage"}:
        return "Incydent"
    if name in {"Interdiction", "UnderAttack", "ShieldState", "Died"}:
        return "Combat"
    return "TECH"


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

    if event_name == "SupercruiseEntry":
        return "Wejscie do nadswietlnej"

    if event_name == "SupercruiseExit":
        body = _as_text(ev.get("Body") or ev.get("BodyName"))
        if body:
            return f"Wyjscie z nadswietlnej przy {body}"
        return "Wyjscie z nadswietlnej"

    if event_name == "ApproachBody":
        body = _as_text(ev.get("Body") or ev.get("BodyName")) or "cialo"
        lower = body.lower()
        if " ring" in lower or " piers" in lower:
            return f"Wejscie do pierscienia: {body}"
        return f"Podescie do ciala/orbita: {body}"

    if event_name == "Touchdown":
        body = _as_text(ev.get("Body") or ev.get("BodyName"))
        if body:
            return f"Ladowanie na {body}"
        return "Ladowanie"

    if event_name == "Liftoff":
        body = _as_text(ev.get("Body") or ev.get("BodyName"))
        if body:
            return f"Start z {body}"
        return "Start z powierzchni"

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
        scan_type = _as_text(ev.get("ScanType"))
        prefix = "Exobio"
        if scan_type:
            scan_type_l = scan_type.lower()
            if "sample" in scan_type_l:
                prefix = "Exobio: probka"
            elif "log" in scan_type_l or "analyse" in scan_type_l:
                prefix = "Exobio: analiza"
        if species:
            return f"{prefix}: {species}"
        return f"{prefix.lower()}" if prefix != "Exobio" else "Exobio: scan organic"

    if event_name == "CodexEntry":
        name = _as_text(ev.get("Name_Localised") or ev.get("Name"))
        if name:
            return f"Codex: {name}"
        return "Codex entry"

    if event_name == "SellExplorationData":
        total = _format_credits(
            ev.get("TotalEarnings")
            or ev.get("BaseValue")
            or ev.get("Value")
            or ev.get("Reward")
        )
        if total:
            return f"Sprzedaz danych eksploracji: {total}"
        return "Sprzedaz danych eksploracji"

    if event_name == "SellOrganicData":
        total = _format_credits(
            ev.get("TotalEarnings")
            or ev.get("BioDataValue")
            or ev.get("Value")
            or ev.get("Reward")
        )
        if total:
            return f"Sprzedaz danych exobio: {total}"
        return "Sprzedaz danych exobio"

    if event_name == "Interdicted":
        by = _as_text(ev.get("Interdictor"))
        submitted = ev.get("Submitted")
        parts: list[str] = ["Proba wyciagniecia z nadswietlnej"]
        if by:
            parts.append(f"przez {by}")
        if isinstance(submitted, bool):
            parts.append("poddanie" if submitted else "walka o utrzymanie kursu")
        return " | ".join(parts)

    if event_name == "EscapeInterdiction":
        by = _as_text(ev.get("Interdictor"))
        if by:
            return f"Interdiction: udalo sie uciec ({by})"
        return "Interdiction: udalo sie uciec"

    if event_name == "Interdiction":
        target = _as_text(ev.get("Interdicted"))
        success = ev.get("Success")
        suffix = ""
        if isinstance(success, bool):
            suffix = " (sukces)" if success else " (nieudana)"
        if target:
            return f"Interdiction celu: {target}{suffix}"
        return f"Interdiction celu{suffix}"

    if event_name == "UnderAttack":
        target = _as_text(ev.get("Target") or ev.get("Target_Localised") or ev.get("KillerName"))
        if target:
            return f"Atak: kontakt bojowy ({target})"
        return "Atak: kontakt bojowy"

    if event_name == "HullDamage":
        hull = _format_hull_percent(ev)
        if hull:
            return f"Incydent: uszkodzenie kadluba (hul {hull})"
        return "Incydent: uszkodzenie kadluba"

    if event_name == "ShieldState":
        shields_up = ev.get("ShieldsUp")
        if isinstance(shields_up, bool):
            return "Tarcze: aktywne" if shields_up else "Tarcze: offline"
        return "Zmiana stanu tarcz"

    if event_name == "Died":
        killer = _as_text(ev.get("KillerName") or ev.get("KillerName_Localised"))
        if killer:
            return f"Zgon statku / CMDR (sprawca: {killer})"
        return "Zgon statku / CMDR"

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
    add("INTERDICTOR", ev.get("Interdictor"))
    add("TARGET", ev.get("Interdicted") or ev.get("Target") or ev.get("Target_Localised"))

    amount = _as_int(ev.get("Count") or ev.get("Amount"))
    if amount is not None:
        chips.append({"kind": "AMOUNT", "value": str(amount)})

    price = _as_int(ev.get("BuyPrice") or ev.get("SellPrice") or ev.get("Price"))
    if price is not None:
        chips.append({"kind": "PRICE", "value": str(price)})

    total_credits = _as_int(
        ev.get("TotalEarnings")
        or ev.get("BioDataValue")
        or ev.get("BaseValue")
        or ev.get("Value")
        or ev.get("Reward")
    )
    if total_credits is not None:
        chips.append({"kind": "CR", "value": str(total_credits)})

    hull_percent = _format_hull_percent(ev)
    if hull_percent:
        chips.append({"kind": "HULL", "value": hull_percent})

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
        "event_class": classify_logbook_event(event_name),
        "system_name": system_name,
        "station_name": station_name,
        "body_name": body_name,
        "summary": _format_summary(event_name, event),
        "chips": _build_chips(event_name, event),
        "default_category": default_category_for_event(event_name),
        "raw_event": dict(event),
    }


def _credit_value_from_feed_item(item: dict[str, Any]) -> int:
    raw = item.get("raw_event")
    if not isinstance(raw, dict):
        return 0
    value = _as_int(
        raw.get("TotalEarnings")
        or raw.get("BioDataValue")
        or raw.get("BaseValue")
        or raw.get("Value")
        or raw.get("Reward")
    )
    return int(value or 0)


def build_logbook_info_rows(feed_item: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(feed_item, dict):
        return []

    rows: list[dict[str, str]] = []

    def add(label: str, value: Any) -> None:
        text = _as_text(value)
        if text:
            rows.append({"label": str(label), "value": text})

    add("Klasa", feed_item.get("event_class"))
    add("Event", feed_item.get("event_name"))
    add("Czas", feed_item.get("timestamp"))
    add("System", feed_item.get("system_name"))
    add("Stacja", feed_item.get("station_name"))
    add("Obiekt", feed_item.get("body_name"))
    add("Podsumowanie", feed_item.get("summary"))

    raw = feed_item.get("raw_event")
    if isinstance(raw, dict):
        event_name = _as_text(feed_item.get("event_name"))

        if event_name in {"MarketBuy", "MarketSell"}:
            add("Towar", raw.get("Type") or raw.get("Commodity"))
            amount = _as_int(raw.get("Count") or raw.get("Amount"))
            if amount is not None:
                add("Ilosc", amount)
            price = _as_int(raw.get("BuyPrice") or raw.get("SellPrice") or raw.get("Price"))
            if price is not None:
                add("Cena jedn.", f"{price} cr")
            if amount is not None and price is not None:
                add("Wartosc laczna", f"{amount * price} cr")

        if event_name in {"SellExplorationData", "SellOrganicData"}:
            total = _credit_value_from_feed_item(feed_item)
            if total > 0:
                add("Sprzedaz", f"{total} cr")

        if event_name == "ScanOrganic":
            add("Gatunek", raw.get("Species_Localised") or raw.get("Species") or raw.get("Name"))
            add("Rodzaj skanu", raw.get("ScanType"))

        if event_name in {"Interdicted", "EscapeInterdiction"}:
            add("Interdictor", raw.get("Interdictor"))
            if "Submitted" in raw:
                submitted = raw.get("Submitted")
                if isinstance(submitted, bool):
                    add("Wynik pilota", "Poddanie" if submitted else "Obrona")

        if event_name == "Interdiction":
            add("Cel", raw.get("Interdicted"))
            if "Success" in raw:
                success = raw.get("Success")
                if isinstance(success, bool):
                    add("Wynik", "Sukces" if success else "Nieudana")

        if event_name in {"UnderAttack", "Died"}:
            add(
                "Kontakt",
                raw.get("Target")
                or raw.get("Target_Localised")
                or raw.get("KillerName")
                or raw.get("KillerName_Localised"),
            )

        if event_name == "HullDamage":
            hull = _format_hull_percent(raw)
            if hull:
                add("Kadlub", hull)

        if event_name == "ShieldState":
            if isinstance(raw.get("ShieldsUp"), bool):
                add("Tarcze", "Aktywne" if raw.get("ShieldsUp") else "Offline")

    chips = feed_item.get("chips")
    if isinstance(chips, list):
        for chip in chips[:8]:
            if not isinstance(chip, dict):
                continue
            kind = _as_text(chip.get("kind"))
            value = _as_text(chip.get("value"))
            if not kind or not value:
                continue
            rows.append({"label": f"Chip/{kind}", "value": value})

    return rows


def build_logbook_summary_snapshot(feed_items: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "total_events": 0,
        "class_counts": {},
        "jump_count": 0,
        "landing_count": 0,
        "dock_count": 0,
        "hull_incidents": 0,
        "interdictions": 0,
        "interdiction_escapes": 0,
        "uc_sold_cr": 0,
        "vista_sold_cr": 0,
    }
    class_counts: dict[str, int] = {}

    for item in feed_items:
        if not isinstance(item, dict):
            continue
        summary["total_events"] += 1
        event_name = _as_text(item.get("event_name"))
        event_class = _as_text(item.get("event_class")) or "TECH"
        class_counts[event_class] = int(class_counts.get(event_class, 0)) + 1

        if event_name in {"FSDJump", "CarrierJump"}:
            summary["jump_count"] += 1
        elif event_name == "Touchdown":
            summary["landing_count"] += 1
        elif event_name == "Docked":
            summary["dock_count"] += 1
        elif event_name == "HullDamage":
            summary["hull_incidents"] += 1
        elif event_name == "Interdicted":
            summary["interdictions"] += 1
        elif event_name == "EscapeInterdiction":
            summary["interdiction_escapes"] += 1
        elif event_name == "SellExplorationData":
            summary["uc_sold_cr"] += _credit_value_from_feed_item(item)
        elif event_name == "SellOrganicData":
            summary["vista_sold_cr"] += _credit_value_from_feed_item(item)

    summary["class_counts"] = class_counts
    summary["total_sold_cr"] = int(summary["uc_sold_cr"]) + int(summary["vista_sold_cr"])
    return summary
