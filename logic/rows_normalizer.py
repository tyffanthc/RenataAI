from __future__ import annotations

import math
import re
import time
from typing import Any, Iterable, Tuple
from datetime import datetime


def pick_value(entry: dict, keys: Iterable[str]) -> Any:
    for key in keys:
        val = entry.get(key)
        if isinstance(val, dict):
            for nested_key in ("value", "distance", "remaining", "ly", "ls"):
                nested_val = val.get(nested_key)
                if nested_val is not None and nested_val != "":
                    return nested_val
        if val is not None and val != "":
            return val
    return None


def is_terraformable(body: dict) -> bool:
    for key in ("terraformable", "is_terraformable"):
        val = body.get(key)
        if isinstance(val, bool):
            return val
    terra_state = body.get("terraforming_state") or body.get("terraform_state") or ""
    if isinstance(terra_state, str):
        return "terraform" in terra_state.lower()
    return False


def normalize_body_rows(
    result: Any,
    *,
    system_keys: Iterable[str],
    bodies_keys: Iterable[str],
    body_name_keys: Iterable[str],
    subtype_keys: Iterable[str],
    distance_keys: Iterable[str],
    scan_value_keys: Iterable[str],
    map_value_keys: Iterable[str],
    jumps_keys: Iterable[str],
) -> Tuple[list[str], list[dict]]:
    route: list[str] = []
    rows: list[dict] = []

    if not result:
        return route, rows

    if isinstance(result, dict):
        segments = (
            result.get("route")
            or result.get("systems")
            or result.get("result")
            or []
        )
    else:
        segments = result

    for seg in segments or []:
        if isinstance(seg, dict):
            system_name = pick_value(seg, system_keys)
            bodies_raw = pick_value(seg, bodies_keys) or []
        else:
            system_name = str(seg)
            bodies_raw = []

        if not system_name:
            continue

        route.append(system_name)
        jumps_val = pick_value(seg, jumps_keys) if isinstance(seg, dict) else None

        if not bodies_raw:
            rows.append(
                {
                    "system_name": system_name,
                    "body_name": None,
                    "subtype": None,
                    "terraformable": None,
                    "distance_ls": None,
                    "value_scan": None,
                    "value_map": None,
                    "jumps": jumps_val,
                    "done": False,
                }
            )
            continue

        for body in bodies_raw:
            if isinstance(body, dict):
                rows.append(
                    {
                        "system_name": system_name,
                        "body_name": pick_value(body, body_name_keys) or "???",
                        "subtype": pick_value(body, subtype_keys),
                        "terraformable": is_terraformable(body),
                        "distance_ls": pick_value(body, distance_keys),
                        "value_scan": pick_value(body, scan_value_keys),
                        "value_map": pick_value(body, map_value_keys),
                        "jumps": jumps_val,
                        "done": False,
                    }
                )
            else:
                rows.append(
                    {
                        "system_name": system_name,
                        "body_name": str(body),
                        "subtype": None,
                        "terraformable": None,
                        "distance_ls": None,
                        "value_scan": None,
                        "value_map": None,
                        "jumps": jumps_val,
                        "done": False,
                    }
                )

    return route, rows


