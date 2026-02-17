from __future__ import annotations

from typing import Any


class EntryTemplateError(ValueError):
    """Raised when template input is invalid."""


_TEMPLATE_DEFAULT_CATEGORIES = {
    "mining_hotspot": "Gornictwo/Hotspoty",
    "trade_route": "Handel/Trasy",
}


def _as_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text else None


def _require_text(value: Any, field_name: str) -> str:
    text = _as_text(value)
    if not text:
        raise EntryTemplateError(f"{field_name} is required")
    return text


def _as_float(value: Any) -> float | None:
    text = _as_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise EntryTemplateError(f"{value!r} is not a valid number") from exc


def _normalize_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "tak"}:
        return True
    if text in {"0", "false", "no", "n", "nie"}:
        return False
    raise EntryTemplateError(f"{value!r} is not a valid boolean")


def default_category_for_template(template_id: str) -> str | None:
    return _TEMPLATE_DEFAULT_CATEGORIES.get(str(template_id or "").strip().lower())


def _build_mining_hotspot(fields: dict[str, Any]) -> dict[str, Any]:
    commodity = _require_text(fields.get("commodity"), "commodity")
    body_name = _require_text(fields.get("body_name"), "body_name")
    system_name = _as_text(fields.get("system_name"))
    ring_type = _as_text(fields.get("ring_type"))
    hotspot_strength = _as_text(fields.get("hotspot_strength"))
    res_nearby = _as_text(fields.get("res_nearby"))
    notes = _as_text(fields.get("notes"))

    title = f"{commodity} hotspot - {body_name}"
    body_lines = [
        "Template: Mining Hotspot",
        f"Commodity: {commodity}",
        f"System: {system_name or '-'}",
        f"Body: {body_name}",
        f"Ring type: {ring_type or '-'}",
        f"Hotspot strength: {hotspot_strength or '-'}",
        f"RES nearby: {res_nearby or '-'}",
    ]
    if notes:
        body_lines.append(f"Notes: {notes}")

    payload = {
        "commodity": commodity,
        "ring_type": ring_type,
        "hotspot_strength": hotspot_strength,
        "res_nearby": res_nearby,
        "notes": notes,
    }

    return {
        "category_path": default_category_for_template("mining_hotspot"),
        "title": title,
        "body": "\n".join(body_lines),
        "entry_type": "mining_hotspot",
        "tags": ["template", "mining", "hotspot", commodity.lower()],
        "location": {
            "system_name": system_name,
            "station_name": None,
            "body_name": body_name,
        },
        "source": {"kind": "manual"},
        "payload": {"mining_hotspot": payload},
    }


def _build_trade_route(fields: dict[str, Any]) -> dict[str, Any]:
    from_station = _require_text(fields.get("from_station"), "from_station")
    to_station = _require_text(fields.get("to_station"), "to_station")
    from_system = _as_text(fields.get("from_system"))
    to_system = _as_text(fields.get("to_system"))
    profit_per_t = _as_float(fields.get("profit_per_t"))
    pad_size = _as_text(fields.get("pad_size"))
    distance_ls = _as_float(fields.get("distance_ls"))
    permit_required = _normalize_bool(fields.get("permit_required"))
    notes = _as_text(fields.get("notes"))

    profit_label = (
        f"{int(round(profit_per_t))} cr/t"
        if profit_per_t is not None
        else "? cr/t"
    )
    title = f"{from_station} -> {to_station} - {profit_label}"
    body_lines = [
        "Template: Trade Route",
        f"From: {from_system or '-'} / {from_station}",
        f"To: {to_system or '-'} / {to_station}",
        f"Profit per ton: {profit_label}",
        f"Pad size: {pad_size or '-'}",
        f"Distance LS: {distance_ls if distance_ls is not None else '-'}",
        (
            "Permit required: yes"
            if permit_required is True
            else "Permit required: no"
            if permit_required is False
            else "Permit required: -"
        ),
    ]
    if notes:
        body_lines.append(f"Notes: {notes}")

    payload = {
        "from_system": from_system,
        "from_station": from_station,
        "to_system": to_system,
        "to_station": to_station,
        "profit_per_t": profit_per_t,
        "pad_size": pad_size,
        "distance_ls": distance_ls,
        "permit_required": permit_required,
        "notes": notes,
    }

    return {
        "category_path": default_category_for_template("trade_route"),
        "title": title,
        "body": "\n".join(body_lines),
        "entry_type": "trade_route",
        "tags": ["template", "trade", "route"],
        "location": {
            "system_name": from_system,
            "station_name": from_station,
            "body_name": None,
            "distance_ls": distance_ls,
            "permit_required": permit_required,
        },
        "source": {"kind": "manual"},
        "payload": {"trade_route": payload},
    }


def build_template_entry(template_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    template_key = str(template_id or "").strip().lower()
    if not isinstance(fields, dict):
        raise EntryTemplateError("fields must be an object")

    if template_key == "mining_hotspot":
        return _build_mining_hotspot(fields)
    if template_key == "trade_route":
        return _build_trade_route(fields)
    raise EntryTemplateError(f"unsupported template_id: {template_id}")

