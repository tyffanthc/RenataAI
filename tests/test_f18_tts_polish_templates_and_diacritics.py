from __future__ import annotations

import unicodedata
from pathlib import Path
import unittest

from logic.tts.message_templates import allowed_message_ids, template_for_message
from logic.tts.text_preprocessor import ALLOWED_MESSAGES, _repair_polish_text, prepare_tts


class F18TtsPolishTemplatesAndDiacriticsTests(unittest.TestCase):
    def test_registry_and_preprocessor_allowed_messages_are_consistent(self) -> None:
        self.assertSetEqual(set(ALLOWED_MESSAGES), set(allowed_message_ids()))

    def test_prepare_tts_repairs_ascii_polish_forms_in_raw_text(self) -> None:
        high_g = prepare_tts(
            "MSG.HIGH_G_WARNING",
            {"raw_text": "Wykryto wysokie przeciazenie grawitacyjne. Ogranicz opadanie."},
        ) or ""
        stale = prepare_tts(
            "MSG.TRADE_DATA_STALE",
            {"raw_text": "Dane rynkowe sa nieswieze. Traktuj wynik orientacyjnie."},
        ) or ""
        runtime = prepare_tts(
            "MSG.RUNTIME_CRITICAL",
            {"raw_text": "Blad krytyczny runtime. Sprawdz panel statusu."},
        ) or ""

        self.assertIn("przeciążenie", high_g.lower())
        self.assertIn("nieświeże", stale.lower())
        self.assertIn("błąd", runtime.lower())

    def test_key_templates_keep_polish_diacritics(self) -> None:
        expectations = {
            "MSG.NEXT_HOP": "Następny",
            "MSG.HIGH_G_WARNING": "przeciążenie",
            "MSG.TRADE_DATA_STALE": "nieświeże",
            "MSG.RUNTIME_CRITICAL": "błąd",
            "MSG.FSS_PROGRESS_50": "Połowa",
        }
        for message_id, expected_fragment in expectations.items():
            template = template_for_message(message_id)
            self.assertIn(expected_fragment, template, f"Template {message_id} missing '{expected_fragment}'")

    def test_no_known_mojibake_tokens_in_primary_tts_emitters(self) -> None:
        files = [
            Path("app/main_loop.py"),
            Path("logic/events/high_g_warning.py"),
            Path("logic/tts/message_templates.py"),
        ]
        bad_tokens = ("Ä…", "Å‚", "Ã³", "Ăł", "Ĺ‚", "â€", "Â ")
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in bad_tokens:
                self.assertNotIn(token, text, f"Mojibake token {token!r} found in {path}")

    def test_prepare_tts_preserves_informational_neutral_tone_after_normalization(self) -> None:
        samples = [
            prepare_tts("MSG.NEXT_HOP", {"system": "SOL"}) or "",
            prepare_tts("MSG.TRADE_DATA_STALE", {"raw_text": "Dane rynkowe sa nieswieze. Traktuj wynik orientacyjnie."}) or "",
            prepare_tts("MSG.RUNTIME_CRITICAL", {"raw_text": "Blad krytyczny runtime. Sprawdz panel."}) or "",
        ]
        forbidden = ("musisz", "natychmiast", "jedyna opcja")
        for line in samples:
            normalized = unicodedata.normalize("NFKD", line.lower()).encode("ascii", "ignore").decode("ascii")
            for snippet in forbidden:
                self.assertNotIn(snippet, normalized)

    def test_repair_polish_text_is_idempotent_for_already_correct_diacritics(self) -> None:
        samples = [
            "ł",
            "Zażółć gęślą jaźń",
            "Błąd krytyczny runtime.",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                once = _repair_polish_text(sample)
                twice = _repair_polish_text(once)
                self.assertEqual(once, sample)
                self.assertEqual(twice, sample)


if __name__ == "__main__":
    unittest.main()
