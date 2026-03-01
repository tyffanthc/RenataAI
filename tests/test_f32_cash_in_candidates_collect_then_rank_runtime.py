from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F32CashInCandidatesCollectThenRankRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F32_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in_assistant_enabled"] = True
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["cash_in.swr_cache_enabled"] = False
        config.config._settings["cash_in.local_known_fallback_enabled"] = False
        config.config._settings["cash_in.offline_index_fallback_enabled"] = True
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.trade.station_lookup_online"] = False

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
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()

    @staticmethod
    def _payload() -> dict:
        return {
            "system": "F32_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 8_000_000.0,
            "cash_in_session_estimated": 28_000_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_runtime_provider_empty_collects_playerdb_and_offline_then_ranks(self) -> None:
        playerdb_rows = [
            {
                "name": "F32 PlayerDB Hub",
                "system_name": "F32_PLAYERDB_SYS",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 24.0,
                "distance_ls": 1400.0,
                "source": "PLAYERDB",
                "freshness_ts": "2026-03-01T10:00:00Z",
            }
        ]
        playerdb_meta = {
            "lookup_status": "playerdb",
            "query_mode": "nearest",
            "origin_coords_used": True,
            "origin_coords_from_playerdb": False,
            "coords_missing_count": 0,
            "count": 1,
        }
        offline_rows = [
            {
                "name": "F32 Offline Near Port",
                "system_name": "F32_OFFLINE_SYS",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 9.0,
                "distance_ls": 900.0,
                "source": "OFFLINE_INDEX",
                "freshness_ts": "2026-02-25T00:00:00Z",
            }
        ]
        offline_meta = {
            "lookup_status": "offline_index",
            "index_date": "2026-02-25",
            "index_age_days": 5,
            "rows_total": 1,
            "rows_service_match": 1,
            "rows_coords_match": 1,
            "ignored_carriers": 0,
        }

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch(
                "logic.events.cash_in_assistant.station_candidates_from_playerdb",
                return_value=(playerdb_rows, playerdb_meta),
            ) as playerdb_mock,
            patch(
                "logic.events.cash_in_assistant.station_candidates_from_offline_index",
                return_value=(offline_rows, offline_meta),
            ) as offline_mock,
            patch(
                "logic.events.cash_in_assistant._load_local_known_candidates",
                return_value={"used": False, "age_sec": 0.0, "count": 0, "candidates": []},
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._payload(),
            )

        self.assertTrue(ok)
        self.assertTrue(playerdb_mock.called)
        self.assertTrue(offline_mock.called)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        candidates = [dict(item) for item in (structured.get("station_candidates") or []) if isinstance(item, dict)]

        self.assertTrue(bool(station_meta.get("playerdb_lookup_attempted")))
        self.assertTrue(bool(station_meta.get("offline_index_lookup_attempted")))
        self.assertEqual(str(station_meta.get("source_status") or ""), "offline_index")
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(str(candidates[0].get("system_name") or ""), "F32_OFFLINE_SYS")


if __name__ == "__main__":
    unittest.main()
