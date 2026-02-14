from __future__ import annotations

import queue
import unittest

import config
from logic.capabilities import (
    CAP_VOICE_STT,
    capability_config_patch_from_free_policy,
)
from logic.utils.notify import MSG_QUEUE, execute_voice_stt_action


def _drain_queue() -> list[object]:
    items: list[object] = []
    try:
        while True:
            items.append(MSG_QUEUE.get_nowait())
    except queue.Empty:
        return items


class VoiceCapabilityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self.assertIsInstance(settings, dict)
        self._settings = settings
        self._original = {
            "plan.profile": settings.get("plan.profile"),
            "features.tts.free_policy_enabled": settings.get("features.tts.free_policy_enabled"),
            CAP_VOICE_STT: settings.get(CAP_VOICE_STT),
        }
        _drain_queue()

    def tearDown(self) -> None:
        for key, value in self._original.items():
            if value is None and key in self._settings:
                self._settings.pop(key, None)
            else:
                self._settings[key] = value
        _drain_queue()

    def test_free_profile_blocks_stt_action_and_emits_fallback(self) -> None:
        self._settings.update(capability_config_patch_from_free_policy(True))
        called = {"value": False}

        ok, result = execute_voice_stt_action(
            lambda: called.__setitem__("value", True),
        )

        self.assertFalse(ok)
        self.assertIsNone(result)
        self.assertFalse(called["value"])
        joined = " | ".join(str(item) for item in _drain_queue())
        self.assertIn("Tryb glosowy STT niedostepny", joined)

    def test_pro_profile_runs_stt_action(self) -> None:
        self._settings.update(capability_config_patch_from_free_policy(False))
        ok, result = execute_voice_stt_action(lambda: "ok")

        self.assertTrue(ok)
        self.assertEqual(result, "ok")

    def test_stt_action_failure_is_soft(self) -> None:
        self._settings.update(capability_config_patch_from_free_policy(False))

        def _boom() -> str:
            raise RuntimeError("boom")

        ok, result = execute_voice_stt_action(_boom)
        self.assertFalse(ok)
        self.assertIsNone(result)
        joined = " | ".join(str(item) for item in _drain_queue())
        self.assertIn("Akcja glosowa STT chwilowo niedostepna", joined)


if __name__ == "__main__":
    unittest.main()
