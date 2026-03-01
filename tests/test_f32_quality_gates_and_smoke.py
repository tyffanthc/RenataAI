from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.cash_in_station_candidates import collect_then_rank_station_candidates
from logic.events import cash_in_assistant


class F32QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_star_pos = getattr(app_state, "current_star_pos", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F32_QG_ORIGIN"
        app_state.current_station = ""
        app_state.current_star_pos = [0.0, 0.0, 0.0]
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in_assistant_enabled"] = True
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["cash_in.swr_cache_enabled"] = True
        config.config._settings["cash_in.offline_index_fallback_enabled"] = True
        config.config._settings["cash_in.local_known_fallback_enabled"] = False
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
            "system": "F32_QG_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 7_500_000.0,
            "cash_in_session_estimated": 22_500_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_quality_gate_collect_then_rank_mixed_sources_conflict_and_sort(self) -> None:
        out = collect_then_rank_station_candidates(
            source_rows={
                "OFFLINE_INDEX": [
                    {
                        "market_id": "900001",
                        "name": "Offline Tie",
                        "system_name": "F32_DUP_A",
                        "services": {"has_uc": True},
                        "distance_ly": 11.0,
                        "distance_ls": 1400.0,
                        "freshness_ts": "2026-03-01T12:00:00Z",
                        "source": "OFFLINE_INDEX",
                    },
                    {
                        "market_id": "900002",
                        "name": "Offline Older",
                        "system_name": "F32_DUP_B",
                        "services": {"has_uc": True},
                        "distance_ly": 7.0,
                        "distance_ls": 900.0,
                        "freshness_ts": "2026-02-20T12:00:00Z",
                        "source": "OFFLINE_INDEX",
                    },
                ],
                "EDSM": [
                    {
                        "market_id": "900001",
                        "name": "EDSM Tie Winner",
                        "system_name": "F32_DUP_A",
                        "services": {"has_uc": True},
                        "distance_ly": 12.0,
                        "distance_ls": 1800.0,
                        "freshness_ts": "2026-03-01T12:00:00Z",
                        "source": "EDSM",
                    }
                ],
                "PLAYERDB": [
                    {
                        "market_id": "900002",
                        "name": "PlayerDB Fresh Winner",
                        "system_name": "F32_DUP_B",
                        "services": {"has_uc": True},
                        "distance_ly": 8.0,
                        "distance_ls": 500.0,
                        "freshness_ts": "2026-03-02T12:00:00Z",
                        "source": "PLAYERDB",
                    },
                    {
                        "market_id": "900003",
                        "name": "PlayerDB Sort Second",
                        "system_name": "F32_SORT_B",
                        "services": {"has_uc": True},
                        "distance_ly": 6.0,
                        "distance_ls": 900.0,
                        "freshness_ts": "2026-03-02T12:00:00Z",
                        "source": "PLAYERDB",
                    },
                ],
                "SPANSH": [
                    {
                        "market_id": "900004",
                        "name": "Spansh Sort First",
                        "system_name": "F32_SORT_A",
                        "services": {"has_uc": True},
                        "distance_ly": 6.0,
                        "distance_ls": 400.0,
                        "freshness_ts": "2026-03-02T12:00:00Z",
                        "source": "SPANSH",
                    }
                ],
            },
            default_system="F32_QG_ORIGIN",
            limit=10,
        )

        self.assertGreaterEqual(len(out), 4)
        by_market = {
            str((row or {}).get("market_id") or ""): dict(row)
            for row in out
            if isinstance(row, dict)
        }

        tie_row = by_market.get("900001") or {}
        self.assertEqual(str(tie_row.get("name") or ""), "EDSM Tie Winner")
        self.assertIn("EDSM", str(tie_row.get("source") or ""))
        self.assertIn("OFFLINE_INDEX", str(tie_row.get("source") or ""))

        freshness_row = by_market.get("900002") or {}
        self.assertEqual(str(freshness_row.get("name") or ""), "PlayerDB Fresh Winner")
        self.assertEqual(str(freshness_row.get("freshness_ts") or ""), "2026-03-02T12:00:00Z")
        self.assertIn("PLAYERDB", str(freshness_row.get("source") or ""))
        self.assertIn("OFFLINE_INDEX", str(freshness_row.get("source") or ""))

        names = [str((row or {}).get("name") or "") for row in out]
        self.assertEqual(names[:2], ["Spansh Sort First", "PlayerDB Sort Second"])

    def test_smoke_runtime_mixed_source_profiles_and_target_system_name(self) -> None:
        playerdb_rows = [
            {
                "name": "F32 PlayerDB Prime",
                "system_name": "F32_PLAYER_SYS",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 8.0,
                "distance_ls": 1500.0,
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
                "name": "F32 Offline Port",
                "system_name": "F32_OFFLINE_SYS",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 9.0,
                "distance_ls": 1200.0,
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
        swr_snapshot = {
            "status": "FRESH",
            "age_sec": 30.0,
            "entry": {
                "saved_at_utc": "2026-03-01T09:30:00Z",
                "source_status": "providers",
                "candidates": [
                    {
                        "name": "F32 SWR Spansh Port",
                        "system_name": "F32_SWR_SYS",
                        "type": "station",
                        "services": {"has_uc": True, "has_vista": False},
                        "distance_ly": 20.0,
                        "distance_ls": 800.0,
                        "source": "SPANSH",
                        "freshness_ts": "2026-03-01T09:30:00Z",
                    }
                ],
            },
        }

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=[],
            ),
            patch("logic.events.cash_in_assistant.edsm_provider_resilience_snapshot", return_value={}),
            patch("logic.events.cash_in_assistant._load_swr_snapshot", return_value=swr_snapshot),
            patch(
                "logic.events.cash_in_assistant.station_candidates_from_playerdb",
                return_value=(playerdb_rows, playerdb_meta),
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_from_offline_index",
                return_value=(offline_rows, offline_meta),
            ),
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
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        ranking_meta = dict(structured.get("ranking_meta") or {})
        candidates = [
            dict(item)
            for item in (structured.get("station_candidates") or [])
            if isinstance(item, dict)
        ]

        self.assertEqual(str(station_meta.get("source_status") or ""), "playerdb")
        self.assertTrue(bool(station_meta.get("playerdb_lookup_attempted")))
        self.assertTrue(bool(station_meta.get("offline_index_lookup_attempted")))
        self.assertEqual(str(station_meta.get("swr_lookup_status") or ""), "FRESH")
        self.assertGreaterEqual(len(candidates), 3)

        source_union: set[str] = set()
        for row in candidates:
            for token in str(row.get("source") or "").split("+"):
                token_norm = str(token or "").strip().upper()
                if token_norm:
                    source_union.add(token_norm)
        self.assertIn("SWR_CACHE", source_union)
        self.assertIn("PLAYERDB", source_union)
        self.assertIn("OFFLINE_INDEX", source_union)

        profiles = [str(item).strip().upper() for item in (ranking_meta.get("profiles") or [])]
        self.assertEqual(profiles, ["SECURE_PORT", "NEAREST", "CARRIER_FRIENDLY"])
        self.assertEqual(str(structured.get("target_system_name") or ""), "F32_PLAYER_SYS")
        self.assertEqual(str(ctx.get("target_system_name") or ""), "F32_PLAYER_SYS")


if __name__ == "__main__":
    unittest.main()
