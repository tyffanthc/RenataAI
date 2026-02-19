from __future__ import annotations

import os
import tempfile
import unittest
import time
from contextlib import contextmanager
from unittest.mock import patch

import config
from app.state import app_state
from logic.context_state_contract import (
    STATE_SCHEMA_VERSION,
    default_state_contract,
    load_state_contract_file,
    restart_loss_audit_contract,
)
from logic.events import smuggler_events, trade_events
from logic.utils import notify as notify_module


class F10QualityGatesAndSmokeTests(unittest.TestCase):
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

    @contextmanager
    def _temp_state_contract(self):
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_quality_state.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())
                yield tmp_path
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_corrupted_state_file_falls_back_to_default_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "corrupt_state.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{this is not valid json")

            loaded = load_state_contract_file(path)
            self.assertEqual(int(loaded.get("schema_version") or 0), STATE_SCHEMA_VERSION)
            self.assertIsInstance(loaded.get("ui_state"), dict)
            self.assertIsInstance(loaded.get("preferences"), dict)
            self.assertIsInstance(loaded.get("domain_state"), dict)
            self.assertIsInstance(loaded.get("anti_spam_state"), dict)

    def test_restart_loss_audit_policy_contract_is_explicit(self) -> None:
        audit = restart_loss_audit_contract()
        self.assertEqual(str((audit.get("exobio_sample_state") or {}).get("decision") or ""), "persist")
        self.assertEqual(
            str((audit.get("combat_survival_pattern_runtime") or {}).get("decision") or ""),
            "session-only",
        )
        decisions = {
            str((row or {}).get("decision") or "")
            for row in audit.values()
            if isinstance(row, dict)
        }
        self.assertIn("persist", decisions)
        self.assertIn("session-only", decisions)

    def test_anti_spam_limits_keep_debouncer_state_bounded(self) -> None:
        with self._temp_state_contract():
            max_keys = int(config.get("anti_spam.debouncer.max_keys", 800))
            now_ts = time.time()
            entries = [
                {"key": f"INSIGHT_ENTITY:MSG.{idx}", "context": f"ctx-{idx}", "last_ts": now_ts - (idx % 30)}
                for idx in range(max_keys + 100)
            ]
            config.update_anti_spam_state(
                {
                    "dispatcher_debouncer_windows": {
                        "schema_version": 1,
                        "updated_at": 123456,
                        "entries": entries,
                    }
                }
            )

            notify_module.DEBOUNCER.reset()
            load_stats = notify_module.DEBOUNCER.load_from_contract(force=True)
            self.assertTrue(bool(load_stats.get("loaded")))
            exported = notify_module.DEBOUNCER.export_state()
            exported_entries = exported.get("entries") or []
            self.assertLessEqual(len(exported_entries), max_keys)

    def test_restart_smoke_restores_ui_preferences_and_domain_layers(self) -> None:
        with self._temp_state_contract() as path:
            config.update_ui_state(
                {
                    "main": {"active_tab_key": "journal"},
                    "journal": {"active_subtab_key": "entries"},
                }
            )
            config.update_preferences(
                {
                    "verbosity": "high",
                    "trade_choice_bias": "safety",
                    "tts_enabled": False,
                }
            )
            config.update_domain_state(
                {
                    "sys": "F10_SMOKE_SYSTEM",
                    "route_mode": "awareness",
                    "route_target": "F10_SMOKE_TARGET",
                }
            )

            # Simulated app restart: read persisted contract and re-apply runtime snapshot.
            restored = load_state_contract_file(path)
            config.save_state_contract(restored)

            ui_state = config.get_ui_state(default={})
            prefs = config.get_preferences(default={})
            domain = config.get_domain_state(default={})

            self.assertEqual((ui_state.get("main") or {}).get("active_tab_key"), "journal")
            self.assertEqual((ui_state.get("journal") or {}).get("active_subtab_key"), "entries")
            self.assertEqual(str(prefs.get("verbosity") or ""), "high")
            self.assertEqual(str(prefs.get("trade_choice_bias") or ""), "safety")
            self.assertFalse(bool(prefs.get("tts_enabled")))
            self.assertEqual(str(domain.get("sys") or ""), "F10_SMOKE_SYSTEM")
            self.assertEqual(str(domain.get("route_mode") or ""), "awareness")
            self.assertEqual(str(domain.get("route_target") or ""), "F10_SMOKE_TARGET")

    def test_restart_smoke_anti_spam_persistence_blocks_duplicate_alerts(self) -> None:
        with self._temp_state_contract():
            notify_module.DEBOUNCER.reset()
            trade_events.reset_jackpot_runtime_state()
            smuggler_events.reset_smuggler_runtime_state()

            app_state.current_system = "F10_SMOKE_TRADE_SYSTEM"
            trade_payload = {
                "StationName": "F10_SMOKE_TRADE_STATION",
                "Items": [{"Name_Localised": "Gold", "Stock": 120, "BuyPrice": 7000}],
            }

            with patch("logic.events.trade_events.powiedz") as trade_tts:
                trade_events.handle_market_data(trade_payload, gui_ref=None)
                self.assertEqual(trade_tts.call_count, 1)

            trade_events.reset_jackpot_runtime_state()
            with patch("logic.events.trade_events.powiedz") as trade_tts:
                trade_events.handle_market_data(trade_payload, gui_ref=None)
                self.assertEqual(trade_tts.call_count, 0)

            smuggler_events.CARGO_HAS_ILLEGAL = True
            smuggler_ev = {"event": "DockingRequested", "StationName": "F10_SMOKE_SMUGGLER_STATION"}

            with patch("logic.events.smuggler_events.powiedz") as smuggler_tts:
                smuggler_events.handle_smuggler_alert(smuggler_ev, gui_ref=None)
                self.assertEqual(smuggler_tts.call_count, 1)

            smuggler_events.reset_smuggler_runtime_state()
            smuggler_events.CARGO_HAS_ILLEGAL = True
            with patch("logic.events.smuggler_events.powiedz") as smuggler_tts:
                smuggler_events.handle_smuggler_alert(smuggler_ev, gui_ref=None)
                self.assertEqual(smuggler_tts.call_count, 0)


if __name__ == "__main__":
    unittest.main()
