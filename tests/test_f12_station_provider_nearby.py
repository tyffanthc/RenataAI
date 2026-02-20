from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.utils import edsm_client
from logic.utils.http_edsm import edsm_nearby_systems


class _DummyResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class F12StationProviderNearbyTests(unittest.TestCase):
    def test_edsm_fetch_nearby_systems_parses_distance(self) -> None:
        payload = [
            {"name": "Origin", "distance": 0.0},
            {"name": "Near A", "distance": 11.2, "coords": {"x": 1, "y": 2, "z": 3}},
            {"name": "Near B", "distance": 34.0},
        ]
        with patch("logic.utils.edsm_client.requests.get", return_value=_DummyResponse(200, payload)):
            rows = edsm_client.fetch_nearby_systems("Origin", radius_ly=80.0, limit=8)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].get("name"), "Near A")
        self.assertEqual(float(rows[0].get("distance_ly") or 0.0), 11.2)
        self.assertEqual(rows[0].get("source"), "EDSM")

    def test_http_wrapper_returns_empty_when_edsm_disabled(self) -> None:
        with patch("logic.utils.http_edsm.is_edsm_enabled", return_value=False):
            rows = edsm_nearby_systems("Origin", radius_ly=60.0, limit=6)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()

