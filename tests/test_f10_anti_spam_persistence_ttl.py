from __future__ import annotations

import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import config
from app.state import app_state
from gui import common_route_progress as route_progress
from logic.context_state_contract import default_state_contract
from logic.events import smuggler_events, trade_events
from logic.utils import notify as notify_module


class F10AntiSpamPersistenceTTLTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", "")

    def tearDown(self) -> None:
        try:
            app_state.current_system = self._saved_system
        except Exception:
            pass
        try:
            notify_module.DEBOUNCER.reset()
        except Exception:
            pass
        try:
            trade_events.reset_jackpot_runtime_state()
        except Exception:
            pass
        try:
            smuggler_events.reset_smuggler_runtime_state()
        except Exception:
            pass
        try:
            route_progress._ROUTE_MILESTONE_CACHE = {}
            route_progress._ROUTE_MILESTONE_CACHE_LOADED = False
            route_progress._ROUTE_MILESTONE_CACHE_LAST_PERSIST_TS = 0.0
        except Exception:
            pass

    @contextmanager
    def _temp_state_contract(self):
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_anti_spam_persistence.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())
                yield tmp_path
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_debouncer_windows_persist_and_block_duplicate_after_restart(self) -> None:
        with self._temp_state_contract():
            notify_module.DEBOUNCER.reset()

            first = notify_module.DEBOUNCER.can_send(
                "INSIGHT_ENTITY:MSG.FSS_PROGRESS_25",
                cooldown_sec=120.0,
                context="fss25:F10_SYSTEM",
            )
            self.assertTrue(first)

            notify_module.DEBOUNCER.reset()
            load_stats = notify_module.DEBOUNCER.load_from_contract(force=True)
            self.assertTrue(bool(load_stats.get("loaded")))

            second = notify_module.DEBOUNCER.can_send(
                "INSIGHT_ENTITY:MSG.FSS_PROGRESS_25",
                cooldown_sec=120.0,
                context="fss25:F10_SYSTEM",
            )
            self.assertFalse(second, "Restart should preserve debouncer cooldown window.")

    def test_debouncer_ttl_prunes_stale_entries(self) -> None:
        with self._temp_state_contract():
            now = time.time()
            stale_ts = now - (float(config.get("anti_spam.debouncer.ttl_sec", 900.0)) + 120.0)
            fresh_ts = now - 5.0
            config.update_anti_spam_state(
                {
                    "dispatcher_debouncer_windows": {
                        "schema_version": 1,
                        "updated_at": int(now),
                        "entries": [
                            {"key": "INSIGHT_ENTITY:OLD", "context": "old", "last_ts": stale_ts},
                            {"key": "INSIGHT_ENTITY:NEW", "context": "fresh", "last_ts": fresh_ts},
                        ],
                    }
                }
            )

            notify_module.DEBOUNCER.reset()
            notify_module.DEBOUNCER.load_from_contract(force=True)
            state = notify_module.DEBOUNCER.export_state()
            entries = list(state.get("entries") or [])
            keys = {(str(row.get("key")), str(row.get("context"))) for row in entries if isinstance(row, dict)}
            self.assertIn(("INSIGHT_ENTITY:NEW", "fresh"), keys)
            self.assertNotIn(("INSIGHT_ENTITY:OLD", "old"), keys)

    def test_trade_jackpot_cache_persists_across_restart(self) -> None:
        with self._temp_state_contract():
            trade_events.reset_jackpot_runtime_state()
            app_state.current_system = "F10_TRADE_SYSTEM"
            payload = {
                "StationName": "F10_TRADE_STATION",
                "Items": [
                    {
                        "Name_Localised": "Gold",
                        "Stock": 128,
                        "BuyPrice": 7000,
                    }
                ],
            }

            with patch("logic.events.trade_events.powiedz") as powiedz_mock:
                trade_events.handle_market_data(payload, gui_ref=None)
                self.assertEqual(powiedz_mock.call_count, 1)

            trade_events.reset_jackpot_runtime_state()
            with patch("logic.events.trade_events.powiedz") as powiedz_mock:
                trade_events.handle_market_data(payload, gui_ref=None)
                self.assertEqual(powiedz_mock.call_count, 0)

    def test_smuggler_warned_targets_persist_across_restart(self) -> None:
        with self._temp_state_contract():
            smuggler_events.reset_smuggler_runtime_state()
            smuggler_events.CARGO_HAS_ILLEGAL = True
            ev = {"event": "DockingRequested", "StationName": "F10_SMUGGLER_STATION"}

            with patch("logic.events.smuggler_events.powiedz") as powiedz_mock:
                smuggler_events.handle_smuggler_alert(ev, gui_ref=None)
                self.assertEqual(powiedz_mock.call_count, 1)

            smuggler_events.reset_smuggler_runtime_state()
            smuggler_events.CARGO_HAS_ILLEGAL = True
            with patch("logic.events.smuggler_events.powiedz") as powiedz_mock:
                smuggler_events.handle_smuggler_alert(ev, gui_ref=None)
                self.assertEqual(powiedz_mock.call_count, 0)

    def test_route_milestone_progress_cache_restores_announced_thresholds(self) -> None:
        with self._temp_state_contract():
            route_progress._ROUTE_MILESTONE_CACHE = {}
            route_progress._ROUTE_MILESTONE_CACHE_LOADED = False
            route_progress._ROUTE_MILESTONE_CACHE_LAST_PERSIST_TS = 0.0

            route = ["F10_A", "F10_B", "F10_C", "F10_D"]
            text = " -> ".join(route)
            sig = "F10_ROUTE_SIG_CACHE"
            route_progress._set_active_route_data(route, text, sig, source="test.route.setup")
            route_progress._ACTIVE_MILESTONE_TARGET_NORM = route_progress.normalize_system_name("F10_C")
            route_progress._ACTIVE_MILESTONE_TARGET_RAW = "F10_C"
            route_progress._ACTIVE_MILESTONE_TARGET_INDEX = 2
            route_progress._ACTIVE_MILESTONE_START_INDEX = 0
            route_progress._ACTIVE_MILESTONE_START_REMAINING = None
            route_progress._ACTIVE_MILESTONE_ANNOUNCED = {25, 50}
            route_progress._save_active_milestone_progress_cache(force=True)

            route_progress._ACTIVE_MILESTONE_TARGET_NORM = None
            route_progress._ACTIVE_MILESTONE_TARGET_RAW = None
            route_progress._ACTIVE_MILESTONE_TARGET_INDEX = None
            route_progress._ACTIVE_MILESTONE_START_INDEX = 0
            route_progress._ACTIVE_MILESTONE_START_REMAINING = None
            route_progress._ACTIVE_MILESTONE_ANNOUNCED = set()
            route_progress._ROUTE_MILESTONE_CACHE = {}
            route_progress._ROUTE_MILESTONE_CACHE_LOADED = False

            route_progress._set_active_route_data(route, text, sig, source="test.route.restart")

            self.assertEqual(route_progress._ACTIVE_MILESTONE_TARGET_INDEX, 2)
            self.assertEqual(route_progress._ACTIVE_MILESTONE_TARGET_RAW, "F10_C")
            self.assertEqual(route_progress._ACTIVE_MILESTONE_ANNOUNCED, {25, 50})


if __name__ == "__main__":
    unittest.main()
