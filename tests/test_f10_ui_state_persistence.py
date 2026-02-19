from __future__ import annotations

import os
import tempfile
import unittest

import config
from logic.context_state_contract import default_state_contract, load_state_contract_file


class F10UiStatePersistenceTests(unittest.TestCase):
    def test_update_ui_state_merges_nested_payload(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_ui_state.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())

                config.update_ui_state({"main": {"active_tab_key": "spansh"}})
                config.update_ui_state(
                    {
                        "journal": {
                            "active_subtab_key": "feed",
                            "filters": {"pinned_only": True},
                        }
                    }
                )
                config.update_ui_state(
                    {
                        "spansh": {
                            "trade": {
                                "flags": {
                                    "large_pad": False,
                                    "planetary": True,
                                }
                            }
                        }
                    }
                )

                ui_state = config.get_ui_state(default={})
                self.assertEqual((ui_state.get("main") or {}).get("active_tab_key"), "spansh")
                self.assertEqual((ui_state.get("journal") or {}).get("active_subtab_key"), "feed")
                self.assertTrue(bool((((ui_state.get("journal") or {}).get("filters") or {}).get("pinned_only"))))
                trade_flags = (((ui_state.get("spansh") or {}).get("trade") or {}).get("flags") or {})
                self.assertFalse(bool(trade_flags.get("large_pad")))
                self.assertTrue(bool(trade_flags.get("planetary")))

                payload = load_state_contract_file(tmp_path)
                self.assertEqual(payload.get("ui_state"), ui_state)
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_get_ui_state_applies_defaults_overlay(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_ui_defaults.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())
                config.update_ui_state({"main": {"active_tab_key": "journal"}})

                merged = config.get_ui_state(
                    default={
                        "main": {"active_tab_key": "pulpit"},
                        "journal": {"active_subtab_key": "entries"},
                    }
                )
                self.assertEqual((merged.get("main") or {}).get("active_tab_key"), "journal")
                self.assertEqual((merged.get("journal") or {}).get("active_subtab_key"), "entries")
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_ui_state_hooks_are_present_in_gui_modules(self) -> None:
        project_root = os.path.dirname(os.path.dirname(__file__))
        paths = {
            "app": os.path.join(project_root, "gui", "app.py"),
            "spansh": os.path.join(project_root, "gui", "tabs", "spansh", "__init__.py"),
            "trade": os.path.join(project_root, "gui", "tabs", "spansh", "trade.py"),
            "logbook": os.path.join(project_root, "gui", "tabs", "logbook.py"),
        }

        for key, path in paths.items():
            self.assertTrue(os.path.exists(path), f"Missing expected file for UI hook check: {key}")

        with open(paths["app"], "r", encoding="utf-8", errors="ignore") as handle:
            app_content = handle.read()
        self.assertIn("_restore_main_tab_from_ui_state", app_content)
        self.assertIn("active_tab_key", app_content)

        with open(paths["spansh"], "r", encoding="utf-8", errors="ignore") as handle:
            spansh_content = handle.read()
        self.assertIn("_restore_tab_from_ui_state", spansh_content)
        self.assertIn("spansh", spansh_content)
        self.assertIn("active_tab_key", spansh_content)

        with open(paths["trade"], "r", encoding="utf-8", errors="ignore") as handle:
            trade_content = handle.read()
        self.assertIn("_collect_trade_ui_state_flags", trade_content)
        self.assertIn("_persist_trade_ui_state", trade_content)

        with open(paths["logbook"], "r", encoding="utf-8", errors="ignore") as handle:
            logbook_content = handle.read()
        self.assertIn("_persist_ui_state", logbook_content)
        self.assertIn("active_subtab_key", logbook_content)
        self.assertIn("pinned_only", logbook_content)


if __name__ == "__main__":
    unittest.main()
