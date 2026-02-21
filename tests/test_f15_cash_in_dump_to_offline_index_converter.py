from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest

from logic.cash_in_offline_index_builder import build_offline_index_from_spansh_dump


class F15CashInDumpToOfflineIndexConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dump_path = os.path.join(self._tmp.name, "galaxy_stations.json.gz")
        self.index_path = os.path.join(self._tmp.name, "offline_station_index.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_dump(self, payload) -> None:
        with gzip.open(self.dump_path, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

    def test_build_converter_writes_offline_index_with_services_and_coords(self) -> None:
        payload = [
            {
                "name": "Diagaundri",
                "coords": {"x": 10.0, "y": 20.0, "z": 30.0},
                "date": "2026-02-20 14:08:06+00",
                "stations": [
                    {
                        "name": "Ray Gateway",
                        "type": "Orbis Starport",
                        "services": ["Dock", "Universal Cartographics"],
                        "distanceToArrival": 415,
                        "updateTime": "2026-02-20 15:00:00+00",
                    },
                    {
                        "name": "Ignored No Service",
                        "type": "Outpost",
                        "services": ["Dock", "Repair"],
                        "distanceToArrival": 90,
                    },
                ],
            },
            {
                "name": "Outopps UA-L c22-0",
                "coords": {"x": 110.0, "y": 220.0, "z": 330.0},
                "date": "2026-02-21 10:31:52+00",
                "stations": [
                    {
                        "name": "Carrier K7Q-1HT",
                        "type": "Drake-Class Carrier",
                        "services": ["Dock", "Vista Genomics"],
                        "distanceToArrival": 250,
                    }
                ],
            },
            {
                "name": "NoCoordsSystem",
                "date": "2026-02-21 11:00:00+00",
                "stations": [
                    {
                        "name": "NoCoords Station",
                        "type": "Coriolis Starport",
                        "services": ["Universal Cartographics"],
                    }
                ],
            },
        ]
        self._write_dump(payload)

        progress_events: list[tuple[float, str]] = []
        result = build_offline_index_from_spansh_dump(
            self.dump_path,
            self.index_path,
            progress_callback=lambda p, s: progress_events.append((float(p), str(s))),
        )

        self.assertTrue(os.path.isfile(self.index_path))
        self.assertGreaterEqual(len(progress_events), 1)
        self.assertGreaterEqual(progress_events[-1][0], 99.0)
        self.assertEqual(int(result.get("stations_written") or 0), 2)
        self.assertEqual(int(result.get("systems_with_relevant_stations") or 0), 2)
        self.assertEqual(str(result.get("index_date") or ""), "2026-02-21")

        with open(self.index_path, "r", encoding="utf-8") as handle:
            index_payload = json.load(handle)

        stations = list(index_payload.get("stations") or [])
        self.assertEqual(len(stations), 2)
        station_names = {str(row.get("name")) for row in stations}
        self.assertEqual(station_names, {"Ray Gateway", "Carrier K7Q-1HT"})

        ray = next(row for row in stations if row.get("name") == "Ray Gateway")
        carrier = next(row for row in stations if row.get("name") == "Carrier K7Q-1HT")
        self.assertEqual(ray.get("system_name"), "Diagaundri")
        self.assertEqual(carrier.get("type"), "fleet_carrier")
        self.assertTrue(bool((ray.get("services") or {}).get("has_uc")))
        self.assertTrue(bool((carrier.get("services") or {}).get("has_vista")))

        systems_rows = list(index_payload.get("systems_rows") or [])
        system_names = {str(row.get("name")) for row in systems_rows}
        self.assertEqual(system_names, {"Diagaundri", "Outopps UA-L c22-0"})

    def test_build_converter_raises_for_missing_dump(self) -> None:
        with self.assertRaises(FileNotFoundError):
            build_offline_index_from_spansh_dump(
                os.path.join(self._tmp.name, "missing.json.gz"),
                self.index_path,
            )

    def test_build_converter_raises_for_non_array_dump(self) -> None:
        with gzip.open(self.dump_path, "wt", encoding="utf-8") as handle:
            handle.write('{"not":"array"}')
        with self.assertRaises(ValueError):
            build_offline_index_from_spansh_dump(
                self.dump_path,
                self.index_path,
            )


if __name__ == "__main__":
    unittest.main()
