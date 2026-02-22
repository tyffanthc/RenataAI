from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic import player_local_db
from logic import cash_in_station_candidates
from logic.event_handler import EventHandler
from logic.events import cash_in_assistant


class F16QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "db", "player_local.db")
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._saved_bootstrap = getattr(app_state, "bootstrap_replay", None)
        self._saved_live = getattr(app_state, "has_live_system_event", None)

        app_state.current_system = "F16_QG_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        app_state.bootstrap_replay = False
        app_state.has_live_system_event = True

        config.config._settings["cash_in_assistant_enabled"] = True
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.swr_cache_enabled"] = False
        config.config._settings["cash_in.local_known_fallback_enabled"] = False
        config.config._settings["cash_in.offline_index_fallback_enabled"] = True
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False

        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()

        self._default_path_patch = patch("logic.player_local_db.default_playerdb_path", return_value=self._db_path)
        self._default_path_patch.start()

    def tearDown(self) -> None:
        self._default_path_patch.stop()
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.current_star_pos = self._saved_star_pos
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        app_state.bootstrap_replay = self._saved_bootstrap
        app_state.has_live_system_event = self._saved_live
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()
        self._tmp.cleanup()

    @staticmethod
    def _cashin_payload(system: str = "F16_QG_ORIGIN") -> dict:
        return {
            "system": system,
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 12_000_000.0,
            "cash_in_session_estimated": 120_000_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_quality_gate_f16_eventhandler_replay_populates_playerdb_and_cashin_uses_playerdb(self) -> None:
        router = EventHandler()

        # Origin with coords
        router.handle_event(
            json.dumps(
                {
                    "event": "Location",
                    "timestamp": "2026-02-22T23:30:00Z",
                    "StarSystem": "F16_QG_ORIGIN",
                    "SystemAddress": 5001,
                    "StarPos": [0.0, 0.0, 0.0],
                }
            )
        )
        # Nearby target system + docked station with UC/Vista
        router.handle_event(
            json.dumps(
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-22T23:31:00Z",
                    "StarSystem": "F16_QG_TARGET",
                    "SystemAddress": 5002,
                    "StarPos": [18.0, 0.0, 0.0],
                }
            )
        )
        router.handle_event(
            json.dumps(
                {
                    "event": "Docked",
                    "timestamp": "2026-02-22T23:32:00Z",
                    "StarSystem": "F16_QG_TARGET",
                    "SystemAddress": 5002,
                    "StationName": "F16 QG Station",
                    "StationType": "Orbis Starport",
                    "MarketID": 88001,
                    "DistFromStarLS": 512,
                    "StationServices": ["Universal Cartographics", "Vista Genomics", "Commodities"],
                }
            )
        )
        # Market snapshot + cash-in history
        router.on_market_update(
            {
                "StationName": "F16 QG Station",
                "StarSystem": "F16_QG_TARGET",
                "MarketID": 88001,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000, "Stock": 100},
                    {"Name_Localised": "Silver", "BuyPrice": 4000, "SellPrice": 7000, "Stock": 200},
                ],
            }
        )
        router.handle_event(
            json.dumps(
                {
                    "event": "SellExplorationData",
                    "timestamp": "2026-02-22T23:33:00Z",
                    "StarSystem": "F16_QG_TARGET",
                    "StationName": "F16 QG Station",
                    "TotalEarnings": 1200000,
                }
            )
        )
        router.handle_event(
            json.dumps(
                {
                    "event": "SellOrganicData",
                    "timestamp": "2026-02-22T23:34:00Z",
                    "StarSystem": "F16_QG_TARGET",
                    "StationName": "F16 QG Station",
                    "TotalEarnings": 3300000,
                }
            )
        )

        # Set current context back to origin to force nearest query toward target.
        app_state.current_system = "F16_QG_ORIGIN"
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._cashin_payload("F16_QG_ORIGIN"),
            )

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        options = [dict(x) for x in (structured.get("options") or []) if isinstance(x, dict)]

        self.assertEqual(str(station_meta.get("source_status") or ""), "playerdb")
        self.assertTrue(bool(station_meta.get("playerdb_used")))
        self.assertEqual(str(station_meta.get("playerdb_query_mode") or ""), "nearest")
        self.assertTrue(bool(station_meta.get("playerdb_origin_coords_used")))
        self.assertFalse(bool(station_meta.get("offline_index_used")))

        self.assertGreaterEqual(len(options), 1)
        handoff = cash_in_assistant.handoff_cash_in_to_route_intent(
            options[0],
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertTrue(bool(handoff.get("ok")))
        self.assertEqual(str(handoff.get("target_system") or ""), "F16_QG_TARGET")
        self.assertEqual(str(handoff.get("target_station") or ""), "F16 QG Station")

        history = player_local_db.query_cashin_history(path=self._db_path, limit=10)
        services = [str(row.get("service") or "") for row in history]
        self.assertIn("UC", services)
        self.assertIn("VISTA", services)

    def test_quality_gate_f16_playerdb_provider_last_seen_fallback_when_origin_coords_missing(self) -> None:
        # Build data with station but query from unknown origin without coords.
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T23:40:00Z",
                "StarSystem": "F16_LASTSEEN_TARGET",
                "SystemAddress": 6002,
                "StarPos": [25.0, 0.0, 0.0],
            },
            path=self._db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": "2026-02-22T23:41:00Z",
                "StarSystem": "F16_LASTSEEN_TARGET",
                "SystemAddress": 6002,
                "StationName": "F16 LastSeen Station",
                "MarketID": 66002,
                "StationServices": ["Universal Cartographics"],
            },
            path=self._db_path,
        )

        rows, meta = cash_in_station_candidates.station_candidates_from_playerdb(
            "F16_UNKNOWN_ORIGIN",
            service="uc",
            limit=10,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(meta.get("lookup_status") or ""), "playerdb")
        self.assertEqual(str(meta.get("query_mode") or ""), "last_seen")
        self.assertFalse(bool(meta.get("origin_coords_used")))

    def test_smoke_f16_market_snapshot_dedupe_through_eventhandler_market_update(self) -> None:
        router = EventHandler()
        router.handle_event(
            json.dumps(
                {
                    "event": "Docked",
                    "timestamp": "2026-02-22T23:50:00Z",
                    "StarSystem": "F16_DEDUPE_SYS",
                    "SystemAddress": 7001,
                    "StationName": "F16 Dedupe Station",
                    "MarketID": 77001,
                    "StationServices": ["Commodities"],
                }
            )
        )
        payload = {
            "StationName": "F16 Dedupe Station",
            "StarSystem": "F16_DEDUPE_SYS",
            "MarketID": 77001,
            "Items": [{"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000, "Stock": 10}],
        }
        router.on_market_update(dict(payload))
        router.on_market_update(dict(payload))

        with player_local_db.playerdb_connection(path=self._db_path) as conn:
            snap_count = int(conn.execute("SELECT COUNT(*) FROM market_snapshots;").fetchone()[0])
            item_count = int(conn.execute("SELECT COUNT(*) FROM market_snapshot_items;").fetchone()[0])
        self.assertEqual(snap_count, 1)
        self.assertEqual(item_count, 1)


if __name__ == "__main__":
    unittest.main()

