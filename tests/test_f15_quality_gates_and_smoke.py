from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.cash_in_station_candidates import _reset_offline_index_cache_for_tests
from logic.cash_in_offline_index_builder import build_offline_index_from_spansh_dump
from logic.events import cash_in_assistant


class F15QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F15_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["cash_in.cross_system_radius_ly"] = 100.0
        config.config._settings["cash_in.cross_system_max_systems"] = 12
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

    def tearDown(self) -> None:
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

    def _write_dump(self, systems_payload: list[dict], filename: str = "galaxy_stations.json.gz") -> str:
        dump_path = os.path.join(self._tmp.name, filename)
        with gzip.open(dump_path, "wt", encoding="utf-8") as handle:
            json.dump(systems_payload, handle, ensure_ascii=False)
        return dump_path

    @staticmethod
    def _payload() -> dict:
        return {
            "system": "F15_ORIGIN",
            "service": "uc",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 10_000_000.0,
            "cash_in_session_estimated": 100_000_000.0,
            "confidence": "high",
        }

    def test_quality_gate_download_convert_then_runtime_uses_real_target(self) -> None:
        dump_path = self._write_dump(
            [
                {
                    "name": "F15_ORIGIN",
                    "coords": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "date": "2026-02-20 10:00:00+00",
                    "stations": [],
                },
                {
                    "name": "F15_TARGET_SYS",
                    "coords": {"x": 12.0, "y": 0.0, "z": 0.0},
                    "date": "2026-02-21 10:00:00+00",
                    "stations": [
                        {
                            "name": "F15_TARGET_STATION",
                            "type": "Orbis Starport",
                            "services": ["Dock", "Universal Cartographics"],
                            "distanceToArrival": 420,
                            "updateTime": "2026-02-21 09:55:00+00",
                        }
                    ],
                },
            ]
        )
        index_path = os.path.join(self._tmp.name, "offline_station_index.json")
        result = build_offline_index_from_spansh_dump(dump_path, index_path)
        self.assertEqual(int(result.get("stations_written") or 0), 1)
        self.assertTrue(os.path.isfile(index_path))
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
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

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
        self.assertEqual(str(handoff.get("target_system") or ""), "F15_TARGET_SYS")
        self.assertEqual(str(handoff.get("target_station") or ""), "F15_TARGET_STATION")

    def test_quality_gate_old_index_date_downgrades_confidence_to_low(self) -> None:
        dump_path = self._write_dump(
            [
                {
                    "name": "F15_ORIGIN",
                    "coords": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "date": "2020-01-01 10:00:00+00",
                    "stations": [],
                },
                {
                    "name": "F15_OLD_SYS",
                    "coords": {"x": 25.0, "y": 0.0, "z": 0.0},
                    "date": "2020-01-01 10:00:00+00",
                    "stations": [
                        {
                            "name": "F15_OLD_TARGET",
                            "type": "Outpost",
                            "services": ["Universal Cartographics"],
                            "distanceToArrival": 1000,
                        }
                    ],
                },
            ],
            filename="galaxy_stations_old.json.gz",
        )
        index_path = os.path.join(self._tmp.name, "offline_station_index_old.json")
        build_offline_index_from_spansh_dump(dump_path, index_path)
        config.config._settings["cash_in.offline_index_path"] = index_path
        config.config._settings["cash_in.offline_index_confidence_med_age_days"] = 7

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
        edge = dict(structured.get("edge_case_meta") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        self.assertEqual(str(station_meta.get("source_status") or ""), "offline_index")
        self.assertEqual(str(edge.get("confidence") or "").lower(), "low")


if __name__ == "__main__":
    unittest.main()
