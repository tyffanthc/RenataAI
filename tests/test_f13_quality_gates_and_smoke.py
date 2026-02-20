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


class F13QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F13_QG_SYSTEM"
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.trade.station_lookup_online"] = False

        config.config._settings["providers.edsm.resilience.retry.max_attempts"] = 4
        config.config._settings["providers.edsm.resilience.retry.base_delay_sec"] = 0.1
        config.config._settings["providers.edsm.resilience.retry.max_delay_sec"] = 8.0
        config.config._settings["providers.edsm.resilience.retry.jitter_sec"] = 0.0
        config.config._settings["providers.edsm.resilience.circuit_breaker_ttl_sec"] = 60.0

        config.config._settings["cash_in.swr_cache_enabled"] = True
        config.config._settings["cash_in.swr_cache_fresh_ttl_sec"] = 0.01
        config.config._settings["cash_in.swr_cache_stale_ttl_sec"] = 3600.0
        config.config._settings["cash_in.swr_cache_max_items"] = 64
        config.config._settings["cash_in.local_known_fallback_enabled"] = True

        edsm_client._reset_provider_resilience_state_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

        edsm_client._reset_provider_resilience_state_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()

    @staticmethod
    def _payload(system: str = "F13_QG_SYSTEM") -> dict:
        return {
            "system": system,
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 7_000_000.0,
            "cash_in_session_estimated": 24_000_000.0,
            "service": "uc",
        }

    def test_quality_gate_circuit_breaker_ttl_open_and_close(self) -> None:
        config.config._settings["providers.edsm.resilience.retry.max_attempts"] = 1

        with (
            patch("logic.utils.edsm_client._throttle", return_value=None),
            patch("logic.utils.edsm_client.requests.get", return_value=_DummyResponse(503, [])),
        ):
            with self.assertRaises(edsm_client.Edsmunavailable):
                edsm_client.fetch_nearby_systems("F13_QG_SYSTEM", radius_ly=100.0, limit=8)

        snap_open = edsm_client.get_provider_resilience_snapshot()
        endpoint_open = dict((snap_open.get("endpoints") or {}).get("nearby_systems") or {})
        self.assertTrue(bool(endpoint_open.get("circuit_open")))
        self.assertGreater(float(endpoint_open.get("down_ttl_sec") or 0.0), 0.0)

        # Force-close TTL in runtime state and confirm snapshot goes back to closed.
        state = dict(edsm_client._PROVIDER_ENDPOINT_STATE.get("nearby_systems") or {})
        state["down_until_monotonic"] = time.monotonic() - 1.0
        edsm_client._PROVIDER_ENDPOINT_STATE["nearby_systems"] = state
        snap_closed = edsm_client.get_provider_resilience_snapshot()
        endpoint_closed = dict((snap_closed.get("endpoints") or {}).get("nearby_systems") or {})
        self.assertFalse(bool(endpoint_closed.get("circuit_open")))

    def test_quality_gate_backoff_profile_attempts_and_sleep_sequence(self) -> None:
        with (
            patch("logic.utils.edsm_client._throttle", return_value=None),
            patch("logic.utils.edsm_client.requests.get", return_value=_DummyResponse(503, [])) as get_mock,
            patch("logic.utils.edsm_client.random.uniform", return_value=0.0),
            patch("logic.utils.edsm_client.time.sleep", return_value=None) as sleep_mock,
        ):
            with self.assertRaises(edsm_client.Edsmunavailable):
                edsm_client.fetch_system_stations_details("F13_QG_SYSTEM")

        self.assertEqual(get_mock.call_count, 4)
        sleep_values = [float(call.args[0]) for call in sleep_mock.call_args_list]
        self.assertEqual(sleep_values, [0.1, 0.2, 0.4])

    def test_quality_gate_stale_fallback_marks_labels_and_confidence(self) -> None:
        payload = self._payload()
        provider_rows = [
            {
                "name": "F13_QG_UC_HUB",
                "system_name": "F13_QG_REMOTE",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 28.0,
                "source": "EDSM",
            }
        ]
        snapshot_503 = {
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
                side_effect=[provider_rows, []],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                side_effect=[{}, snapshot_503],
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            self.assertTrue(cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload))
            time.sleep(0.05)
            self.assertTrue(cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload))

        ctx = dict(emit_mock.call_args_list[1].kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge_meta = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge_meta.get("reasons") or [])}

        self.assertTrue(bool(station_meta.get("swr_cache_used")))
        self.assertEqual(str(station_meta.get("swr_freshness") or ""), "STALE")
        self.assertEqual(str(station_meta.get("provider_lookup_status") or ""), "provider_down_503")
        self.assertIn("stale_cache", reasons)
        self.assertIn("provider_down_503", reasons)
        self.assertEqual(str(edge_meta.get("confidence") or ""), "low")

    def test_quality_gate_provider_recovery_returns_to_providers_mode(self) -> None:
        payload = self._payload()
        seed_rows = [
            {
                "name": "F13_QG_SEED_HUB",
                "system_name": "F13_QG_REMOTE_A",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 30.0,
                "source": "EDSM",
            }
        ]
        recovered_rows = [
            {
                "name": "F13_QG_RECOVERY_HUB",
                "system_name": "F13_QG_REMOTE_B",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 18.0,
                "source": "EDSM",
            }
        ]
        snapshot_503 = {
            "provider": "EDSM",
            "endpoints": {
                "station_details": {
                    "circuit_open": False,
                    "last_error_code": 503,
                    "provider_down_503_count": 1,
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
                side_effect=[seed_rows, [], recovered_rows],
            ),
            patch(
                "logic.events.cash_in_assistant.edsm_provider_resilience_snapshot",
                side_effect=[{}, snapshot_503, {}],
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            self.assertTrue(cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload))
            time.sleep(0.05)
            self.assertTrue(cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload))
            self.assertTrue(cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload))

        third_ctx = dict(emit_mock.call_args_list[2].kwargs.get("context") or {})
        third_payload = dict(third_ctx.get("cash_in_payload") or {})
        third_meta = dict(third_payload.get("station_candidates_meta") or {})

        self.assertFalse(bool(third_meta.get("swr_cache_used")))
        self.assertEqual(str(third_meta.get("source_status") or ""), "providers")
        self.assertEqual(str(third_meta.get("provider_lookup_status") or ""), "providers")
        self.assertEqual(str(third_meta.get("confidence") or ""), "high")


if __name__ == "__main__":
    unittest.main()
