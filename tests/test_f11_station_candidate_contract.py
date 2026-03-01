from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.cash_in_station_candidates import (
    build_station_candidates,
    filter_candidates_by_service,
    merge_station_candidates,
    normalize_station_candidate,
)
from logic.events import cash_in_assistant


class F11StationCandidateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._orig_settings = dict(config.config._settings)
        app_state.current_system = "F11_STATION_CONTRACT_SYSTEM"
        app_state.current_station = "Local Hub"
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.station_candidates_limit"] = 24

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        config.config._settings = self._orig_settings

    def test_normalize_station_candidate_maps_required_fields(self) -> None:
        raw = {
            "name": "Test Carrier K7Q-1HT",
            "system": "F11_STATION_CONTRACT_SYSTEM",
            "type": "Fleet Carrier",
            "services": ["Universal Cartographics", "Vista Genomics"],
            "distanceToArrival": 1500,
            "distance_ly": 22.5,
            "source": "EDSM",
            "updatedAt": "2026-02-19T22:10:00Z",
        }
        row = normalize_station_candidate(raw)
        self.assertIsNotNone(row)
        candidate = dict(row or {})
        self.assertEqual(candidate.get("name"), "Test Carrier K7Q-1HT")
        self.assertEqual(candidate.get("system_name"), "F11_STATION_CONTRACT_SYSTEM")
        self.assertEqual(candidate.get("type"), "fleet_carrier")
        services = dict(candidate.get("services") or {})
        self.assertTrue(bool(services.get("has_uc")))
        self.assertTrue(bool(services.get("has_vista")))
        self.assertEqual(float(candidate.get("distance_ly") or 0.0), 22.5)
        self.assertEqual(float(candidate.get("distance_ls") or 0.0), 1500.0)
        self.assertEqual(candidate.get("source"), "EDSM")
        self.assertEqual(candidate.get("freshness_ts"), "2026-02-19T22:10:00Z")

    def test_merge_station_candidates_dedupes_and_combines_service_coverage(self) -> None:
        rows = [
            {
                "name": "Ray Gateway",
                "system_name": "Diagaundri",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "source": "EDSM",
                "distance_ly": 14.0,
            },
            {
                "name": "Ray Gateway",
                "system_name": "Diagaundri",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "source": "SPANSH",
                "distance_ly": 12.0,
            },
        ]
        merged = merge_station_candidates(rows, limit=10)
        self.assertEqual(len(merged), 1)
        item = dict(merged[0])
        self.assertEqual(item.get("source"), "EDSM+SPANSH")
        services = dict(item.get("services") or {})
        self.assertTrue(bool(services.get("has_uc")))
        self.assertTrue(bool(services.get("has_vista")))
        self.assertEqual(float(item.get("distance_ly") or 0.0), 12.0)

    def test_build_and_filter_candidates_service_aware(self) -> None:
        rows = build_station_candidates(
            [
                {"name": "A", "system_name": "S", "services": ["Universal Cartographics"]},
                {"name": "B", "system_name": "S", "services": ["Vista Genomics"]},
                {"name": "C", "system_name": "S"},
            ],
            default_system="S",
            source_hint="TEST",
        )
        uc_only = filter_candidates_by_service(rows, service="uc")
        vista_only = filter_candidates_by_service(rows, service="vista")
        self.assertEqual([item.get("name") for item in uc_only], ["A"])
        self.assertEqual([item.get("name") for item in vista_only], ["B"])

    def test_merge_station_candidates_uses_station_name_when_name_missing(self) -> None:
        rows = [
            {
                "name": "",
                "station_name": "Alpha Port",
                "system_name": "Diagaundri",
                "source": "OFFLINE_INDEX",
                "distance_ly": 10.0,
            },
            {
                "name": "",
                "station_name": "Beta Port",
                "system_name": "Diagaundri",
                "source": "OFFLINE_INDEX",
                "distance_ly": 12.0,
            },
        ]
        merged = merge_station_candidates(rows, limit=10)
        self.assertEqual(len(merged), 2)
        names = {str(item.get("station_name") or item.get("name") or "") for item in merged}
        self.assertEqual(names, {"Alpha Port", "Beta Port"})

    def test_trigger_cash_in_assistant_includes_station_candidates_from_payload(self) -> None:
        payload = {
            "system": "F11_STATION_CONTRACT_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 5_000_000.0,
            "cash_in_session_estimated": 17_000_000.0,
            "station_candidates": [
                {
                    "name": "Ray Gateway",
                    "system_name": "Diagaundri",
                    "type": "Station",
                    "services": ["Universal Cartographics"],
                    "distance_ly": 12.0,
                    "source": "EDSM",
                },
                {
                    "name": "Vista Point",
                    "system_name": "Diagaundri",
                    "type": "Fleet Carrier",
                    "services": ["Vista Genomics"],
                    "distance_ly": 9.0,
                    "source": "SPANSH",
                },
            ],
        }
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        candidates = list(structured.get("station_candidates") or [])
        meta = dict(structured.get("station_candidates_meta") or {})
        self.assertEqual(len(candidates), 2)
        self.assertEqual(meta.get("source_status"), "payload")
        self.assertEqual(int(meta.get("uc_count") or 0), 1)
        self.assertEqual(int(meta.get("vista_count") or 0), 1)

    def test_trigger_cash_in_assistant_uses_provider_lookup_when_enabled(self) -> None:
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        payload = {
            "system": "F11_STATION_CONTRACT_SYSTEM",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 2_000_000.0,
            "cash_in_session_estimated": 8_000_000.0,
        }
        provider_candidates = [
            {
                "name": "Provider Hub",
                "system_name": "F11_STATION_CONTRACT_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 4.0,
                "source": "EDSM",
            }
        ]
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=provider_candidates,
            ) as provider_mock,
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertTrue(provider_mock.called)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        meta = dict(structured.get("station_candidates_meta") or {})
        self.assertEqual(meta.get("source_status"), "providers")
        self.assertEqual(int(meta.get("count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
