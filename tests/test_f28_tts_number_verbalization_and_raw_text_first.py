from __future__ import annotations

import unittest

from logic.tts.text_preprocessor import prepare_tts


class F28TtsNumberVerbalizationAndRawTextFirstTests(unittest.TestCase):
    def test_raw_text_first_path_applies_polish_repair_and_number_verbalization(self) -> None:
        text = prepare_tts(
            "MSG.CASH_IN_ASSISTANT",
            {
                "raw_text": "Dane warte 132 555 000 Cr. Rozwaz teraz, po domknieciu systemu albo pozniej."
            },
        ) or ""
        self.assertIn("Rozważ", text)
        self.assertIn("domknięciu", text)
        self.assertIn("milion", text.lower())
        self.assertIn("kredyt", text.lower())

    def test_percent_and_ly_are_read_as_polish_words(self) -> None:
        text = prepare_tts(
            "MSG.RUNTIME_CRITICAL",
            {"raw_text": "Progres 25% i dystans 33.9 LY."},
        ) or ""
        lowered = text.lower()
        self.assertIn("dwadzieścia pięć procent", lowered)
        self.assertIn("trzydzieści trzy przecinek dziewięć lat świetlnych", lowered)


    def test_commas_are_preserved_for_prosody(self) -> None:
        text = prepare_tts(
            "MSG.CASH_IN_ASSISTANT",
            {"raw_text": "Rozwaz teraz, po domknieciu systemu albo pozniej."},
        ) or ""
        self.assertIn(",", text)


if __name__ == "__main__":
    unittest.main()

