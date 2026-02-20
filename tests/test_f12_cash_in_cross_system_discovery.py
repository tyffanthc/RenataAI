from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.cash_in_station_candidates import station_candidates_cross_system_from_providers
from logic.events import cash_in_assistant


class F12CashInCrossSystemDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F12_ORIGIN"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = True
        config.config._settings["cash_in.cross_system_radius_ly"] = 120.0
        config.config._settings["cash_in.cross_system_max_systems"] = 8
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.providers.system_lookup_online"] = True
        config.config._settings["features.trade.station_lookup_online"] = True

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

    @staticmethod
    def _base_payload() -> dict:
        return {
            "system": "F12_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 5_000_000.0,
            "cash_in_session_estimated": 21_500_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_cross_system_discovery_returns_service_matched_candidates(self) -> None:
        nearby_systems = [
            {"name": "F12_ORIGIN", "distance_ly": 0.0},
            {"name": "F12_BETA", "distance_ly": 18.0},
            {"name": "F12_GAMMA", "distance_ly": 33.0},
        ]

        def _provider_side_effect(system_name: str, **_kwargs):
            if system_name == "F12_BETA":
                return [
                    {
                        "name": "Vista Point",
                        "system_name": "F12_BETA",
                        "type": "station",
                        "services": {"has_uc": False, "has_vista": True},
                        "source": "EDSM",
                    }
                ]
            if system_name == "F12_GAMMA":
                return [
                    {
                        "name": "Gamma Hub",
                        "system_name": "F12_GAMMA",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "source": "SPANSH",
                    }
                ]
            return []

        with (
            patch(
                "logic.cash_in_station_candidates.edsm_nearby_systems",
                return_value=nearby_systems,
            ),
            patch(
                "logic.cash_in_station_candidates.station_candidates_for_system_from_providers",
                side_effect=_provider_side_effect,
            ),
        ):
            candidates, meta = station_candidates_cross_system_from_providers(
                "F12_ORIGIN",
                service="uc",
                include_edsm=True,
                include_spansh=True,
                radius_ly=80.0,
                max_systems=6,
                limit=12,
            )

        self.assertEqual(len(candidates), 1)
        row = dict(candidates[0])
        self.assertEqual(row.get("name"), "Gamma Hub")
        self.assertEqual(row.get("system_name"), "F12_GAMMA")
        self.assertEqual(float(row.get("distance_ly") or 0.0), 33.0)
        self.assertEqual(int(meta.get("systems_requested") or 0), 2)
        self.assertEqual(int(meta.get("systems_with_candidates") or 0), 1)

    def test_runtime_uses_cross_system_when_local_candidates_miss_service(self) -> None:
        payload = self._base_payload()
        local_no_service = [
            {
                "name": "Local Carrier",
                "system_name": "F12_ORIGIN",
                "type": "fleet_carrier",
                "services": {"has_uc": False, "has_vista": True},
                "source": "EDSM",
            }
        ]
        cross_candidates = [
            {
                "name": "Nearest UC Hub",
                "system_name": "F12_NEAR",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 27.0,
                "source": "EDSM",
            }
        ]
        cross_meta = {"systems_requested": 3, "systems_with_candidates": 1}

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=local_no_service,
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=(cross_candidates, cross_meta),
            ) as cross_mock,
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertTrue(cross_mock.called)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        candidates = [dict(item) for item in (structured.get("station_candidates") or []) if isinstance(item, dict)]
        uc_candidates = [
            row
            for row in candidates
            if bool((row.get("services") or {}).get("has_uc"))
        ]

        self.assertEqual(str(station_meta.get("cross_system_lookup_status") or ""), "cross_system")
        self.assertEqual(int(station_meta.get("cross_system_systems_requested") or 0), 3)
        self.assertEqual(int(station_meta.get("cross_system_systems_with_candidates") or 0), 1)
        self.assertEqual(str(station_meta.get("source_status") or ""), "providers_cross_system")
        self.assertGreaterEqual(len(uc_candidates), 1)
        self.assertTrue(any(str(row.get("system_name") or "") == "F12_NEAR" for row in uc_candidates))

    def test_runtime_skips_cross_system_when_local_service_match_exists(self) -> None:
        payload = self._base_payload()
        local_uc = [
            {
                "name": "Origin UC",
                "system_name": "F12_ORIGIN",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 0.0,
                "source": "EDSM",
            }
        ]
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=local_uc,
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=([], {"systems_requested": 0, "systems_with_candidates": 0}),
            ) as cross_mock,
            patch("logic.events.cash_in_assistant.emit_insight"),
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertFalse(cross_mock.called)


if __name__ == "__main__":
    unittest.main()

