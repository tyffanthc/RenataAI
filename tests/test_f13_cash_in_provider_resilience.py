from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant
from logic.utils import edsm_client


class _DummyResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class F13CashInProviderResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F13_TEST_SYSTEM"
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["providers.edsm.resilience.retry.max_attempts"] = 3
        config.config._settings["providers.edsm.resilience.retry.base_delay_sec"] = 0.01
        config.config._settings["providers.edsm.resilience.retry.max_delay_sec"] = 0.02
        config.config._settings["providers.edsm.resilience.retry.jitter_sec"] = 0.0
        config.config._settings["providers.edsm.resilience.circuit_breaker_ttl_sec"] = 60.0

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.trade.station_lookup_online"] = False
        config.config._settings["cash_in.swr_cache_enabled"] = True
        config.config._settings["cash_in.swr_cache_fresh_ttl_sec"] = 900.0
        config.config._settings["cash_in.swr_cache_stale_ttl_sec"] = 21600.0
        config.config._settings["cash_in.swr_cache_max_items"] = 64

        edsm_client._reset_provider_resilience_state_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        edsm_client._reset_provider_resilience_state_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()

    def test_edsm_nearby_503_opens_circuit_and_counts_metric(self) -> None:
        with (
            patch("logic.utils.edsm_client.time.sleep", return_value=None),
            patch(
                "logic.utils.edsm_client.requests.get",
                return_value=_DummyResponse(503, []),
            ) as get_mock,
        ):
            with self.assertRaises(edsm_client.Edsmunavailable):
                edsm_client.fetch_nearby_systems("F13_TEST_SYSTEM", radius_ly=80.0, limit=8)

        snap = edsm_client.get_provider_resilience_snapshot()
        endpoint = dict((snap.get("endpoints") or {}).get("nearby_systems") or {})
        self.assertTrue(bool(endpoint.get("circuit_open")))
        self.assertGreaterEqual(int(endpoint.get("provider_down_503_count") or 0), 1)
        self.assertEqual(get_mock.call_count, 3)

    def test_edsm_nearby_circuit_open_short_circuits_next_call(self) -> None:
        with (
            patch("logic.utils.edsm_client.time.sleep", return_value=None),
            patch(
                "logic.utils.edsm_client.requests.get",
                return_value=_DummyResponse(503, []),
            ),
        ):
            with self.assertRaises(edsm_client.Edsmunavailable):
                edsm_client.fetch_nearby_systems("F13_TEST_SYSTEM", radius_ly=80.0, limit=8)

        with patch("logic.utils.edsm_client.requests.get") as get_mock:
            with self.assertRaises(edsm_client.Edsmcircuitopen):
                edsm_client.fetch_nearby_systems("F13_TEST_SYSTEM", radius_ly=80.0, limit=8)
        self.assertFalse(get_mock.called)

    def test_cash_in_meta_marks_provider_down_503_when_provider_snapshot_reports_503(self) -> None:
        payload = {
            "system": "F13_TEST_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 8_000_000.0,
            "cash_in_session_estimated": 25_000_000.0,
        }
        snapshot = {
            "provider": "EDSM",
            "endpoints": {
                "station_details": {
                    "circuit_open": False,
                    "last_error_code": 503,
                    "provider_down_503_count": 2,
                },
                "nearby_systems": {
                    "circuit_open": False,
                    "last_error_code": 0,
                    "provider_down_503_count": 0,
                },
            },
        }
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                return_value=snapshot,
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = [str(item).strip().lower() for item in (edge.get("reasons") or [])]

        self.assertEqual(str(meta.get("provider_lookup_status") or ""), "provider_down_503")
        self.assertEqual(int(meta.get("provider_down_503_count") or 0), 2)
        self.assertIn("provider_down_503", reasons)

    def test_cash_in_meta_marks_provider_circuit_open_when_provider_snapshot_reports_open(self) -> None:
        payload = {
            "system": "F13_TEST_SYSTEM",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 2_000_000.0,
            "cash_in_session_estimated": 7_000_000.0,
        }
        snapshot = {
            "provider": "EDSM",
            "endpoints": {
                "station_details": {
                    "circuit_open": True,
                    "last_error_code": 503,
                    "provider_down_503_count": 5,
                },
                "nearby_systems": {
                    "circuit_open": False,
                    "last_error_code": 0,
                    "provider_down_503_count": 0,
                },
            },
        }
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                return_value=snapshot,
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = [str(item).strip().lower() for item in (edge.get("reasons") or [])]

        self.assertEqual(str(meta.get("provider_lookup_status") or ""), "provider_circuit_open")
        self.assertEqual(int(meta.get("provider_down_503_count") or 0), 5)
        self.assertIn("provider_circuit_open", reasons)

    def test_swr_stale_cache_fallback_marks_stale_and_lowers_confidence(self) -> None:
        config.config._settings["cash_in.swr_cache_fresh_ttl_sec"] = 0.01
        config.config._settings["cash_in.swr_cache_stale_ttl_sec"] = 3600.0
        payload = {
            "system": "F13_TEST_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 8_000_000.0,
            "cash_in_session_estimated": 25_000_000.0,
            "service": "uc",
        }
        provider_rows = [
            {
                "name": "Cached UC Hub",
                "system_name": "F13_TEST_SYSTEM_B",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 22.0,
                "source": "EDSM",
            }
        ]
        snapshot_503 = {
            "provider": "EDSM",
            "endpoints": {
                "station_details": {
                    "circuit_open": False,
                    "last_error_code": 503,
                    "provider_down_503_count": 3,
                },
                "nearby_systems": {
                    "circuit_open": False,
                    "last_error_code": 0,
                    "provider_down_503_count": 0,
                },
            },
        }
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                side_effect=[provider_rows, []],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                side_effect=[{}, snapshot_503],
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            first_ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
            time.sleep(0.05)
            second_ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(first_ok)
        self.assertTrue(second_ok)
        self.assertEqual(emit_mock.call_count, 2)
        ctx = dict(emit_mock.call_args_list[1].kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertTrue(bool(meta.get("swr_cache_used")))
        self.assertEqual(str(meta.get("swr_freshness") or ""), "STALE")
        self.assertEqual(str(meta.get("source_status") or ""), "providers_cache_stale")
        self.assertEqual(str(meta.get("provider_lookup_status") or ""), "provider_down_503")
        self.assertIn("stale_cache", reasons)
        self.assertEqual(str(edge.get("confidence") or ""), "low")

    def test_swr_expired_snapshot_is_not_used(self) -> None:
        config.config._settings["cash_in.swr_cache_fresh_ttl_sec"] = 0.0
        config.config._settings["cash_in.swr_cache_stale_ttl_sec"] = 0.01
        payload = {
            "system": "F13_TEST_SYSTEM",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 2_000_000.0,
            "cash_in_session_estimated": 8_000_000.0,
            "service": "uc",
        }
        provider_rows = [
            {
                "name": "Expired Cache Seed",
                "system_name": "F13_TEST_SYSTEM_B",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 18.0,
                "source": "EDSM",
            }
        ]
        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                side_effect=[provider_rows, []],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock2,
        ):
            first_ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
            self.assertTrue(first_ok)
            time.sleep(0.05)
            second_ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(second_ok)
        self.assertEqual(emit_mock2.call_count, 2)
        ctx = dict(emit_mock2.call_args_list[1].kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        meta = dict(structured.get("station_candidates_meta") or {})
        self.assertFalse(bool(meta.get("swr_cache_used")))
        self.assertEqual(str(meta.get("swr_freshness") or ""), "EXPIRED")


if __name__ == "__main__":
    unittest.main()
