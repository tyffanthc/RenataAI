from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

import config
from logic.cache_store import CacheStore
from logic.spansh_client import SpanshClient
from logic.utils import edsm_client


class _DummyResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class F11StationProviderDetailsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        config.config._settings["spansh_base_url"] = "https://example.test/api"
        config.config._settings["spansh_timeout"] = 5
        config.config._settings["spansh_retries"] = 1
        self._tmp = tempfile.TemporaryDirectory()
        self.client = SpanshClient()
        self.client.cache = CacheStore(
            namespace="spansh_test_station_details",
            base_dir=self._tmp.name,
            provider="spansh",
        )

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        self._tmp.cleanup()

    def test_edsm_fetch_system_stations_details_parses_services_and_distance(self) -> None:
        payload = {
            "stations": [
                {
                    "name": "Ray Gateway",
                    "type": "Orbis Starport",
                    "distanceToArrival": 415,
                    "otherServices": ["Universal Cartographics", "Vista Genomics"],
                }
            ]
        }
        with patch("logic.utils.edsm_client.requests.get", return_value=_DummyResponse(200, payload)):
            rows = edsm_client.fetch_system_stations_details("Diagaundri")

        self.assertEqual(len(rows), 1)
        row = dict(rows[0])
        self.assertEqual(row.get("name"), "Ray Gateway")
        self.assertEqual(row.get("system"), "Diagaundri")
        self.assertEqual(row.get("distance_ls"), 415)
        self.assertIn("Universal Cartographics", list(row.get("services") or []))
        self.assertEqual(row.get("source"), "EDSM")

    def test_spansh_stations_for_system_details_maps_name_rows(self) -> None:
        payload = {
            "stations": [
                {
                    "name": "Carrier K7Q-1HT",
                    "type": "Fleet Carrier",
                    "services": ["Universal Cartographics"],
                    "distance_ly": 10.5,
                },
                "Ray Gateway",
            ]
        }
        with (
            patch("logic.spansh_client.DEBOUNCER.is_allowed", return_value=True),
            patch("logic.spansh_client.requests.get", return_value=_DummyResponse(200, payload)),
        ):
            rows = self.client.stations_for_system_details("Diagaundri")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].get("source"), "SPANSH")
        self.assertTrue(any(str(row.get("name")) == "Ray Gateway" for row in rows))


if __name__ == "__main__":
    unittest.main()

