from __future__ import annotations

import os
import tempfile
import unittest

import config
from logic.context_state_contract import default_state_contract, load_state_contract_file


class F10PreferencesPersistenceTests(unittest.TestCase):
    def test_update_preferences_persists_and_updates_runtime(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        runtime_settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        old_runtime = dict(runtime_settings) if isinstance(runtime_settings, dict) else {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_state = os.path.join(tmp_dir, "f10_preferences_state.json")
            try:
                config.STATE_FILE = tmp_state
                config.save_state_contract(default_state_contract())
                config.update_preferences(
                    {
                        "verbosity": "high",
                        "trade_choice_bias": "profit",
                        "tts_enabled": False,
                    }
                )

                prefs = config.get_preferences()
                self.assertEqual(prefs.get("verbosity"), "high")
                self.assertEqual(prefs.get("trade_choice_bias"), "profit")
                self.assertFalse(bool(prefs.get("tts_enabled")))

                self.assertFalse(bool(config.get("voice_enabled", True)))
                self.assertFalse(bool(config.get("tts_enabled", True)))

                payload = load_state_contract_file(tmp_state)
                saved_prefs = payload.get("preferences") or {}
                self.assertEqual(saved_prefs.get("verbosity"), "high")
                self.assertEqual(saved_prefs.get("trade_choice_bias"), "profit")
                self.assertFalse(bool(saved_prefs.get("tts_enabled")))
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)
                if isinstance(runtime_settings, dict):
                    runtime_settings.clear()
                    runtime_settings.update(old_runtime)

    def test_config_save_syncs_voice_enabled_to_preferences(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        manager = config.config
        old_settings_path = str(getattr(manager, "settings_path", ""))
        runtime_settings = getattr(manager, "_settings", None)  # type: ignore[attr-defined]
        old_runtime = dict(runtime_settings) if isinstance(runtime_settings, dict) else {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_state = os.path.join(tmp_dir, "f10_preferences_save_state.json")
            tmp_settings = os.path.join(tmp_dir, "f10_preferences_user_settings.json")
            try:
                config.STATE_FILE = tmp_state
                config.save_state_contract(default_state_contract())
                manager.settings_path = tmp_settings
                if isinstance(runtime_settings, dict):
                    runtime_settings.clear()
                    runtime_settings.update(old_runtime)

                config.save({"voice_enabled": False})

                prefs = config.get_preferences()
                self.assertFalse(bool(prefs.get("tts_enabled")))
                self.assertFalse(bool(config.get("voice_enabled", True)))
                self.assertTrue(os.path.exists(tmp_settings))
            finally:
                manager.settings_path = old_settings_path
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)
                if isinstance(runtime_settings, dict):
                    runtime_settings.clear()
                    runtime_settings.update(old_runtime)

    def test_invalid_preferences_are_normalized(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        runtime_settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        old_runtime = dict(runtime_settings) if isinstance(runtime_settings, dict) else {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_state = os.path.join(tmp_dir, "f10_preferences_normalize_state.json")
            try:
                config.STATE_FILE = tmp_state
                config.save_state_contract(default_state_contract())
                config.update_preferences(
                    {
                        "verbosity": "very-loud",
                        "trade_choice_bias": "aggressive",
                        "tts_enabled": "off",
                    }
                )

                prefs = config.get_preferences()
                self.assertEqual(prefs.get("verbosity"), "normal")
                self.assertEqual(prefs.get("trade_choice_bias"), "balanced")
                self.assertFalse(bool(prefs.get("tts_enabled")))
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)
                if isinstance(runtime_settings, dict):
                    runtime_settings.clear()
                    runtime_settings.update(old_runtime)


if __name__ == "__main__":
    unittest.main()
