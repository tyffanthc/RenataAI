from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant
from logic.utils import edsm_client


class F11CashInEdgeCasesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_live = getattr(app_state, "has_live_system_event", None)
        self._saved_bootstrap = getattr(app_state, "bootstrap_replay", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F11_EDGE_CASE_SYSTEM"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.has_live_system_event = True
        app_state.bootstrap_replay = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["features.providers.system_lookup_online"] = False
        edsm_client._reset_provider_resilience_state_for_tests()

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.has_live_system_event = self._saved_live
        app_state.bootstrap_replay = self._saved_bootstrap
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        edsm_client._reset_provider_resilience_state_for_tests()

    @staticmethod
    def _base_payload() -> dict:
        return {
            "system": "F11_EDGE_CASE_SYSTEM",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 2_700_000.0,
            "cash_in_session_estimated": 11_900_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_providers_empty_and_no_station_data_are_reported_with_low_confidence(self) -> None:
        payload = self._base_payload()
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertEqual(str(station_meta.get("provider_lookup_status") or ""), "providers_empty")
        self.assertIn("providers_empty", reasons)
        self.assertIn("no_station_data", reasons)
        self.assertEqual(str(edge.get("confidence") or ""), "low")
        self.assertIn("brak pelnych danych stacyjnych", str(ctx.get("raw_text") or "").lower())
        self.assertIn("Brak pelnych danych stacyjnych", str(structured.get("note") or ""))

    def test_no_non_carrier_uc_adds_carrier_warning(self) -> None:
        payload = self._base_payload()
        payload["station_candidates"] = [
            {
                "name": "FC ONLY K7Q-AAA",
                "system_name": "F11_EDGE_CASE_SYSTEM",
                "type": "fleet_carrier",
                "services": ["Universal Cartographics"],
                "distance_ly": 4.0,
                "distance_ls": 900.0,
                "source": "SPANSH",
            }
        ]
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertIn("no_non_carrier", reasons)
        self.assertIn("tylko carriery", str(ctx.get("raw_text") or "").lower())
        self.assertIn("Brak non-carrier dla UC", str(structured.get("note") or ""))

    def test_offline_or_interrupted_logs_use_safe_wording(self) -> None:
        payload = self._base_payload()
        payload["journal_interrupted"] = True
        payload["station_candidates"] = [
            {
                "name": "Safe Station",
                "system_name": "F11_EDGE_CASE_SYSTEM",
                "type": "station",
                "services": ["Universal Cartographics"],
                "distance_ly": 8.0,
                "distance_ls": 1_500.0,
                "source": "EDSM",
            }
        ]
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertIn("offline", reasons)
        self.assertIn("offline", str(ctx.get("raw_text") or "").lower())
        self.assertIn("offline", str(structured.get("note") or "").lower())

    def test_strict_combo_no_non_carrier_and_providers_empty_message(self) -> None:
        payload = self._base_payload()
        station_candidates = [
            {
                "name": "FC ONLY K7Q-CCC",
                "system_name": "F11_EDGE_CASE_SYSTEM",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 3.0,
                "distance_ls": 800.0,
                "source": "SPANSH",
            }
        ]
        station_meta = {
            "source_status": "local_fallback",
            "provider_lookup_attempted": True,
            "provider_lookup_status": "providers_empty",
            "count": 1,
            "uc_count": 1,
            "vista_count": 0,
            "confidence": "low",
        }
        with (
            patch(
                "logic.events.cash_in_assistant._build_station_candidates_runtime",
                return_value=(station_candidates, station_meta),
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertIn("providers_empty", reasons)
        self.assertIn("no_non_carrier", reasons)
        self.assertIn(
            "dane stacyjne ograniczone i dla uc widze tylko carriery",
            str(ctx.get("raw_text") or "").lower(),
        )


if __name__ == "__main__":
    unittest.main()
