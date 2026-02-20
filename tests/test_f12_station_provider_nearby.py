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

    def test_edsm_fetch_nearby_systems_fallbacks_to_coords_when_name_lookup_empty(self) -> None:
        first_payload = []
        second_payload = [
            {"name": "Near Coord A", "distance": 42.0, "coords": {"x": 10, "y": 11, "z": 12}},
        ]
        with patch(
            "logic.utils.edsm_client.requests.get",
            side_effect=[
                _DummyResponse(200, first_payload),
                _DummyResponse(200, second_payload),
            ],
        ) as get_mock:
            rows = edsm_client.fetch_nearby_systems(
                "Origin",
                radius_ly=1200.0,
                limit=8,
                origin_coords=[1.25, 2.5, 3.75],
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("name"), "Near Coord A")
        self.assertEqual(get_mock.call_count, 2)
        first_params = dict(get_mock.call_args_list[0].kwargs.get("params") or {})
        second_params = dict(get_mock.call_args_list[1].kwargs.get("params") or {})
        self.assertIn("systemName", first_params)
        self.assertEqual(first_params.get("systemName"), "Origin")
        self.assertNotIn("systemName", second_params)
        self.assertEqual(float(second_params.get("x")), 1.25)
        self.assertEqual(float(second_params.get("y")), 2.5)
        self.assertEqual(float(second_params.get("z")), 3.75)


if __name__ == "__main__":
    unittest.main()
