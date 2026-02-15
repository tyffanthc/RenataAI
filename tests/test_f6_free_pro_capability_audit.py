from __future__ import annotations

import os
import unittest

import config
from logic.capabilities import (
    CAP_SETTINGS_FULL,
    CAP_TTS_ADVANCED_POLICY,
    CAP_UI_EXTENDED_TABS,
    CAP_VOICE_STT,
    PROFILE_FREE,
    capability_config_patch_from_free_policy,
    has_capability,
    resolve_capabilities,
)
from logic.event_insight_mapping import resolve_emit_contract


class F6FreeProCapabilityAuditTests(unittest.TestCase):
    def test_default_settings_profile_is_free_pub(self) -> None:
        caps = resolve_capabilities(config.DEFAULT_SETTINGS)

        self.assertEqual(caps.profile, PROFILE_FREE)
        self.assertFalse(caps.has(CAP_SETTINGS_FULL))
        self.assertFalse(caps.has(CAP_UI_EXTENDED_TABS))
        self.assertFalse(caps.has(CAP_TTS_ADVANCED_POLICY))
        self.assertFalse(caps.has(CAP_VOICE_STT))
        self.assertTrue(bool(config.DEFAULT_SETTINGS.get("features.tts.free_policy_enabled", False)))

    def test_action_modules_do_not_contain_plan_or_capability_checks(self) -> None:
        action_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logic", "events")
        forbidden_markers = (
            "plan.profile",
            "features.tts.free_policy_enabled",
            "logic.capabilities",
            "CAP_VOICE_STT",
            "CAP_UI_EXTENDED_TABS",
            "CAP_SETTINGS_FULL",
            "CAP_TTS_ADVANCED_POLICY",
        )

        for filename in os.listdir(action_dir):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(action_dir, filename)
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                content = f.read()
            for marker in forbidden_markers:
                self.assertNotIn(
                    marker,
                    content,
                    f"Forbidden marker '{marker}' found in action module: {path}",
                )

    def test_emit_contract_is_profile_agnostic(self) -> None:
        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self.assertIsInstance(settings, dict)
        runtime_settings = settings

        original = {
            "plan.profile": runtime_settings.get("plan.profile"),
            "features.tts.free_policy_enabled": runtime_settings.get("features.tts.free_policy_enabled"),
            CAP_VOICE_STT: runtime_settings.get(CAP_VOICE_STT),
            CAP_UI_EXTENDED_TABS: runtime_settings.get(CAP_UI_EXTENDED_TABS),
            CAP_SETTINGS_FULL: runtime_settings.get(CAP_SETTINGS_FULL),
            CAP_TTS_ADVANCED_POLICY: runtime_settings.get(CAP_TTS_ADVANCED_POLICY),
        }

        try:
            runtime_settings.update(capability_config_patch_from_free_policy(True))
            free_contract = resolve_emit_contract(
                message_id="MSG.ROUTE_DESYNC",
                context={"system": "SOL"},
                event_type="ROUTE_PROGRESS",
            )

            runtime_settings.update(capability_config_patch_from_free_policy(False))
            pro_contract = resolve_emit_contract(
                message_id="MSG.ROUTE_DESYNC",
                context={"system": "SOL"},
                event_type="ROUTE_PROGRESS",
            )

            self.assertEqual(free_contract, pro_contract)
        finally:
            for key, value in original.items():
                if value is None and key in runtime_settings:
                    runtime_settings.pop(key, None)
                else:
                    runtime_settings[key] = value

    def test_runtime_capability_patch_stays_on_channel_layer(self) -> None:
        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self.assertIsInstance(settings, dict)
        runtime_settings = settings

        original = {
            "plan.profile": runtime_settings.get("plan.profile"),
            "features.tts.free_policy_enabled": runtime_settings.get("features.tts.free_policy_enabled"),
            CAP_VOICE_STT: runtime_settings.get(CAP_VOICE_STT),
            CAP_UI_EXTENDED_TABS: runtime_settings.get(CAP_UI_EXTENDED_TABS),
            CAP_SETTINGS_FULL: runtime_settings.get(CAP_SETTINGS_FULL),
            CAP_TTS_ADVANCED_POLICY: runtime_settings.get(CAP_TTS_ADVANCED_POLICY),
        }

        try:
            runtime_settings.update(capability_config_patch_from_free_policy(True))
            self.assertFalse(has_capability(CAP_VOICE_STT))
            self.assertFalse(has_capability(CAP_UI_EXTENDED_TABS))
            self.assertFalse(has_capability(CAP_SETTINGS_FULL))
            self.assertFalse(has_capability(CAP_TTS_ADVANCED_POLICY))

            runtime_settings.update(capability_config_patch_from_free_policy(False))
            self.assertTrue(has_capability(CAP_VOICE_STT))
            self.assertTrue(has_capability(CAP_UI_EXTENDED_TABS))
            self.assertTrue(has_capability(CAP_SETTINGS_FULL))
            self.assertTrue(has_capability(CAP_TTS_ADVANCED_POLICY))
        finally:
            for key, value in original.items():
                if value is None and key in runtime_settings:
                    runtime_settings.pop(key, None)
                else:
                    runtime_settings[key] = value


if __name__ == "__main__":
    unittest.main()
