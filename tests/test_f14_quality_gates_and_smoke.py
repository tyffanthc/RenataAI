from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.cash_in_station_candidates import _reset_offline_index_cache_for_tests
from logic.events import cash_in_assistant


class F14QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._tmp = tempfile.TemporaryDirectory()

        app_state.current_system = "F14_QG_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["cash_in.cross_system_radius_ly"] = 120.0
        config.config._settings["cash_in.cross_system_max_systems"] = 8
        config.config._settings["cash_in.swr_cache_enabled"] = False
        config.config._settings["cash_in.local_known_fallback_enabled"] = False
        config.config._settings["cash_in.offline_index_fallback_enabled"] = True
        config.config._settings["cash_in.offline_index_non_carrier_only"] = True
        config.config._settings["cash_in.offline_index_confidence_med_age_days"] = 30
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.providers.system_lookup_online"] = True
        config.config._settings["features.trade.station_lookup_online"] = False

        _reset_offline_index_cache_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()
        self._playerdb_patch = patch(
            "logic.events.cash_in_assistant.station_candidates_from_playerdb",
            return_value=(
                [],
                {
                    "lookup_status": "disabled_for_f14_test",
                    "query_mode": "none",
                    "origin_coords_used": False,
                    "origin_coords_from_playerdb": False,
                    "coords_missing_count": 0,
                },
            ),
        )
        self._playerdb_patch.start()

    def tearDown(self) -> None:
        try:
            self._playerdb_patch.stop()
        except Exception:
            pass
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.current_star_pos = self._saved_star_pos
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        _reset_offline_index_cache_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()
        self._tmp.cleanup()

    def _write_index(self, payload: dict) -> str:
        path = f"{self._tmp.name}/f14_offline_index.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        return path

    @staticmethod
    def _payload() -> dict:
        return {
            "system": "F14_QG_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 8_000_000.0,
            "cash_in_session_estimated": 28_000_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_quality_gate_online_real_target_is_not_overridden_by_offline_index(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "OFFLINE_SHOULD_NOT_WIN",
                        "system_name": "F14_OFFLINE_ONLY",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "coords": [3.0, 0.0, 0.0],
                    }
                ],
            }
        )
        config.config._settings["cash_in.offline_index_path"] = index_path
        online_rows = [
            {
                "name": "ONLINE_REAL_TARGET",
                "system_name": "F14_ONLINE_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 18.0,
                "source": "EDSM",
            }
        ]

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=online_rows,
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=self._payload())

        self.assertTrue(ok)
        structured = dict((emit_mock.call_args.kwargs.get("context") or {}).get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertEqual(str(station_meta.get("source_status") or ""), "providers")
        self.assertFalse(bool(station_meta.get("offline_index_used")))
        self.assertEqual(str(station_meta.get("offline_index_lookup_status") or ""), "not_needed")
        self.assertNotIn("offline_index", reasons)
        self.assertNotIn("no_offline_index_hit", reasons)

    def test_quality_gate_online_nearby_without_stations_uses_offline_index(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "F14_OFFLINE_REAL_TARGET",
                        "system_name": "F14_OFFLINE_REAL_SYSTEM",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "coords": [11.0, 0.0, 0.0],
                    }
                ],
            }
        )
        config.config._settings["cash_in.offline_index_path"] = index_path
        config.config._settings["cash_in.cross_system_discovery_enabled"] = True
        config.config._settings["features.providers.system_lookup_online"] = True

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=(
                    [],
                    {
                        "systems_requested": 30,
                        "systems_with_candidates": 0,
                        "nearby_requested_radius_ly": 100.0,
                        "nearby_effective_radius_ly": 100.0,
                        "nearby_provider_response_count": 30,
                        "nearby_reason": "",
                    },
                ),
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=self._payload())

        self.assertTrue(ok)
        structured = dict((emit_mock.call_args.kwargs.get("context") or {}).get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]

        self.assertTrue(bool(station_meta.get("cross_system_lookup_attempted")))
        self.assertEqual(int(station_meta.get("cross_system_systems_requested") or 0), 30)
        self.assertEqual(str(station_meta.get("source_status") or ""), "offline_index")
        self.assertTrue(bool(station_meta.get("offline_index_used")))
        self.assertIn("offline_index", reasons)

        self.assertGreaterEqual(len(options), 1)
        handoff = cash_in_assistant.handoff_cash_in_to_route_intent(
            options[0],
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertTrue(bool(handoff.get("ok")))
        self.assertEqual(str(handoff.get("target_system") or ""), "F14_OFFLINE_REAL_SYSTEM")
        self.assertEqual(str(handoff.get("target_station") or ""), "F14_OFFLINE_REAL_TARGET")

    def test_quality_gate_offline_index_miss_keeps_orientational_fallback_and_reason(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "VISTA_ONLY_NO_UC",
                        "system_name": "F14_VISTA_SYSTEM",
                        "type": "station",
                        "services": {"has_uc": False, "has_vista": True},
                        "coords": [5.0, 0.0, 0.0],
                    }
                ],
            }
        )
        config.config._settings["cash_in.offline_index_path"] = index_path

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=self._payload())

        self.assertTrue(ok)
        structured = dict((emit_mock.call_args.kwargs.get("context") or {}).get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]

        self.assertEqual(str(station_meta.get("offline_index_lookup_status") or ""), "no_offline_index_hit")
        self.assertIn("no_offline_index_hit", reasons)
        self.assertIn("providers_empty", reasons)
        self.assertGreaterEqual(len(options), 1)

        blocked = cash_in_assistant.handoff_cash_in_to_route_intent(
            options[0],
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(blocked.get("ok")))
        self.assertEqual(str(blocked.get("reason") or ""), "target_missing_system")

    def test_smoke_runtime_offline_still_uses_offline_index_target(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "F14_OFFLINE_MODE_TARGET",
                        "system_name": "F14_OFFLINE_MODE_SYSTEM",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "coords": [14.0, 0.0, 0.0],
                    }
                ],
            }
        )
        config.config._settings["cash_in.offline_index_path"] = index_path
        payload = self._payload()
        payload["offline"] = True

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
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value=snapshot_503),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        structured = dict((emit_mock.call_args.kwargs.get("context") or {}).get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]

        self.assertEqual(str(station_meta.get("source_status") or ""), "offline_index")
        self.assertTrue(bool(station_meta.get("offline_index_used")))
        self.assertIn("offline", reasons)
        self.assertIn("offline_index", reasons)
        self.assertGreaterEqual(len(options), 1)
        handoff = cash_in_assistant.handoff_cash_in_to_route_intent(
            options[0],
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertTrue(bool(handoff.get("ok")))
        self.assertEqual(str(handoff.get("target_system") or ""), "F14_OFFLINE_MODE_SYSTEM")


if __name__ == "__main__":
    unittest.main()
