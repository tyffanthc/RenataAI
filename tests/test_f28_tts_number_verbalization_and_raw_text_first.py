from __future__ import annotations

import unicodedata
import unittest

from logic.tts.text_preprocessor import prepare_tts


def _norm_ascii(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(value or "").lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


class F28TtsNumberVerbalizationAndRawTextFirstTests(unittest.TestCase):
    def test_raw_text_first_path_applies_polish_repair_and_number_verbalization(self) -> None:
        text = prepare_tts(
            "MSG.CASH_IN_ASSISTANT",
            {
                "raw_text": "Dane warte 132 555 000 Cr. Rozwaz teraz, po domknieciu systemu albo pozniej."
            },
        ) or ""
        normalized = _norm_ascii(text)
        self.assertIn("rozwaz", normalized)
        self.assertIn("domknieciu", normalized)
        self.assertIn("milion", normalized)
        self.assertIn("kredyt", normalized)

    def test_percent_and_ly_are_read_as_polish_words(self) -> None:
        text = prepare_tts(
            "MSG.RUNTIME_CRITICAL",
            {"raw_text": "Progres 25% i dystans 33.9 LY."},
        ) or ""
        normalized = " ".join(_norm_ascii(text.replace(";", " ")).split())
        self.assertIn("dwadziescia piec procent", normalized)
        self.assertIn("trzydziesci trzy przecinek dziewiec lat swietlnych", normalized)
        self.assertIn(";", text)

    def test_commas_are_preserved_for_prosody(self) -> None:
        text = prepare_tts(
            "MSG.CASH_IN_ASSISTANT",
            {"raw_text": "Rozwaz teraz, po domknieciu systemu albo pozniej."},
        ) or ""
        self.assertIn(",", text)

    def test_credits_grouped_with_comma_or_nbsp_do_not_degrade_to_tail_zero(self) -> None:
        cases = [
            "Dane warte 132,555,000 Cr.",
            "Dane warte 132\u00A0555\u00A0000 Cr.",
        ]
        for raw_text in cases:
            with self.subTest(raw_text=raw_text):
                text = prepare_tts("MSG.CASH_IN_ASSISTANT", {"raw_text": raw_text}) or ""
                normalized = _norm_ascii(text)
                self.assertIn("milion", normalized)
                self.assertIn("kredyt", normalized)
                self.assertIn(";", text)
                self.assertNotIn("132,555,zero", normalized)
                self.assertNotIn("132 555 zero", normalized)

    def test_system_name_digits_are_verbalized_with_semicolon_breaks(self) -> None:
        text = prepare_tts("MSG.NEXT_HOP", {"system": "LHS 20"}) or ""
        normalized = _norm_ascii(text)
        self.assertIn("lhs", normalized)
        self.assertIn("dwadziescia", normalized)
        self.assertIn(";", text)

    def test_large_system_number_is_intentionally_verbalized_with_prosody_breaks(self) -> None:
        text = prepare_tts("MSG.JUMPED_SYSTEM", {"system": "HIP 63523"}) or ""
        normalized = _norm_ascii(text)
        self.assertIn("hip", normalized)
        self.assertNotIn("63523", normalized)
        self.assertIn("tysiac", normalized)
        self.assertIn(";", text)


if __name__ == "__main__":
    unittest.main()
