from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic import player_local_db
from logic import cash_in_station_candidates
from logic.events import cash_in_assistant


class F16PlayerDbProviderForCashInAndMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        app_state.current_system = "F16_PROVIDER_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in_assistant_enabled"] = True
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.offline_index_fallback_enabled"] = True
        config.config._settings["cash_in.local_known_fallback_enabled"] = True
        config.config._settings["cash_in.swr_cache_enabled"] = False
        config.config._settings["cash_in.station_candidates_limit"] = 24

        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.current_star_pos = self._saved_star_pos
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()

    @staticmethod
    def _payload() -> dict:
        return {
            "system": "F16_PROVIDER_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 15_000_000.0,
            "cash_in_session_estimated": 45_000_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_station_candidates_from_playerdb_wrapper_returns_shared_provider_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            player_local_db.ingest_journal_event(
                {
                    "event": "Location",
                    "timestamp": "2026-02-22T23:00:00Z",
                    "StarSystem": "Origin",
                    "SystemAddress": 1001,
                    "StarPos": [0.0, 0.0, 0.0],
                },
                path=db_path,
            )
            player_local_db.ingest_journal_event(
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-22T23:01:00Z",
                    "StarSystem": "Target",
                    "SystemAddress": 1002,
                    "StarPos": [12.0, 0.0, 0.0],
                },
                path=db_path,
            )
            player_local_db.ingest_journal_event(
                {
                    "event": "Docked",
                    "timestamp": "2026-02-22T23:02:00Z",
                    "StarSystem": "Target",
                    "SystemAddress": 1002,
                    "StationName": "Target Hub",
                    "MarketID": 9001,
                    "StationServices": ["Universal Cartographics", "Commodities"],
                },
                path=db_path,
            )

            rows, meta = cash_in_station_candidates.station_candidates_from_playerdb(
                "Origin",
                service="uc",
                limit=10,
                db_path=db_path,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "Target Hub")
            self.assertEqual(rows[0]["source"], "PLAYERDB")
            self.assertAlmostEqual(float(rows[0]["distance_ly"]), 12.0)
            self.assertEqual(str(meta.get("lookup_status")), "playerdb")
            self.assertEqual(str(meta.get("query_mode")), "nearest")
            self.assertTrue(bool(meta.get("origin_coords_used")))

    def test_cash_in_prefers_playerdb_provider_before_bridge_and_offline_index(self) -> None:
        playerdb_rows = [
            {
                "name": "F16 PlayerDB UC",
                "system_name": "F16_DB_TARGET",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 22.0,
                "distance_ls": 350.0,
                "source": "PLAYERDB",
                "freshness_ts": "2026-02-22T23:15:00Z",
                "confidence": "high",
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

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_from_playerdb",
                return_value=(playerdb_rows, playerdb_meta),
            ) as playerdb_mock,
            patch(
                "logic.events.cash_in_assistant._load_local_known_candidates",
                return_value={"used": False, "age_sec": 0.0, "count": 0, "candidates": []},
            ) as local_known_mock,
            patch(
                "logic.events.cash_in_assistant.station_candidates_from_offline_index",
                return_value=([], {"lookup_status": "not_needed"}),
            ) as offline_mock,
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._payload(),
            )

        self.assertTrue(ok)
        self.assertTrue(playerdb_mock.called)
        self.assertFalse(local_known_mock.called, "bridge cache should not run before playerdb")
        self.assertFalse(offline_mock.called, "offline_index should not run before playerdb")
        self.assertEqual(emit_mock.call_count, 1)

        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        order_contract = [str(x) for x in (station_meta.get("source_order_contract") or [])]
        self.assertEqual(str(station_meta.get("source_status") or ""), "playerdb")
        self.assertTrue(bool(station_meta.get("playerdb_lookup_attempted")))
        self.assertTrue(bool(station_meta.get("playerdb_used")))
        self.assertEqual(str(station_meta.get("playerdb_lookup_status") or ""), "playerdb")
        self.assertEqual(str(station_meta.get("playerdb_query_mode") or ""), "nearest")
        self.assertTrue(bool(station_meta.get("playerdb_origin_coords_used")))
        self.assertIn("playerdb", order_contract)
        self.assertIn("playerdb_bridge", order_contract)
        self.assertIn("offline_index", order_contract)
        self.assertLess(order_contract.index("playerdb"), order_contract.index("offline_index"))


if __name__ == "__main__":
    unittest.main()

