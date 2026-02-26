from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


class F31TtsAutoPyttsx3FallbackFocusSafeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_engine_logged = getattr(notify_module, "_TTS_ENGINE_LOGGED", False)
        notify_module._TTS_ENGINE_LOGGED = False

    def tearDown(self) -> None:
        notify_module._TTS_ENGINE_LOGGED = self._saved_engine_logged

    def test_auto_mode_blocks_pyttsx3_fallback_by_default_when_piper_missing(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.tts.piper_tts.select_piper_paths", return_value=None),
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "auto" if key == "tts.engine"
                else False if key == "tts.auto_allow_pyttsx3_fallback"
                else default
            )
            notify_module._speak_tts("test")
            pyttsx3_speak.assert_not_called()

    def test_auto_mode_blocked_fallback_logs_user_facing_diagnostic(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.tts.piper_tts.select_piper_paths", return_value=None),
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
            patch("logic.utils.notify._log_notify_soft_failure") as soft_log,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "auto" if key == "tts.engine"
                else False if key == "tts.auto_allow_pyttsx3_fallback"
                else default
            )
            notify_module._speak_tts("test")

        pyttsx3_speak.assert_not_called()
        soft_log.assert_called()
        self.assertTrue(
            any("fallback pyttsx3 jest zablokowany" in str(call.args[1]) for call in soft_log.call_args_list),
            "Expected user-facing diagnostic when auto fallback is blocked.",
        )

    def test_auto_mode_can_allow_pyttsx3_fallback_when_opted_in(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.tts.piper_tts.select_piper_paths", return_value=None),
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "auto" if key == "tts.engine"
                else True if key == "tts.auto_allow_pyttsx3_fallback"
                else default
            )
            notify_module._speak_tts("test")
            pyttsx3_speak.assert_called_once()

    def test_explicit_pyttsx3_engine_still_works_even_when_auto_fallback_blocked(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "pyttsx3" if key == "tts.engine"
                else False if key == "tts.auto_allow_pyttsx3_fallback"
                else default
            )
            notify_module._speak_tts("test")
            pyttsx3_speak.assert_called_once()


if __name__ == "__main__":
    unittest.main()
