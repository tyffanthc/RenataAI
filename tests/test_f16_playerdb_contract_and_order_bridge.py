from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F16PlayerDbContractAndOrderBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.current_system = "F16_PLAYERDB_BRIDGE_SYS"
        app_state.current_station = ""
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
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        cash_in_assistant._reset_cash_in_local_known_cache_for_tests()
        cash_in_assistant._reset_cash_in_swr_cache_for_tests()

    @staticmethod
    def _payload() -> dict:
        return {
            "system": "F16_PLAYERDB_BRIDGE_SYS",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 3_000_000.0,
            "cash_in_session_estimated": 9_500_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_local_known_bridge_precedes_offline_index_and_exposes_bridge_labels(self) -> None:
        local_known_result = {
            "used": True,
            "age_sec": 120.0,
            "count": 1,
            "candidates": [
                {
                    "name": "F16 Local Known UC",
                    "system_name": "F16_LOCAL_SYS",
                    "type": "station",
                    "services": {"has_uc": True, "has_vista": False},
                    "distance_ly": 42.0,
                    "source": "LOCAL_KNOWN",
                }
            ],
        }

        with (
            patch(
                "logic.events.cash_in_assistant._load_local_known_candidates",
                return_value=local_known_result,
            ),
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
        self.assertFalse(offline_mock.called, "offline_index should not run before local known bridge")
        self.assertEqual(emit_mock.call_count, 1)

        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        edge_meta = dict(structured.get("edge_case_meta") or {})
        reasons = {str(item).strip().lower() for item in (edge_meta.get("reasons") or [])}

        self.assertEqual(str(station_meta.get("source_status") or ""), "local_known_fallback")
        self.assertEqual(str(station_meta.get("source_status_bridge") or ""), "playerdb_bridge")
        self.assertTrue(bool(station_meta.get("local_known_fallback_used")))
        self.assertTrue(bool(station_meta.get("playerdb_bridge_used")))
        self.assertEqual(str(station_meta.get("playerdb_bridge_source_status") or ""), "playerdb_bridge")
        self.assertEqual(str(station_meta.get("playerdb_bridge_backend") or ""), "runtime_memory_cache")
        order_contract = [str(x) for x in (station_meta.get("source_order_contract") or [])]
        self.assertIn("playerdb_bridge", order_contract)
        self.assertIn("offline_index", order_contract)
        self.assertLess(order_contract.index("playerdb_bridge"), order_contract.index("offline_index"))

        self.assertEqual(str(edge_meta.get("source_status_bridge") or ""), "playerdb_bridge")
        self.assertTrue(bool(edge_meta.get("playerdb_bridge_used")))
        self.assertIn("local_known_fallback", reasons)
        self.assertIn("playerdb_bridge", reasons)


if __name__ == "__main__":
    unittest.main()
