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
            patch("logic.utils.notify.log_event_throttled") as throttled_log,
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
        throttled_log.assert_called()
        self.assertTrue(
            any(
                call.args[:4]
                == (
                    "tts:auto_pyttsx3_fallback_blocked",
                    5000,
                    "TTS",
                    "auto fallback to pyttsx3 blocked (focus-safe)",
                )
                for call in throttled_log.call_args_list
            ),
            "Expected throttled TTS diagnostic log entry for blocked auto fallback.",
        )
        self.assertTrue(
            any(str(call.kwargs.get("reason", "")) == "tts.auto_allow_pyttsx3_fallback=false" for call in throttled_log.call_args_list),
            "Expected explicit reason in throttled diagnostic log entry.",
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
                else True if key == "tts.pyttsx3_allow_focus_risk"
                else default
            )
            notify_module._speak_tts("test")
            pyttsx3_speak.assert_called_once()

    def test_auto_mode_with_fallback_opt_in_still_blocks_when_focus_risk_opt_in_missing(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.tts.piper_tts.select_piper_paths", return_value=None),
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
            patch("logic.utils.notify.log_event_throttled") as throttled_log,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "auto" if key == "tts.engine"
                else True if key == "tts.auto_allow_pyttsx3_fallback"
                else False if key == "tts.pyttsx3_allow_focus_risk"
                else default
            )
            notify_module._speak_tts("test")

        pyttsx3_speak.assert_not_called()
        self.assertTrue(
            any(
                call.args[:4]
                == (
                    "tts:pyttsx3_focus_risk_blocked",
                    5000,
                    "TTS",
                    "pyttsx3 blocked (focus-safe)",
                )
                for call in throttled_log.call_args_list
            )
        )

    def test_explicit_pyttsx3_engine_is_blocked_by_default_for_focus_safety(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
            patch("logic.utils.notify.log_event_throttled") as throttled_log,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "pyttsx3" if key == "tts.engine"
                else False if key == "tts.auto_allow_pyttsx3_fallback"
                else False if key == "tts.pyttsx3_allow_focus_risk"
                else default
            )
            notify_module._speak_tts("test")
            pyttsx3_speak.assert_not_called()
            self.assertTrue(
                any(
                    call.args[:4]
                    == (
                        "tts:pyttsx3_focus_risk_blocked",
                        5000,
                        "TTS",
                        "pyttsx3 blocked (focus-safe)",
                    )
                    for call in throttled_log.call_args_list
                )
            )

    def test_explicit_pyttsx3_engine_can_run_when_focus_risk_opt_in_enabled(self) -> None:
        with (
            patch("logic.utils.notify.config.get") as cfg_get,
            patch("logic.utils.notify._speak_pyttsx3") as pyttsx3_speak,
        ):
            cfg_get.side_effect = lambda key, default=None: (
                "pyttsx3" if key == "tts.engine"
                else False if key == "tts.auto_allow_pyttsx3_fallback"
                else True if key == "tts.pyttsx3_allow_focus_risk"
                else default
            )
            notify_module._speak_tts("test")
            pyttsx3_speak.assert_called_once()


if __name__ == "__main__":
    unittest.main()
