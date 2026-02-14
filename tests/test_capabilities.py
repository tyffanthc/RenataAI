from __future__ import annotations

import unittest

from logic.capabilities import (
    CAP_SETTINGS_FULL,
    CAP_TTS_ADVANCED_POLICY,
    CAP_UI_EXTENDED_TABS,
    CAP_VOICE_STT,
    PROFILE_FREE,
    PROFILE_PRO,
    capability_config_patch_from_free_policy,
    resolve_capabilities,
    resolve_profile,
)


class CapabilitiesTests(unittest.TestCase):
    def test_resolve_profile_falls_back_to_legacy_free_policy_flag(self) -> None:
        free_profile = resolve_profile({"features.tts.free_policy_enabled": True})
        pro_profile = resolve_profile({"features.tts.free_policy_enabled": False})
        self.assertEqual(free_profile, PROFILE_FREE)
        self.assertEqual(pro_profile, PROFILE_PRO)

    def test_resolve_capabilities_uses_profile_defaults(self) -> None:
        free_caps = resolve_capabilities({"plan.profile": "FREE"})
        pro_caps = resolve_capabilities({"plan.profile": "PRO"})

        self.assertFalse(free_caps.has(CAP_SETTINGS_FULL))
        self.assertFalse(free_caps.has(CAP_UI_EXTENDED_TABS))
        self.assertFalse(free_caps.has(CAP_TTS_ADVANCED_POLICY))
        self.assertFalse(free_caps.has(CAP_VOICE_STT))

        self.assertTrue(pro_caps.has(CAP_SETTINGS_FULL))
        self.assertTrue(pro_caps.has(CAP_UI_EXTENDED_TABS))
        self.assertTrue(pro_caps.has(CAP_TTS_ADVANCED_POLICY))
        self.assertTrue(pro_caps.has(CAP_VOICE_STT))

    def test_explicit_capability_override_wins_over_profile_default(self) -> None:
        caps = resolve_capabilities(
            {
                "plan.profile": "FREE",
                CAP_UI_EXTENDED_TABS: True,
                CAP_SETTINGS_FULL: True,
            }
        )
        self.assertTrue(caps.has(CAP_UI_EXTENDED_TABS))
        self.assertTrue(caps.has(CAP_SETTINGS_FULL))

    def test_capability_patch_from_free_policy(self) -> None:
        free_patch = capability_config_patch_from_free_policy(True)
        pro_patch = capability_config_patch_from_free_policy(False)

        self.assertEqual(free_patch["plan.profile"], PROFILE_FREE)
        self.assertFalse(free_patch[CAP_TTS_ADVANCED_POLICY])
        self.assertFalse(free_patch[CAP_SETTINGS_FULL])

        self.assertEqual(pro_patch["plan.profile"], PROFILE_PRO)
        self.assertTrue(pro_patch[CAP_TTS_ADVANCED_POLICY])
        self.assertTrue(pro_patch[CAP_SETTINGS_FULL])


if __name__ == "__main__":
    unittest.main()

