from __future__ import annotations

from typing import Any


def _as_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text else None


def _resolve_target_and_kind(
    *,
    station_name: Any,
    body_name: Any,
    system_name: Any,
) -> tuple[str, str] | None:
    station = _as_text(station_name)
    if station:
        return "STATION", station
    body = _as_text(body_name)
    if body:
        return "BODY", body
    system = _as_text(system_name)
    if system:
        return "SYSTEM", system
    return None


def resolve_entry_nav_target_typed(entry: dict[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(entry, dict):
        return None
    location = entry.get("location") or {}
    if not isinstance(location, dict):
        location = {}
    return _resolve_target_and_kind(
        station_name=location.get("station_name"),
        body_name=location.get("body_name"),
        system_name=location.get("system_name"),
    )


def resolve_entry_nav_target(entry: dict[str, Any] | None) -> str | None:
    resolved = resolve_entry_nav_target_typed(entry)
    return resolved[1] if resolved else None


def resolve_logbook_nav_target_typed(feed_item: dict[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(feed_item, dict):
        return None
    return _resolve_target_and_kind(
        station_name=feed_item.get("station_name"),
        body_name=feed_item.get("body_name"),
        system_name=feed_item.get("system_name"),
    )


def resolve_logbook_nav_target(feed_item: dict[str, Any] | None) -> str | None:
    resolved = resolve_logbook_nav_target_typed(feed_item)
    return resolved[1] if resolved else None


def extract_navigation_chips(feed_item: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(feed_item, dict):
        return []
    raw_chips = feed_item.get("chips") or []
    if not isinstance(raw_chips, list):
        return []

    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for chip in raw_chips:
        if not isinstance(chip, dict):
            continue
        kind = str(chip.get("kind") or "").strip().upper()
        value = _as_text(chip.get("value"))
        if kind not in {"SYSTEM", "STATION"} or not value:
            continue
        key = (kind, value)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "value": value})
    return out


def resolve_chip_nav_target(chip: dict[str, Any] | None) -> str | None:
    if not isinstance(chip, dict):
        return None
    kind = str(chip.get("kind") or "").strip().upper()
    if kind not in {"SYSTEM", "STATION"}:
        return None
    return _as_text(chip.get("value"))
