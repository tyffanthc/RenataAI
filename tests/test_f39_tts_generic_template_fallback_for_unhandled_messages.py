from __future__ import annotations

import unittest

from logic.tts.text_preprocessor import prepare_tts


class F39TtsGenericTemplateFallbackForUnhandledMessagesTests(unittest.TestCase):
    def test_prepare_tts_raw_text_first_message_falls_back_to_template_when_raw_text_missing(self) -> None:
        # raw_text_first=True messages should still speak via template fallback
        # when emitters don't provide raw_text in context.
        text = prepare_tts("MSG.ELW_DETECTED", {})
        self.assertIsInstance(text, str)
        self.assertTrue(text)
        self.assertIn("planet", text.lower())
        self.assertTrue(text.endswith("."))

    def test_prepare_tts_returns_text_for_template_only_message_ids(self) -> None:
        # These message IDs are present in templates and allowed list, but do not
        # have dedicated branches in prepare_tts().
        message_ids = [
            "MSG.BIO_SIGNALS_HIGH",
            "MSG.DSS_TARGET_HINT",
            "MSG.DSS_COMPLETED",
            "MSG.DSS_PROGRESS",
            "MSG.EXOBIO_SAMPLE_LOGGED",
            "MSG.EXOBIO_NEW_ENTRY",
            "MSG.EXOBIO_RANGE_READY",
            "MSG.FIRST_MAPPED",
            "MSG.SMUGGLER_ILLEGAL_CARGO",
            "MSG.TERRAFORMABLE_DETECTED",
            "MSG.TRADE_JACKPOT",
            "MSG.WW_DETECTED",
        ]
        for message_id in message_ids:
            with self.subTest(message_id=message_id):
                text = prepare_tts(message_id, {})
                self.assertIsInstance(text, str)
                self.assertTrue(text)
                self.assertTrue(text.endswith("."))


if __name__ == "__main__":
    unittest.main()
