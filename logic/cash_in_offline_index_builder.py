from __future__ import annotations

import gzip
import io
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from logic.utils.renata_log import log_event_throttled

ProgressCallback = Callable[[float, str], None]


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        text = _as_text(value).replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None


def _to_iso_date(value: Any) -> str:
    text = _as_text(value)
    if not text:
        return ""
    try:
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        return ""


def _normalize_station_type(value: Any) -> str:
    text = _as_text(value).lower()
    if "carrier" in text:
        return "fleet_carrier"
    if "outpost" in text:
        return "outpost"
    if "settlement" in text:
        return "settlement"
    return "station"


def _service_token(value: Any) -> str:
    raw = _as_text(value).casefold()
    return "".join(ch for ch in raw if ch.isalnum())


def _has_uc_service(services: list[Any]) -> bool:
    for item in services:
        token = _service_token(item)
        if not token:
            continue
        if "universalcartographics" in token or token == "cartographics":
            return True
    return False


def _has_vista_service(services: list[Any]) -> bool:
    for item in services:
        token = _service_token(item)
        if not token:
            continue
        if "vistagenomics" in token or token == "genomics":
            return True
    return False


def _iter_json_array_objects(
    text_stream: io.TextIOBase,
    *,
    chunk_size: int = 262_144,
):
    decoder = json.JSONDecoder()
    buffer = ""
    in_array = False

    while True:
        chunk = text_stream.read(chunk_size)
        eof = chunk == ""
        if chunk:
            buffer += chunk

        pos = 0
        while True:
            size = len(buffer)
            while pos < size and buffer[pos] in " \r\n\t,":
                pos += 1

            if not in_array:
                if pos >= size:
                    break
                if buffer[pos] == "[":
                    in_array = True
                    pos += 1
                    continue
                raise ValueError("Spansh dump is not a JSON array.")

            if pos >= size:
                break
            if buffer[pos] == "]":
                return

            try:
                item, end = decoder.raw_decode(buffer, pos)
            except json.JSONDecodeError:
                break
            yield item
            pos = end

        if pos > 0:
            buffer = buffer[pos:]

        if eof:
            tail = buffer.strip()
            if not tail or tail == "]":
                return
            raise ValueError("Malformed or truncated Spansh dump payload.")


def _emit_progress(
    progress_callback: ProgressCallback | None,
    percent: float,
    message: str,
) -> None:
    if not callable(progress_callback):
        return
    clamped = max(0.0, min(100.0, float(percent)))
    progress_callback(clamped, message)


