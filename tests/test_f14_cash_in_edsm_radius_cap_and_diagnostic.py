from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F14CashInEdsmRadiusCapDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F14_CAP_TEST_SYSTEM"
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.cross_system_discovery_enabled"] = True
        config.config._settings["cash_in.cross_system_radius_ly"] = 20_000.0
        config.config._settings["cash_in.cross_system_max_systems"] = 30
        config.config._settings["features.providers.system_lookup_online"] = True
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.trade.station_lookup_online"] = False

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

    @staticmethod
    def _payload() -> dict:
        return {
            "system": "F14_CAP_TEST_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 7_000_000.0,
            "cash_in_session_estimated": 31_000_000.0,
            "service": "uc",
        }

    def test_radius_cap_reason_is_exposed_in_meta_and_edge(self) -> None:
        cross_meta = {
            "systems_requested": 30,
            "systems_with_candidates": 0,
            "service": "uc",
            "radius_ly": 20_000.0,
            "origin_coords_used": True,
            "nearby_requested_radius_ly": 20_000.0,
            "nearby_effective_radius_ly": 100.0,
            "nearby_provider_response_count": 30,
            "nearby_reason": "provider_radius_cap",
        }
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=([], cross_meta),
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                return_value={},
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._payload(),
            )

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge_meta = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge_meta.get("reasons") or [])}

        self.assertIn("provider_radius_cap", reasons)
        self.assertEqual(float(station_meta.get("nearby_requested_radius_ly") or 0.0), 20_000.0)
        self.assertEqual(float(station_meta.get("nearby_effective_radius_ly") or 0.0), 100.0)
        self.assertEqual(int(station_meta.get("nearby_provider_response_count") or 0), 30)
        self.assertIn("EDSM limit 100 LY", str(edge_meta.get("ui_hint") or ""))

    def test_provider_empty_reason_is_exposed_when_effective_radius_has_zero_results(self) -> None:
        cross_meta = {
            "systems_requested": 0,
            "systems_with_candidates": 0,
            "service": "uc",
            "radius_ly": 20_000.0,
            "origin_coords_used": True,
            "nearby_requested_radius_ly": 20_000.0,
            "nearby_effective_radius_ly": 100.0,
            "nearby_provider_response_count": 0,
            "nearby_reason": "provider_empty",
        }
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=([], cross_meta),
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                return_value={},
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._payload(),
            )

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        edge_meta = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge_meta.get("reasons") or [])}

        self.assertIn("provider_empty", reasons)
        self.assertIn("provider_radius_cap", reasons)
        self.assertIn("effective=100", str(edge_meta.get("ui_hint") or ""))


if __name__ == "__main__":
    unittest.main()