def normalize_trade_rows(result: Any) -> Tuple[list[str], list[dict]]:
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    def _pick_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            for key in (
                "value",
                "label",
                "text",
                "title",
                "ago",
                "name",
                "system",
                "system_name",
                "station",
                "station_name",
                "stationName",
            ):
                nested = _clean_text(value.get(key))
                if nested:
                    return nested
            return None
        text = _clean_text(value)
        return text or None

    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = _clean_text(value)
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

    def _to_int(value: Any) -> int | None:
        num = _to_float(value)
        if num is None:
            return None
        return int(round(num))

    def _pick_trade_raw(entry: dict, keys: Iterable[str]) -> Any:
        for key in keys:
            if key not in entry:
                continue
            value = entry.get(key)
            if isinstance(value, dict):
                for nested_key in (
                    "value",
                    "updated",
                    "updated_ago",
                    "updatedAgo",
                    "updated_at",
                    "updatedAt",
                    "market_updated_at",
                    "marketUpdatedAt",
                    "timestamp",
                    "ts",
                ):
                    nested_value = value.get(nested_key)
                    if nested_value is not None and nested_value != "":
                        return nested_value
            if value is not None and value != "":
                return value
        return None

    def _pick_trade_field(entry: dict, keys: Iterable[str]) -> str | None:
        for key in keys:
            if key not in entry:
                continue
            value = _pick_text(entry.get(key))
            if value:
                return value
        return None

    def _pick_trade_number(entry: dict, keys: Iterable[str]) -> int | None:
        for key in keys:
            if key not in entry:
                continue
            value = entry.get(key)
            num = _to_int(value)
            if num is not None:
                return num
            # Some APIs wrap values in dicts, e.g. {"value": 1234}
            if isinstance(value, dict):
                for nested_key in ("value", "amount", "price", "profit", "total"):
                    num_nested = _to_int(value.get(nested_key))
                    if num_nested is not None:
                        return num_nested
        return None

    def _pick_trade_float(entry: dict, keys: Iterable[str]) -> float | None:
        for key in keys:
            if key not in entry:
                continue
            value = entry.get(key)
            num = _to_float(value)
            if num is not None:
                return num
            if isinstance(value, dict):
                for nested_key in ("value", "distance", "ly", "jump", "length"):
                    num_nested = _to_float(value.get(nested_key))
                    if num_nested is not None:
                        return num_nested
        return None

    def _pick_nested_trade_number(
        entry: dict,
        parent_keys: Iterable[str],
        number_keys: Iterable[str],
    ) -> int | None:
        for parent_key in parent_keys:
            nested = entry.get(parent_key)
            if not isinstance(nested, dict):
                continue
            num = _pick_trade_number(nested, number_keys)
            if num is not None:
                return num
        return None

    def _to_epoch_seconds(value: Any) -> int | None:
        if value is None:
            return None

        if isinstance(value, dict):
            value = _pick_trade_raw(
                value,
                (
                    "value",
                    "timestamp",
                    "ts",
                    "updated_at",
                    "updatedAt",
                    "market_updated_at",
                    "marketUpdatedAt",
                ),
            )

        if isinstance(value, (int, float)):
            epoch = float(value)
        else:
            text = _clean_text(value)
            if not text:
                return None
            try:
                epoch = float(text)
            except Exception:
                parsed = None
                try:
                    parsed = datetime.fromisoformat(text.replace("Z", ""))
                except Exception:
                    parsed = None
                if parsed is None:
                    for fmt in (
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M",
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M",
                    ):
                        try:
                            parsed = datetime.strptime(text, fmt)
                            break
                        except Exception:
                            continue
                if parsed is None:
                    return None
                epoch = parsed.timestamp()

        if epoch > 10_000_000_000:  # milliseconds
            epoch = epoch / 1000.0
        if epoch <= 0:
            return None
        return int(epoch)

    def _format_age_short(seconds: float) -> str:
        sec = max(0, int(round(seconds)))
        if sec < 30:
            return "now"
        if sec < 3600:
            return f"{max(1, sec // 60)}m"
        if sec < 86400:
            return f"{max(1, sec // 3600)}h"
        if sec < 7 * 86400:
            return f"{max(1, sec // 86400)}d"
        if sec < 365 * 86400:
            return f"{max(1, sec // (7 * 86400))}w"
        return f"{max(1, sec // (365 * 86400))}y"

    def _compact_age_from_text(value: Any) -> str | None:
        text = _clean_text(value)
        if not text:
            return None
        lower = text.casefold()
        if lower in {"just now", "now", "teraz", "przed chwila"}:
            return "now"
        if "few second" in lower:
            return "now"
        if "a minute" in lower or "an minute" in lower:
            return "1m"
        if "an hour" in lower or "a hour" in lower:
            return "1h"

        match = re.search(
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
            lower,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        try:
            num = int(match.group("num"))
        except Exception:
            return None
        unit = (match.group("unit") or "").casefold()
        if unit in {"s", "sec", "secs", "second", "seconds", "sek", "sekunda", "sekundy", "sekund"}:
            return "now" if num < 30 else f"{max(1, num // 60)}m"
        if unit in {"m", "min", "mins", "minute", "minutes", "minuta", "minuty", "minut"}:
            return f"{max(1, num)}m"
        if unit in {"h", "hr", "hrs", "hour", "hours", "godz", "godzina", "godziny", "godzin"}:
            return f"{max(1, num)}h"
        if unit in {"d", "day", "days", "dzien", "dni"}:
            return f"{max(1, num)}d"
        if unit in {"w", "week", "weeks", "tydzien", "tygodnie", "tygodni"}:
            return f"{max(1, num)}w"
        if unit in {"month", "months", "miesiac", "miesiace", "miesiecy"}:
            return f"{max(1, num * 30)}d"
        if unit in {"y", "year", "years", "rok", "lata", "lat"}:
            return f"{max(1, num)}y"
        return None

    def _compact_updated(value: Any) -> str | None:
        epoch = _to_epoch_seconds(value)
        if epoch is not None:
            age_seconds = max(0.0, float(int(time.time()) - epoch))
            return _format_age_short(age_seconds)

        short_text = _compact_age_from_text(value)
        if short_text:
            return short_text

        return _pick_text(value)

    def _weighted_average(values: list[tuple[int, int]]) -> int | None:
        if not values:
            return None
        denominator = sum(weight for _value, weight in values if weight > 0)
        if denominator <= 0:
            return None
        numerator = sum(value * weight for value, weight in values if weight > 0)
        return int(round(numerator / denominator))

    def _pick_endpoint(entry: dict, endpoint_keys: Iterable[str]) -> dict:
        for key in endpoint_keys:
            value = entry.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _pick_endpoint_system(endpoint: dict) -> str | None:
        return _pick_trade_field(
            endpoint,
            (
                "system",
                "system_name",
                "from_system",
                "to_system",
                "source_system",
                "destination_system",
                "star_system",
                "name",
            ),
        )

    def _pick_endpoint_station(endpoint: dict) -> str | None:
        station = _pick_trade_field(
            endpoint,
            (
                "station",
                "station_name",
                "from_station",
                "to_station",
                "source_station",
                "destination_station",
                "market",
                "market_name",
                "stationName",
            ),
        )
        if station:
            return station

        has_explicit_system = bool(
            _pick_trade_field(
                endpoint,
                (
                    "system",
                    "system_name",
                    "from_system",
                    "to_system",
                    "source_system",
                    "destination_system",
                    "star_system",
                ),
            )
        )
        if has_explicit_system:
            return None
        return _pick_trade_field(endpoint, ("name",))

    def _normalize_commodities(leg: dict) -> list[dict]:
        raw = (
            leg.get("commodities")
            or leg.get("goods")
            or leg.get("items")
            or leg.get("payload")
            or []
        )
        if isinstance(raw, dict):
            if all(isinstance(v, dict) for v in raw.values()):
                raw_list = list(raw.values())
            else:
                raw_list = [raw]
        elif isinstance(raw, list):
            raw_list = raw
        else:
            raw_list = []

        # Fallback to single commodity shape at leg-level.
        if not raw_list and _pick_trade_field(
            leg,
            ("commodity", "commodity_name", "item", "item_name", "good", "name"),
        ):
            raw_list = [leg]

        normalized: list[dict] = []
        for item in raw_list:
            if isinstance(item, str):
                name = _clean_text(item)
                if not name:
                    continue
                normalized.append({"name": name})
                continue
            if not isinstance(item, dict):
                continue

            name = _pick_trade_field(
                item,
                (
                    "commodity",
                    "commodity_name",
                    "item",
                    "item_name",
                    "good",
                    "name",
                ),
            )
            amount = _pick_trade_number(item, ("amount", "qty", "quantity", "tons", "tonnage", "units"))
            buy_price = _pick_trade_number(item, ("buy_price", "buyPrice", "buy", "buy_price_cr", "buyPriceCr"))
            if buy_price is None:
                buy_price = _pick_nested_trade_number(
                    item,
                    ("source_commodity", "sourceCommodity", "buy_commodity", "buyCommodity", "source"),
                    ("buy_price", "buyPrice", "buy", "price"),
                )
            sell_price = _pick_trade_number(item, ("sell_price", "sellPrice", "sell", "sell_price_cr", "sellPriceCr"))
            if sell_price is None:
                sell_price = _pick_nested_trade_number(
                    item,
                    ("destination_commodity", "destinationCommodity", "sell_commodity", "sellCommodity", "destination"),
                    ("sell_price", "sellPrice", "sell", "price"),
                )
            profit_unit = _pick_trade_number(
                item,
                (
                    "profit_per_ton",
                    "profitPerTon",
                    "profit_per_tonne",
                    "profitPerTonne",
                    "profit",
                    "unit_profit",
                    "unitProfit",
                ),
            )
            total_profit = _pick_trade_number(item, ("total_profit", "totalProfit", "profit_total", "profitTotal"))
            if total_profit is None and profit_unit is not None and amount is not None:
                total_profit = profit_unit * amount

            normalized.append(
                {
                    "name": name,
                    "amount": amount,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "profit_unit": profit_unit,
                    "total_profit": total_profit,
                }
            )
        return normalized

    route: list[str] = []
    rows: list[dict] = []
    running_cumulative_profit: int | None = None

    if not result:
        return route, rows

    core = result
    if isinstance(result, dict):
        core = (
            result.get("result")
            or result.get("routes")
            or result.get("legs")
            or result.get("hops")
            or result
        )

    if not isinstance(core, list):
        return route, rows

    for leg in core:
        if not isinstance(leg, dict):
            continue
        from_endpoint = _pick_endpoint(leg, ("from", "source", "origin", "buy", "start", "sourceLeg"))
        to_endpoint = _pick_endpoint(leg, ("to", "destination", "target", "sell", "end", "targetLeg"))

        from_sys = _pick_trade_field(
            leg,
            (
                "from_system",
                "source_system",
                "origin_system",
                "start_system",
                "fromSystem",
                "sourceSystem",
            ),
        )
        if not from_sys and not from_endpoint:
            from_sys = _pick_trade_field(leg, ("from", "source", "origin"))
        if not from_sys:
            from_sys = _pick_endpoint_system(from_endpoint)

        to_sys = _pick_trade_field(
            leg,
            (
                "to_system",
                "destination_system",
                "target_system",
                "end_system",
                "toSystem",
                "destinationSystem",
            ),
        )
        if not to_sys and not to_endpoint:
            to_sys = _pick_trade_field(leg, ("to", "destination", "target"))
        if not to_sys:
            to_sys = _pick_endpoint_system(to_endpoint)

        from_station = _pick_trade_field(
            leg,
            (
                "from_station",
                "source_station",
                "origin_station",
                "start_station",
                "buy_station",
                "fromStation",
                "sourceStation",
            ),
        )
        if not from_station:
            from_station = _pick_endpoint_station(from_endpoint)

        to_station = _pick_trade_field(
            leg,
            (
                "to_station",
                "destination_station",
                "target_station",
                "end_station",
                "sell_station",
                "toStation",
                "destinationStation",
            ),
        )
        if not to_station:
            to_station = _pick_endpoint_station(to_endpoint)

        commodities = _normalize_commodities(leg)
        commodity_names = [str(c.get("name") or "").strip() for c in commodities if str(c.get("name") or "").strip()]
        commodity_first = commodity_names[0] if commodity_names else None
        commodity_display = None
        if commodity_names:
            commodity_display = commodity_first if len(commodity_names) == 1 else f"{commodity_first} +{len(commodity_names) - 1}"
        else:
            commodity_display = _pick_trade_field(
                leg,
                (
                    "commodity",
                    "commodity_name",
                    "item",
                    "item_name",
                    "name",
                    "good",
                ),
            )

        leg_amount = _pick_trade_number(leg, ("amount", "qty", "quantity", "tons", "tonnage", "units"))
        if leg_amount is None:
            leg_amount = sum(int(c["amount"]) for c in commodities if c.get("amount") is not None) or None

        total_profit = _pick_trade_number(leg, ("total_profit", "totalProfit", "profit_total", "profitTotal"))
        if total_profit is None:
            totals = []
            for c in commodities:
                tp = c.get("total_profit")
                if tp is not None:
                    totals.append(int(tp))
                    continue
                pu = c.get("profit_unit")
                amount = c.get("amount")
                if pu is not None and amount is not None:
                    totals.append(int(pu) * int(amount))
            if totals:
                total_profit = sum(totals)

        profit_per_ton = _pick_trade_number(
            leg,
            (
                "profit_per_ton",
                "profitPerTon",
                "profit_per_tonne",
                "profitPerTonne",
                "profit",
                "estimated_profit",
                "unit_profit",
                "unitProfit",
            ),
        )
        if profit_per_ton is None and total_profit is not None and leg_amount:
            try:
                profit_per_ton = int(round(total_profit / leg_amount))
            except Exception:
                profit_per_ton = None

        buy_price = _pick_trade_number(leg, ("buy_price", "buyPrice", "buy", "buy_price_cr", "buyPriceCr"))
        if buy_price is None:
            weighted_buy = [
                (int(c["buy_price"]), int(c["amount"]))
                for c in commodities
                if c.get("buy_price") is not None and c.get("amount") is not None
            ]
            buy_price = _weighted_average(weighted_buy)

        sell_price = _pick_trade_number(leg, ("sell_price", "sellPrice", "sell", "sell_price_cr", "sellPriceCr"))
        if sell_price is None:
            weighted_sell = [
                (int(c["sell_price"]), int(c["amount"]))
                for c in commodities
                if c.get("sell_price") is not None and c.get("amount") is not None
            ]
            sell_price = _weighted_average(weighted_sell)

        cumulative_profit = _pick_trade_number(
            leg,
            (
                "cumulative_profit",
                "cumulativeProfit",
                "route_cumulative_profit",
                "routeCumulativeProfit",
                "running_profit",
                "runningProfit",
            ),
        )
        cumulative_profit_from_payload = cumulative_profit is not None
        if cumulative_profit is None:
            cumulative_profit = _pick_trade_number(
                to_endpoint,
                (
                    "cumulative_profit",
                    "cumulativeProfit",
                    "running_profit",
                    "runningProfit",
                ),
            )
            cumulative_profit_from_payload = cumulative_profit is not None
        if cumulative_profit is None and total_profit is not None:
            base = running_cumulative_profit if running_cumulative_profit is not None else 0
            cumulative_profit = base + total_profit
        if cumulative_profit is not None:
            running_cumulative_profit = cumulative_profit

        updated_legacy = (
            _pick_trade_field(leg, ("updated_ago", "updatedAgo", "updated", "updated_at", "updatedAt"))
            or _pick_trade_field(to_endpoint, ("updated_ago", "updatedAgo", "updated", "updated_at", "updatedAt"))
            or _pick_trade_field(from_endpoint, ("updated_ago", "updatedAgo", "updated", "updated_at", "updatedAt"))
        )
        updated_at = (
            _pick_trade_field(leg, ("updated_at", "updatedAt"))
            or _pick_trade_field(to_endpoint, ("updated_at", "updatedAt"))
            or _pick_trade_field(from_endpoint, ("updated_at", "updatedAt"))
        )

        buy_updated_raw = _pick_trade_raw(
            from_endpoint,
            ("market_updated_at", "marketUpdatedAt", "updated_ago", "updatedAgo", "updated", "updated_at", "updatedAt"),
        )
        sell_updated_raw = _pick_trade_raw(
            to_endpoint,
            ("market_updated_at", "marketUpdatedAt", "updated_ago", "updatedAgo", "updated", "updated_at", "updatedAt"),
        )
        buy_updated_ago = _compact_updated(buy_updated_raw)
        sell_updated_ago = _compact_updated(sell_updated_raw)
        if buy_updated_ago and sell_updated_ago:
            updated_display = f"{buy_updated_ago} / {sell_updated_ago}"
        else:
            updated_display = buy_updated_ago or sell_updated_ago or updated_legacy or updated_at

        jumps = pick_value(leg, ("jumps", "jump_count"))
        distance_ly = _pick_trade_float(
            leg,
            (
                "distance_ly",
                "distanceLy",
                "distance",
                "jump_distance",
                "jumpDistance",
                "distance_to_system",
                "distanceToSystem",
            ),
        )
        if distance_ly is None:
            distance_ly = _pick_trade_float(
                to_endpoint,
                (
                    "distance_ly",
                    "distanceLy",
                    "distance",
                    "jump_distance",
                    "jumpDistance",
                ),
            )
        if distance_ly is None:
            distance_ly = _pick_trade_float(
                from_endpoint,
                (
                    "distance_ly",
                    "distanceLy",
                    "distance",
                    "jump_distance",
                    "jumpDistance",
                ),
            )

        if from_sys:
            route.append(str(from_sys))
        if to_sys:
            route.append(str(to_sys))

        from_station_final = from_station or "UNKNOWN_STATION"
        to_station_final = to_station or "UNKNOWN_STATION"
        station_for_copy = from_station or to_station or "UNKNOWN_STATION"

        rows.append(
            {
                "from_system": from_sys,
                "to_system": to_sys,
                "from_station": from_station_final,
                "to_station": to_station_final,
                "station": station_for_copy,
                "commodity": commodity_display,
                "commodity_display": commodity_display,
                "commodity_primary": commodity_first,
                "commodities_raw": commodities,
                "amount": leg_amount,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "profit": profit_per_ton,
                "profit_per_ton": profit_per_ton,
                "total_profit": total_profit,
                "cumulative_profit": cumulative_profit,
                "updated_ago": updated_display,
                "updated_at": updated_at,
                "updated_buy_ago": buy_updated_ago,
                "updated_sell_ago": sell_updated_ago,
                "updated_buy_raw": _pick_text(buy_updated_raw),
                "updated_sell_raw": _pick_text(sell_updated_raw),
                "cumulative_profit_from_payload": cumulative_profit_from_payload,
                "distance_ly": distance_ly,
                "jumps": jumps,
            }
        )

    return route, rows


def normalize_neutron_rows(details: list[dict]) -> list[dict]:
    rows: list[dict] = []
    prev_remaining: float | None = None
    prev_entry: dict | None = None
    coords_cache: dict[str, tuple[float, float, float]] = {}

    def _normalize_name(value: Any) -> str:
        return " ".join(str(value or "").strip().split()).lower()

    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _extract_coords(entry: dict | None) -> tuple[float, float, float] | None:
        if not isinstance(entry, dict):
            return None
        coords = entry.get("coords") if isinstance(entry.get("coords"), dict) else None
        if coords is None:
            coords = entry.get("coordinates") if isinstance(entry.get("coordinates"), dict) else None
        if coords:
            x = _coerce_float(coords.get("x"))
            y = _coerce_float(coords.get("y"))
            z = _coerce_float(coords.get("z"))
            if x is not None and y is not None and z is not None:
                return (x, y, z)
        x = _coerce_float(entry.get("x"))
        y = _coerce_float(entry.get("y"))
        z = _coerce_float(entry.get("z"))
        if x is not None and y is not None and z is not None:
            return (x, y, z)
        return None

    def _get_coords(entry: dict | None) -> tuple[float, float, float] | None:
        if not isinstance(entry, dict):
            return None
        name = entry.get("system") or entry.get("system_name")
        key = _normalize_name(name)
        if key and key in coords_cache:
            return coords_cache[key]

        coords = _extract_coords(entry)
        if coords is not None:
            if key:
                coords_cache[key] = coords
            return coords
        return None

    def _distance_from_coords(
        a: tuple[float, float, float],
        b: tuple[float, float, float],
    ) -> float:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        dz = b[2] - a[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    for entry in details or []:
        if not isinstance(entry, dict):
            continue
        remaining_val = entry.get("remaining") or entry.get("remaining_ly")
        try:
            remaining_num = float(remaining_val) if remaining_val is not None else None
        except Exception:
            remaining_num = None

        distance_val = entry.get("distance") or entry.get("distance_ly")
        if distance_val is None:
            prev_coords = _get_coords(prev_entry)
            cur_coords = _get_coords(entry)
            if prev_coords is not None and cur_coords is not None:
                distance_val = round(_distance_from_coords(prev_coords, cur_coords), 2)
            elif remaining_num is not None and prev_remaining is not None:
                delta = prev_remaining - remaining_num
                if delta >= 0:
                    distance_val = delta

        rows.append(
            {
                "system_name": entry.get("system"),
                "distance_ly": distance_val,
                "remaining_ly": entry.get("remaining") or entry.get("remaining_ly"),
                "neutron": entry.get("neutron"),
                "jumps": entry.get("jumps"),
            }
        )
        if remaining_num is not None:
            prev_remaining = remaining_num
        prev_entry = entry
    return rows
