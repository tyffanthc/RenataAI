from __future__ import annotations

import unicodedata
import unittest

from logic.tts.text_preprocessor import _plural_form_pl, prepare_tts


def _norm_ascii(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(value or "").lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


class TtsPolishPluralFormEdgeCasesTests(unittest.TestCase):
    """T7-01: Polish plural forms - special 11-19 rule and n%10==1 boundary.

    Polish pluralization rules for nouns counted with integers:
      n == 1                       -> singular  (jeden kredyt)
      n % 100 in [10..19]          -> genitive  (jedenaście kredytów)  <- special 11-19 rule
      n % 10 == 1  (not in 11-19) -> singular  (dwadzieścia jeden kredyt)
      n % 10 in [2..4]             -> nominative plural (dwa kredyty)
      else                         -> genitive  (pięć kredytów)
    """

    # ------------------------------------------------------------------
    # Direct _plural_form_pl unit tests
    # ------------------------------------------------------------------

    def test_1_singular(self) -> None:
        self.assertEqual(_plural_form_pl(1, "kredyt", "kredyty", "kredytów"), "kredyt")

    def test_11_genitive_not_singular(self) -> None:
        """11 ends in 1 but is in the special 11-19 range -> genitive."""
        self.assertEqual(_plural_form_pl(11, "kredyt", "kredyty", "kredytów"), "kredytów")

    def test_21_singular(self) -> None:
        """21 ends in 1, NOT in 11-19 range -> singular."""
        self.assertEqual(_plural_form_pl(21, "kredyt", "kredyty", "kredytów"), "kredyt")

    def test_31_singular(self) -> None:
        self.assertEqual(_plural_form_pl(31, "kredyt", "kredyty", "kredytów"), "kredyt")

    def test_91_singular(self) -> None:
        self.assertEqual(_plural_form_pl(91, "kredyt", "kredyty", "kredytów"), "kredyt")

    def test_101_singular(self) -> None:
        """101 % 100 = 1, not in 11-19 range -> singular."""
        self.assertEqual(_plural_form_pl(101, "kredyt", "kredyty", "kredytów"), "kredyt")

    def test_111_genitive(self) -> None:
        """111 % 100 = 11, in 11-19 range -> genitive."""
        self.assertEqual(_plural_form_pl(111, "kredyt", "kredyty", "kredytów"), "kredytów")

    def test_121_singular(self) -> None:
        """121 % 100 = 21, n % 10 = 1, not in 11-19 -> singular."""
        self.assertEqual(_plural_form_pl(121, "kredyt", "kredyty", "kredytów"), "kredyt")

    def test_1011_genitive(self) -> None:
        """1011 % 100 = 11, in 11-19 range -> genitive."""
        self.assertEqual(_plural_form_pl(1011, "kredyt", "kredyty", "kredytów"), "kredytów")

    def test_2_few(self) -> None:
        self.assertEqual(_plural_form_pl(2, "kredyt", "kredyty", "kredytów"), "kredyty")

    def test_12_genitive_not_few(self) -> None:
        """12 ends in 2 but is in 11-19 range -> genitive, not nominative plural."""
        self.assertEqual(_plural_form_pl(12, "kredyt", "kredyty", "kredytów"), "kredytów")

    def test_22_few(self) -> None:
        """22 ends in 2, not in 11-19 -> nominative plural."""
        self.assertEqual(_plural_form_pl(22, "kredyt", "kredyty", "kredytów"), "kredyty")

    def test_5_genitive(self) -> None:
        self.assertEqual(_plural_form_pl(5, "kredyt", "kredyty", "kredytów"), "kredytów")

    def test_20_genitive(self) -> None:
        self.assertEqual(_plural_form_pl(20, "kredyt", "kredyty", "kredytów"), "kredytów")

    # ------------------------------------------------------------------
    # Integration: TTS output for credit amounts via raw_text
    # ------------------------------------------------------------------

    def test_tts_1_cr_uses_singular(self) -> None:
        """1 Cr -> 'jeden kredyt' (singular)."""
        text = prepare_tts("MSG.CASH_IN_ASSISTANT", {"raw_text": "Dane warte 1 Cr."}) or ""
        norm = _norm_ascii(text)
        self.assertIn("jeden", norm)
        self.assertIn("kredyt", norm)
        self.assertNotIn("kredytow", norm)

    def test_tts_11_cr_uses_genitive(self) -> None:
        """11 Cr -> 'jedenaście kredytów' (genitive), special 11-19 rule."""
        text = prepare_tts("MSG.CASH_IN_ASSISTANT", {"raw_text": "Dane warte 11 Cr."}) or ""
        norm = _norm_ascii(text)
        self.assertIn("jedenascie", norm)
        self.assertIn("kredytow", norm)

    def test_tts_21_cr_uses_singular(self) -> None:
        """21 Cr -> 'dwadzieścia jeden kredyt' (singular), not 'kredytów'."""
        text = prepare_tts("MSG.CASH_IN_ASSISTANT", {"raw_text": "Dane warte 21 Cr."}) or ""
        norm = _norm_ascii(text)
        self.assertIn("dwadziescia jeden", norm)
        self.assertIn("kredyt", norm)
        self.assertNotIn("kredytow", norm)

    def test_tts_111_cr_uses_genitive(self) -> None:
        """111 Cr -> genitive (111 % 100 = 11, in 11-19 range)."""
        text = prepare_tts("MSG.CASH_IN_ASSISTANT", {"raw_text": "Dane warte 111 Cr."}) or ""
        norm = _norm_ascii(text)
        self.assertIn("jedenascie", norm)
        self.assertIn("kredytow", norm)


if __name__ == "__main__":
    unittest.main()