def build_offline_index_from_spansh_dump(
    dump_path: str,
    output_path: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> Dict[str, Any]:
    input_path = os.path.abspath(_as_text(dump_path))
    out_path = os.path.abspath(_as_text(output_path))
    if not input_path:
        raise ValueError("Missing dump path.")
    if not out_path:
        raise ValueError("Missing output path.")
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Dump file not found: {input_path}")

    output_dir = os.path.dirname(out_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    total_bytes = max(1, int(os.path.getsize(input_path)))
    systems_processed = 0
    systems_with_relevant_stations = 0
    stations_written = 0
    latest_index_date = ""
    systems_coords: dict[str, tuple[float, float, float]] = {}
    started_at = time.monotonic()
    temp_station_path = ""
    output_tmp = f"{out_path}.tmp"

    _emit_progress(progress_callback, 0.0, "Start konwersji dumpa do offline index...")

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".stations.tmp",
        ) as temp_station:
            temp_station_path = temp_station.name
            temp_station.write("[")
            first_station_row = True

            with open(input_path, "rb") as raw_handle:
                with gzip.GzipFile(fileobj=raw_handle, mode="rb") as gz_handle:
                    text_handle = io.TextIOWrapper(gz_handle, encoding="utf-8")
                    for system_obj in _iter_json_array_objects(text_handle):
                        systems_processed += 1
                        if not isinstance(system_obj, dict):
                            continue

                        system_name = _as_text(system_obj.get("name"))
                        coords_obj = system_obj.get("coords") or {}
                        cx = _safe_float(
                            coords_obj.get("x") if isinstance(coords_obj, dict) else None
                        )
                        cy = _safe_float(
                            coords_obj.get("y") if isinstance(coords_obj, dict) else None
                        )
                        cz = _safe_float(
                            coords_obj.get("z") if isinstance(coords_obj, dict) else None
                        )
                        has_system_coords = (
                            system_name != ""
                            and cx is not None
                            and cy is not None
                            and cz is not None
                        )

                        system_date = _to_iso_date(system_obj.get("date"))
                        if system_date and (not latest_index_date or system_date > latest_index_date):
                            latest_index_date = system_date

                        stations = system_obj.get("stations")
                        if not isinstance(stations, list):
                            stations = []

                        wrote_in_this_system = False
                        for station in stations:
                            if not isinstance(station, dict):
                                continue

                            station_name = _as_text(station.get("name"))
                            if not station_name or not system_name:
                                continue

                            services_raw = station.get("services")
                            services: list[Any]
                            if isinstance(services_raw, list):
                                services = list(services_raw)
                            elif isinstance(services_raw, dict):
                                services = list(services_raw.keys())
                            else:
                                services = []

                            has_uc = _has_uc_service(services)
                            has_vista = _has_vista_service(services)
                            if not has_uc and not has_vista:
                                continue
                            if not has_system_coords:
                                continue

                            if has_system_coords and system_name not in systems_coords:
                                systems_coords[system_name] = (float(cx), float(cy), float(cz))

                            freshness_ts = _as_text(
                                station.get("updateTime")
                                or station.get("updatedAt")
                                or station.get("updated_at")
                                or system_obj.get("date")
                            )
                            station_row = {
                                "name": station_name,
                                "system_name": system_name,
                                "type": _normalize_station_type(station.get("type")),
                                "services": {
                                    "has_uc": bool(has_uc),
                                    "has_vista": bool(has_vista),
                                },
                                "distance_ls": _safe_float(station.get("distanceToArrival")),
                                "freshness_ts": freshness_ts,
                            }

                            if not first_station_row:
                                temp_station.write(",")
                            json.dump(
                                station_row,
                                temp_station,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                            first_station_row = False
                            stations_written += 1
                            wrote_in_this_system = True

                        if wrote_in_this_system:
                            systems_with_relevant_stations += 1

                        if systems_processed % 64 == 0:
                            consumed = int(raw_handle.tell())
                            percent = min(95.0, (consumed * 95.0) / float(total_bytes))
                            _emit_progress(
                                progress_callback,
                                percent,
                                (
                                    "Konwersja dumpa: systemy="
                                    f"{systems_processed}, wpisy={stations_written}"
                                ),
                            )

            temp_station.write("]")

        built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        if not latest_index_date:
            latest_index_date = built_at[:10]
        systems_rows = [
            {
                "name": name,
                "coords": {
                    "x": coords[0],
                    "y": coords[1],
                    "z": coords[2],
                },
            }
            for name, coords in sorted(systems_coords.items(), key=lambda x: x[0].casefold())
        ]
        meta = {
            "source": "spansh_galaxy_stations_dump",
            "dump_path": input_path,
            "output_path": out_path,
            "built_at": built_at,
            "index_date": latest_index_date,
            "systems_processed": systems_processed,
            "systems_with_relevant_stations": systems_with_relevant_stations,
            "stations_written": stations_written,
            "systems_with_coords": len(systems_rows),
        }

        with open(output_tmp, "w", encoding="utf-8", newline="\n") as out_handle:
            out_handle.write("{")
            out_handle.write('"meta":')
            json.dump(meta, out_handle, ensure_ascii=False, separators=(",", ":"))
            out_handle.write(',"index_date":')
            json.dump(latest_index_date, out_handle, ensure_ascii=False)
            out_handle.write(',"stations":')
            with open(temp_station_path, "r", encoding="utf-8") as temp_station:
                while True:
                    chunk = temp_station.read(262_144)
                    if not chunk:
                        break
                    out_handle.write(chunk)
            out_handle.write(',"systems_rows":')
            json.dump(systems_rows, out_handle, ensure_ascii=False, separators=(",", ":"))
            out_handle.write("}")

        os.replace(output_tmp, out_path)
        elapsed_sec = round(max(0.0, time.monotonic() - started_at), 3)
        result = dict(meta)
        result["duration_sec"] = elapsed_sec
        _emit_progress(
            progress_callback,
            100.0,
            (
                "Konwersja zakonczona: "
                f"stations={stations_written}, systems={systems_with_relevant_stations}"
            ),
        )
        return result
    finally:
        try:
            if temp_station_path and os.path.isfile(temp_station_path):
                os.remove(temp_station_path)
        except Exception as exc:
            log_event_throttled(
                "cash_in_offline_index.cleanup.temp_station",
                5000,
                "WARN",
                "Offline index builder: failed to remove temp station file",
                path=str(temp_station_path or ""),
                error=f"{type(exc).__name__}: {exc}",
            )
        try:
            if os.path.isfile(output_tmp):
                os.remove(output_tmp)
        except Exception as exc:
            log_event_throttled(
                "cash_in_offline_index.cleanup.output_tmp",
                5000,
                "WARN",
                "Offline index builder: failed to remove temp output file",
                path=str(output_tmp or ""),
                error=f"{type(exc).__name__}: {exc}",
            )
