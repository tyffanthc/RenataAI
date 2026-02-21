from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.cash_in_station_candidates import (
    _reset_offline_index_cache_for_tests,
    station_candidates_from_offline_index,
)
from logic.events import cash_in_assistant


class F14CashInOfflineIndexFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._tmp = tempfile.TemporaryDirectory()

        app_state.current_system = "F14_OFFLINE_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.providers.system_lookup_online"] = True
        config.config._settings["features.trade.station_lookup_online"] = False
        config.config._settings["cash_in.offline_index_fallback_enabled"] = True
        config.config._settings["cash_in.offline_index_non_carrier_only"] = True
        config.config._settings["cash_in.offline_index_confidence_med_age_days"] = 30
        config.config._settings["cash_in.offline_index_path"] = ""

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

    def _write_index(self, payload: dict) -> str:
        path = f"{self._tmp.name}/offline_index.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        return path

    @staticmethod
    def _base_payload() -> dict:
        return {
            "system": "F14_OFFLINE_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 7_200_000.0,
            "cash_in_session_estimated": 23_500_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_offline_index_provider_filters_non_carrier_and_service(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "Carrier Should Skip",
                        "system_name": "F14_A",
                        "type": "fleet_carrier",
                        "services": {"has_uc": True},
                        "coords": [2.0, 0.0, 0.0],
                    },
                    {
                        "name": "UC Hub",
                        "system_name": "F14_B",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "coords": [9.0, 0.0, 0.0],
                    },
                    {
                        "name": "No Service",
                        "system_name": "F14_C",
                        "type": "station",
                        "services": {"has_uc": False, "has_vista": False},
                        "coords": [1.0, 0.0, 0.0],
                    },
                ]
            }
        )
        candidates, meta = station_candidates_from_offline_index(
            "F14_OFFLINE_ORIGIN",
            service="uc",
            origin_coords=[0.0, 0.0, 0.0],
            index_path=index_path,
            limit=16,
            non_carrier_only=True,
        )

        self.assertEqual(len(candidates), 1)
        row = dict(candidates[0])
        self.assertEqual(str(row.get("name") or ""), "UC Hub")
        self.assertEqual(str(row.get("source") or ""), "OFFLINE_INDEX")
        self.assertAlmostEqual(float(row.get("distance_ly") or 0.0), 9.0, places=3)
        self.assertEqual(str(meta.get("lookup_status") or ""), "offline_index")
        self.assertEqual(int(meta.get("ignored_carriers") or 0), 1)
        self.assertEqual(int(meta.get("rows_service_match") or 0), 1)
        self.assertEqual(int(meta.get("rows_coords_match") or 0), 1)

    def test_runtime_uses_offline_index_for_real_route_target(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "Real UC Target",
                        "system_name": "F14_REAL_TARGET",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "coords": [12.0, 0.0, 0.0],
                    }
                ],
            }
        )
        config.config._settings["cash_in.offline_index_path"] = index_path
        payload = self._base_payload()

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]

        self.assertEqual(str(station_meta.get("source_status") or ""), "offline_index")
        self.assertTrue(bool(station_meta.get("offline_index_used")))
        self.assertEqual(str(station_meta.get("offline_index_lookup_status") or ""), "offline_index")
        self.assertIn("offline_index", reasons)
        self.assertEqual(str(edge.get("confidence") or ""), "mid")
        self.assertGreaterEqual(len(options), 1)
        selected = dict(options[0])
        target = dict(selected.get("target") or {})
        self.assertEqual(str(target.get("system_name") or ""), "F14_REAL_TARGET")
        self.assertEqual(str(target.get("name") or ""), "Real UC Target")
        self.assertFalse(bool(selected.get("fallback_target_attached")))

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            selected,
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(str(out.get("reason") or ""), "intent_set")
        self.assertEqual(str(out.get("target_system") or ""), "F14_REAL_TARGET")
        self.assertEqual(str(out.get("target_station") or ""), "Real UC Target")

    def test_runtime_marks_no_offline_index_hit_when_index_has_no_service_match(self) -> None:
        index_path = self._write_index(
            {
                "meta": {"index_date": "2026-02-20"},
                "stations": [
                    {
                        "name": "Vista Only",
                        "system_name": "F14_VISTA_ONLY",
                        "type": "station",
                        "services": {"has_uc": False, "has_vista": True},
                        "coords": [18.0, 0.0, 0.0],
                    }
                ],
            }
        )
        config.config._settings["cash_in.offline_index_path"] = index_path
        payload = self._base_payload()

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge.get("reasons") or [])}

        self.assertEqual(str(station_meta.get("offline_index_lookup_status") or ""), "no_offline_index_hit")
        self.assertIn("no_offline_index_hit", reasons)


if __name__ == "__main__":
    unittest.main()
