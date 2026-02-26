from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from logic.tts import piper_tts


class _FakeTmpWav:
    def __init__(self, path: str) -> None:
        self.name = path

    def close(self) -> None:
        return None


class F44PiperTtsTimeoutAndCleanupTests(unittest.TestCase):
    def test_speak_applies_timeout_and_cleans_up_when_piper_hangs(self) -> None:
        selected = piper_tts.PiperPaths(
            bin_path="C:/fake/piper.exe",
            model_path="C:/fake/model.onnx",
            config_path="C:/fake/model.json",
            source="appdata",
        )
        fake_tmp_path = "C:/fake/renata-piper-timeout.wav"

        with (
            patch("logic.tts.piper_tts._is_runtime_ready", return_value=True),
            patch("logic.tts.piper_tts.tempfile.NamedTemporaryFile", return_value=_FakeTmpWav(fake_tmp_path)),
            patch("logic.tts.piper_tts.os.remove") as remove_mock,
            patch("logic.tts.piper_tts.log_event_throttled") as throttled_log,
            patch("logic.tts.piper_tts.config.get") as cfg_get,
            patch("logic.tts.piper_tts.subprocess.run") as run_mock,
        ):
            cfg_get.side_effect = lambda key, default=None: default
            run_mock.side_effect = subprocess.TimeoutExpired(cmd=["piper.exe"], timeout=15.0)

            ok = piper_tts.speak("test timeout", paths=selected)

        self.assertFalse(ok)
        self.assertEqual(float(run_mock.call_args.kwargs.get("timeout") or 0.0), 15.0)
        remove_mock.assert_called_once_with(fake_tmp_path)

        self.assertTrue(throttled_log.called)
        first_call = throttled_log.call_args_list[0]
        self.assertEqual(first_call.args[0], "piper_speak_exception")
        self.assertIn("TimeoutExpired", str(first_call.kwargs.get("error", "")))


if __name__ == "__main__":
    unittest.main()
