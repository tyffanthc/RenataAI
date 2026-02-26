from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


class _FakeVoice:
    def __init__(self, voice_id: str, *, name: str = "", languages=None) -> None:
        self.id = voice_id
        self.name = name
        self.languages = languages


class F40Pyttsx3PolishVoiceSelectionTests(unittest.TestCase):
    def test_selects_polish_voice_by_name(self) -> None:
        voices = [
            _FakeVoice("en_voice", name="Microsoft David Desktop"),
            _FakeVoice("pl_voice", name="Microsoft Paulina Polish"),
        ]
        self.assertEqual(notify_module._select_pyttsx3_voice_id(voices), "pl_voice")

    def test_selects_polish_voice_by_languages_metadata(self) -> None:
        voices = [
            _FakeVoice("en_voice", name="English Voice", languages=[b"\x05en-us"]),
            _FakeVoice("pl_voice", name="Fallback Voice", languages=[b"\x05pl-PL"]),
        ]
        self.assertEqual(notify_module._select_pyttsx3_voice_id(voices), "pl_voice")

    def test_falls_back_to_first_voice_when_no_polish_match(self) -> None:
        voices = [
            _FakeVoice("voice_a", name="English Voice", languages=["en-US"]),
            _FakeVoice("voice_b", name="German Voice", languages=["de-DE"]),
        ]
        self.assertEqual(notify_module._select_pyttsx3_voice_id(voices), "voice_a")

    def test_returns_none_for_empty_or_invalid_voice_list(self) -> None:
        self.assertIsNone(notify_module._select_pyttsx3_voice_id([]))
        self.assertIsNone(notify_module._select_pyttsx3_voice_id(None))

    def test_speak_pyttsx3_applies_polish_voice_in_engine_path(self) -> None:
        class _FakeEngine:
            def __init__(self) -> None:
                self._voices = [
                    _FakeVoice("en_voice", name="Microsoft David Desktop"),
                    _FakeVoice("pl_voice", name="Microsoft Paulina Polish"),
                ]
                self.set_calls: list[tuple[str, object]] = []
                self.spoken: list[str] = []

            def getProperty(self, key: str):  # noqa: N802 (pyttsx3 API shape)
                if key == "voices":
                    return self._voices
                return None

            def setProperty(self, key: str, value):  # noqa: N802 (pyttsx3 API shape)
                self.set_calls.append((key, value))

            def say(self, text: str) -> None:
                self.spoken.append(text)

            def runAndWait(self) -> None:
                return None

            def stop(self) -> None:
                return None

        fake_engine = _FakeEngine()

        with (
            patch("logic.utils.notify.pyttsx3.init", return_value=fake_engine),
            patch("logic.utils.notify.log_event"),
            patch("logic.utils.notify.config.get") as cfg_get,
        ):
            cfg_get.side_effect = lambda key, default=None: default
            notify_module._speak_pyttsx3("test komunikatu")

        self.assertIn(("voice", "pl_voice"), fake_engine.set_calls)
        self.assertIn(("rate", 155), fake_engine.set_calls)
        self.assertIn(("volume", 1.0), fake_engine.set_calls)
        self.assertEqual(fake_engine.spoken, ["test komunikatu"])


if __name__ == "__main__":
    unittest.main()
