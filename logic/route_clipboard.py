from __future__ import annotations

from typing import Any, Iterable
import hashlib
import json

try:
    import pyperclip
except Exception:
    pyperclip = None


def _coerce_system_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        name = value.strip()
    else:
        name = str(value).strip()
    return name or None


def _coerce_system_list(items: Iterable[Any]) -> list[str]:
    systems: list[str] = []
    for item in items:
        name = None
        if isinstance(item, dict):
            name = (
                item.get("system")
                or item.get("name")
                or item.get("star_system")
                or item.get("system_name")
            )
            if not name:
                name = item.get("from_system") or item.get("to_system")
        if name is None:
            name = item
        name = _coerce_system_name(name)
        if name:
            systems.append(name)
    return systems


def _extract_systems(route: Any) -> list[str]:
    if not route:
        return []
    if isinstance(route, (list, tuple)):
        return _coerce_system_list(route)
    if isinstance(route, dict):
        for key in ("systems", "route", "path", "system_list", "points"):
            value = route.get(key)
            if isinstance(value, (list, tuple)):
                systems = _coerce_system_list(value)
                if systems:
                    return systems
        name = _coerce_system_name(route.get("system") or route.get("name"))
        return [name] if name else []
    if isinstance(route, str):
        name = route.strip()
        return [name] if name else []
    return []


def _first_present(route: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = route.get(key)
        if value is not None and value != "":
            return value
    return None


def _extract_meta(route: Any) -> dict[str, Any]:
    if not isinstance(route, dict):
        return {}

    meta: dict[str, Any] = {}

    start = _first_present(route, ("start", "from", "origin", "system_from"))
    end = _first_present(route, ("end", "to", "destination", "system_to"))
    jumps = _first_present(route, ("jumps", "jump_count", "jumps_count", "hops"))
    distance = _first_present(
        route,
        ("distance_ly", "distance", "total_distance", "distanceLy", "distance_lys"),
    )
    route_type = _first_present(route, ("route_type", "mode", "type"))

    if start is not None:
        meta["start"] = str(start).strip()
    if end is not None:
        meta["end"] = str(end).strip()
    if jumps is not None:
        try:
            meta["jumps"] = int(jumps)
        except Exception:
            meta["jumps"] = jumps
    if distance is not None:
        meta["distance_ly"] = distance
    if route_type is not None:
        meta["route_type"] = str(route_type).strip()

    return meta


def _extract_link(route: Any) -> str | None:
    if not isinstance(route, dict):
        return None
    for key in ("link", "url", "spansh_url", "spansh_link"):
        value = route.get(key)
        if value:
            return str(value).strip()
    return None


def _format_distance(value: Any) -> str | None:
    if value is None:
        return None
    try:
        num = float(value)
    except Exception:
        text = str(value).strip()
        return text or None
    if num.is_integer():
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def format_route_for_clipboard(route: Any) -> str:
    systems = _extract_systems(route)
    if not systems:
        return ""

    meta = _extract_meta(route)
    start = meta.get("start") or systems[0]
    end = meta.get("end") or systems[-1]

    jumps = meta.get("jumps")
    if jumps is None and len(systems) >= 2:
        jumps = len(systems) - 1

    distance = _format_distance(meta.get("distance_ly"))

    lines: list[str] = []
    if start and end:
        header = f"Route: {start} -> {end}"
        if jumps is not None:
            if distance is not None:
                header += f" ({jumps} jumps, {distance} ly)"
            else:
                header += f" ({jumps} jumps)"
        lines.append(header)

    lines.extend(systems)

    link = _extract_link(route)
    if link:
        lines.append(f"Link: {link}")

    return "\n".join(lines)


def try_copy_to_clipboard(text: str) -> dict[str, Any]:
    if text is None or str(text) == "":
        return {"ok": False, "error": "empty text"}

    data = str(text)

    errors: list[str] = []

    if pyperclip is not None:
        try:
            pyperclip.copy(data)
            return {"ok": True}
        except Exception as exc:
            errors.append(f"pyperclip: {exc}")

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(data)
        root.update_idletasks()
        root.update()
        root.destroy()
        return {"ok": True}
    except Exception as exc:
        errors.append(f"tkinter: {exc}")

    if errors:
        return {"ok": False, "error": "; ".join(errors)}
    return {"ok": False, "error": "clipboard unavailable"}


def compute_route_signature(route: Any) -> str:
    systems = _extract_systems(route)
    meta = _extract_meta(route)

    if not systems and not meta:
        return ""

    payload: dict[str, Any] = {
        "systems": [name.casefold() for name in systems],
    }

    cleaned_meta = {k: v for k, v in meta.items() if v is not None and v != ""}
    if cleaned_meta:
        payload["meta"] = cleaned_meta

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
