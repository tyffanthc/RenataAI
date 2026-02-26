from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
