import copy
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any


ENTRY_SCHEMA_VERSION = 1

_SOURCE_KINDS = {"manual", "journal_event", "stt"}
_LOCATION_KEYS = {
    "system_name",
    "station_name",
    "body_name",
    "coords_lat",
    "coords_lon",
    "distance_ls",
    "permit_required",
}
_DEFAULT_LOCATION = {
    "system_name": None,
    "station_name": None,
    "body_name": None,
    "coords_lat": None,
    "coords_lon": None,
    "distance_ls": None,
    "permit_required": None,
}
_DEFAULT_SOURCE = {
    "kind": "manual",
    "event_name": None,
    "event_time": None,
    "raw_ref": None,
}


class EntryValidationError(ValueError):
    """Raised when entry payload does not match contract."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise EntryValidationError("timestamp must be non-empty ISO string")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception as exc:
        raise EntryValidationError(f"invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_text(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    text = str(value if value is not None else "").strip()
    if not allow_empty and not text:
        raise EntryValidationError(f"{field_name} must be a non-empty string")
    return text


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value if value is not None else "").strip()
    return text if text else None


def _normalize_location(raw: Any) -> dict[str, Any]:
    result = dict(_DEFAULT_LOCATION)
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise EntryValidationError("location must be an object")

    for key, value in raw.items():
        if key not in _LOCATION_KEYS:
            continue
        if key in {"system_name", "station_name", "body_name"}:
            result[key] = _normalize_optional_text(value)
        elif key in {"coords_lat", "coords_lon", "distance_ls"}:
            if value is None or str(value).strip() == "":
                result[key] = None
            else:
                try:
                    result[key] = float(value)
                except Exception as exc:
                    raise EntryValidationError(f"location.{key} must be numeric") from exc
        elif key == "permit_required":
            if value is None:
                result[key] = None
            else:
                result[key] = bool(value)
    return result


def _normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise EntryValidationError("tags must be a list[str]")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        tag = _clean_text(item, "tag").lower()
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def _normalize_links(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise EntryValidationError("links must be a list[object]")
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise EntryValidationError("link item must be an object")
        label = _clean_text(item.get("label"), "links.label")
        url = _clean_text(item.get("url"), "links.url")
        out.append({"label": label, "url": url})
    return out


def _normalize_source(raw: Any) -> dict[str, Any]:
    if raw is None:
        return dict(_DEFAULT_SOURCE)
    if not isinstance(raw, dict):
        raise EntryValidationError("source must be an object")

    out = dict(_DEFAULT_SOURCE)
    kind = str(raw.get("kind") or "manual").strip().lower()
    if kind not in _SOURCE_KINDS:
        raise EntryValidationError(f"source.kind must be one of: {sorted(_SOURCE_KINDS)}")
    out["kind"] = kind

    out["event_name"] = _normalize_optional_text(raw.get("event_name"))
    out["raw_ref"] = _normalize_optional_text(raw.get("raw_ref"))

    event_time = raw.get("event_time")
    if event_time is None or str(event_time).strip() == "":
        out["event_time"] = None
    else:
        parsed = _parse_iso(str(event_time))
        out["event_time"] = parsed.isoformat().replace("+00:00", "Z")
    return out


def _normalize_payload(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise EntryValidationError("payload must be an object")
    return copy.deepcopy(raw)


def normalize_entry(entry: dict[str, Any], *, now_iso: str | None = None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise EntryValidationError("entry must be an object")

    now_value = now_iso or _now_iso()
    _parse_iso(now_value)

    result: dict[str, Any] = {}
    result["id"] = _clean_text(entry.get("id") or str(uuid.uuid4()), "id")
    result["schema_version"] = int(entry.get("schema_version") or ENTRY_SCHEMA_VERSION)
    if result["schema_version"] < 1:
        raise EntryValidationError("schema_version must be >= 1")

    result["category_path"] = _clean_text(entry.get("category_path"), "category_path")
    result["title"] = _clean_text(entry.get("title"), "title")
    result["body"] = _clean_text(entry.get("body", ""), "body", allow_empty=True)

    created_at = entry.get("created_at") or now_value
    updated_at = entry.get("updated_at") or created_at
    result["created_at"] = _parse_iso(str(created_at)).isoformat().replace("+00:00", "Z")
    result["updated_at"] = _parse_iso(str(updated_at)).isoformat().replace("+00:00", "Z")

    result["location"] = _normalize_location(entry.get("location"))
    result["tags"] = _normalize_tags(entry.get("tags"))
    result["entry_type"] = _normalize_optional_text(entry.get("entry_type"))
    result["links"] = _normalize_links(entry.get("links"))
    result["source"] = _normalize_source(entry.get("source"))
    result["payload"] = _normalize_payload(entry.get("payload"))

    result["is_pinned"] = bool(entry.get("is_pinned", False))
    pinned_at = entry.get("pinned_at")
    if result["is_pinned"]:
        result["pinned_at"] = _parse_iso(str(pinned_at or now_value)).isoformat().replace("+00:00", "Z")
    else:
        result["pinned_at"] = None

    return result


class EntryRepository:
    """
    Local offline-first repository for Entry records.
    Storage backend: JSONL.
    """

    def __init__(self, path: str = "user_entries.jsonl") -> None:
        self.path = path
        self._entries: list[dict[str, Any]] = []
        self._index: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8"):
                pass
            self._entries = []
            self._index = {}
            return

        loaded: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except Exception as exc:
                    raise EntryValidationError("invalid JSONL line in entry repository") from exc
                normalized = normalize_entry(record)
                entry_id = str(normalized.get("id") or "")
                if entry_id in seen_ids:
                    raise EntryValidationError(f"duplicate entry id in repository: {entry_id}")
                seen_ids.add(entry_id)
                loaded.append(normalized)

        self._entries = loaded
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index = {str(item["id"]): item for item in self._entries}

    def _persist(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, temp_path = tempfile.mkstemp(prefix="entries_", suffix=".jsonl.tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for item in self._entries:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _clone(self, entry: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(entry)

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        found = self._index.get(str(entry_id))
        return self._clone(found) if found else None

    def create_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        payload = dict(entry or {})
        now_iso = _now_iso()
        payload.setdefault("id", str(uuid.uuid4()))
        payload.setdefault("created_at", now_iso)
        payload.setdefault("updated_at", payload["created_at"])
        payload.setdefault("schema_version", ENTRY_SCHEMA_VERSION)
        normalized = normalize_entry(payload, now_iso=now_iso)

        entry_id = str(normalized["id"])
        if entry_id in self._index:
            raise EntryValidationError(f"entry id already exists: {entry_id}")

        self._entries.append(normalized)
        self._rebuild_index()
        self._persist()
        return self._clone(normalized)

    def update_entry(self, entry_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self._index.get(str(entry_id))
        if current is None:
            raise KeyError(f"entry not found: {entry_id}")
        if not isinstance(patch, dict):
            raise EntryValidationError("patch must be an object")

        merged = self._clone(current)
        for key, value in patch.items():
            if key in {"id", "created_at"}:
                continue
            if key in {"location", "source", "payload"} and isinstance(value, dict) and isinstance(merged.get(key), dict):
                next_value = dict(merged.get(key) or {})
                next_value.update(value)
                merged[key] = next_value
                continue
            merged[key] = value

        merged["updated_at"] = _now_iso()
        normalized = normalize_entry(merged)

        for idx, item in enumerate(self._entries):
            if str(item["id"]) == str(entry_id):
                self._entries[idx] = normalized
                break
        self._rebuild_index()
        self._persist()
        return self._clone(normalized)

    def delete_entry(self, entry_id: str) -> dict[str, Any]:
        entry_key = str(entry_id)
        for idx, item in enumerate(self._entries):
            if str(item["id"]) == entry_key:
                deleted = self._entries.pop(idx)
                self._rebuild_index()
                self._persist()
                return self._clone(deleted)
        raise KeyError(f"entry not found: {entry_id}")

    def pin_entry(self, entry_id: str, pinned: bool) -> dict[str, Any]:
        if pinned:
            return self.update_entry(entry_id, {"is_pinned": True, "pinned_at": _now_iso()})
        return self.update_entry(entry_id, {"is_pinned": False, "pinned_at": None})

    def add_tags(self, entry_id: str, tags: list[str]) -> dict[str, Any]:
        current = self._index.get(str(entry_id))
        if current is None:
            raise KeyError(f"entry not found: {entry_id}")
        merged = set(_normalize_tags(current.get("tags")))
        merged.update(_normalize_tags(tags))
        return self.update_entry(entry_id, {"tags": sorted(merged)})

    def remove_tags(self, entry_id: str, tags: list[str]) -> dict[str, Any]:
        current = self._index.get(str(entry_id))
        if current is None:
            raise KeyError(f"entry not found: {entry_id}")
        drop = set(_normalize_tags(tags))
        kept = [tag for tag in _normalize_tags(current.get("tags")) if tag not in drop]
        return self.update_entry(entry_id, {"tags": kept})

    def create_entry_from_journal(
        self,
        event: dict[str, Any],
        category_path: str,
        template: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise EntryValidationError("event must be an object")
        event_name = _normalize_optional_text(event.get("event")) or "JournalEvent"
        system_name = _normalize_optional_text(event.get("StarSystem"))
        station_name = _normalize_optional_text(event.get("StationName"))
        body_name = _normalize_optional_text(event.get("BodyName"))
        timestamp = _normalize_optional_text(event.get("timestamp")) or _now_iso()
        title_target = station_name or system_name or body_name or "unknown"
        title = f"{event_name} - {title_target}"

        body_lines = [
            f"Event: {event_name}",
            f"System: {system_name or '-'}",
            f"Station: {station_name or '-'}",
            f"Body: {body_name or '-'}",
        ]
        payload = {
            "category_path": category_path,
            "title": title,
            "body": "\n".join(body_lines),
            "entry_type": _normalize_optional_text(template),
            "location": {
                "system_name": system_name,
                "station_name": station_name,
                "body_name": body_name,
            },
            "source": {
                "kind": "journal_event",
                "event_name": event_name,
                "event_time": timestamp,
                "raw_ref": _normalize_optional_text(event.get("raw_ref")),
            },
            "payload": copy.deepcopy(event),
        }
        return self.create_entry(payload)

    def list_entries(
        self,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        items = [self._clone(item) for item in self._entries]
        filtered = self._apply_filters(items, filters or {})
        sorted_items = self._apply_sort(filtered, sort)

        start = max(0, int(offset or 0))
        if limit is None:
            return sorted_items[start:]
        size = max(0, int(limit))
        return sorted_items[start:start + size]

    def _apply_filters(self, items: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
        if not filters:
            return items

        text = _normalize_optional_text(filters.get("text"))
        tags = _normalize_tags(filters.get("tags")) if "tags" in filters else []
        entry_type = _normalize_optional_text(filters.get("entry_type"))
        source_kind = _normalize_optional_text(filters.get("source_kind"))
        category_prefix = _normalize_optional_text(filters.get("category_path_prefix"))
        has_system = filters.get("has_system")
        has_station = filters.get("has_station")
        has_body = filters.get("has_body")
        has_coords = filters.get("has_coords")
        pinned = filters.get("is_pinned")

        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        dt_from = _parse_iso(str(date_from)) if date_from else None
        dt_to = _parse_iso(str(date_to)) if date_to else None

        out: list[dict[str, Any]] = []
        for item in items:
            if text:
                hay = " ".join(
                    [
                        str(item.get("title") or ""),
                        str(item.get("body") or ""),
                        " ".join(item.get("tags") or []),
                        str((item.get("location") or {}).get("system_name") or ""),
                        str((item.get("location") or {}).get("station_name") or ""),
                        str((item.get("location") or {}).get("body_name") or ""),
                    ]
                ).lower()
                if text.lower() not in hay:
                    continue

            if tags:
                item_tags = set(_normalize_tags(item.get("tags")))
                if not set(tags).issubset(item_tags):
                    continue

            if entry_type and str(item.get("entry_type") or "").lower() != entry_type.lower():
                continue
            if source_kind and str((item.get("source") or {}).get("kind") or "").lower() != source_kind.lower():
                continue
            if category_prefix and not str(item.get("category_path") or "").startswith(category_prefix):
                continue

            loc = item.get("location") or {}
            if has_system is True and not loc.get("system_name"):
                continue
            if has_system is False and loc.get("system_name"):
                continue
            if has_station is True and not loc.get("station_name"):
                continue
            if has_station is False and loc.get("station_name"):
                continue
            if has_body is True and not loc.get("body_name"):
                continue
            if has_body is False and loc.get("body_name"):
                continue

            if has_coords is True and (loc.get("coords_lat") is None or loc.get("coords_lon") is None):
                continue
            if has_coords is False and (loc.get("coords_lat") is not None and loc.get("coords_lon") is not None):
                continue

            if pinned is True and not bool(item.get("is_pinned")):
                continue
            if pinned is False and bool(item.get("is_pinned")):
                continue

            if dt_from or dt_to:
                created = _parse_iso(str(item.get("created_at")))
                if dt_from and created < dt_from:
                    continue
                if dt_to and created > dt_to:
                    continue

            out.append(item)
        return out

    def _apply_sort(self, items: list[dict[str, Any]], sort: dict[str, Any] | str | None) -> list[dict[str, Any]]:
        sort_by = "updated_at"
        descending = True

        if isinstance(sort, str):
            key = sort.strip().lower()
            if key in {"newest", "created_desc"}:
                sort_by, descending = "created_at", True
            elif key in {"oldest", "created_asc"}:
                sort_by, descending = "created_at", False
            elif key in {"updated_desc", "last_updated"}:
                sort_by, descending = "updated_at", True
            elif key == "updated_asc":
                sort_by, descending = "updated_at", False
            elif key == "system_az":
                sort_by, descending = "system_name", False
            elif key == "system_za":
                sort_by, descending = "system_name", True
            elif key == "title_az":
                sort_by, descending = "title", False
            elif key == "title_za":
                sort_by, descending = "title", True
        elif isinstance(sort, dict):
            sort_by = str(sort.get("by") or sort_by).strip().lower()
            descending = bool(sort.get("descending", descending))

        def _key(item: dict[str, Any]) -> Any:
            location = item.get("location") or {}
            if sort_by == "created_at":
                return _parse_iso(str(item.get("created_at")))
            if sort_by == "updated_at":
                return _parse_iso(str(item.get("updated_at")))
            if sort_by == "system_name":
                return str(location.get("system_name") or "").lower()
            if sort_by == "entry_type":
                return str(item.get("entry_type") or "").lower()
            if sort_by == "title":
                return str(item.get("title") or "").lower()
            return _parse_iso(str(item.get("updated_at")))

        return sorted(items, key=_key, reverse=descending)
