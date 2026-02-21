from __future__ import annotations

import unicodedata
import unittest
from unittest.mock import patch

import config
from logic.event_insight_mapping import get_insight_class, get_tts_policy_spec
from logic.events import high_g_warning
from logic.tts.text_preprocessor import prepare_tts


class F17TtsOperationalCalloutsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        config.config._settings["high_g_warning"] = True
        config.config._settings["high_g_warning_threshold_g"] = 2.0

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings

    def test_high_g_warning_emits_for_high_scan_gravity(self) -> None:
        event = {
            "event": "Scan",
            "BodyName": "F17 HighG Body",
            "StarSystem": "F17_SYS",
            "SurfaceGravity": 24.6,
        }
        with patch("logic.events.high_g_warning.emit_insight") as emit_mock:
            ok = high_g_warning.handle_journal_event(event, gui_ref=None)
        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.HIGH_G_WARNING")
        ctx = dict(kwargs.get("context") or {})
        self.assertIn("wysokie przeciazenie grawitacyjne", str(ctx.get("raw_text") or "").lower())

    def test_high_g_warning_ignored_for_low_gravity(self) -> None:
        event = {
            "event": "Scan",
            "BodyName": "F17 LowG Body",
            "StarSystem": "F17_SYS",
            "SurfaceGravity": 9.81,
        }
        with patch("logic.events.high_g_warning.emit_insight") as emit_mock:
            ok = high_g_warning.handle_journal_event(event, gui_ref=None)
        self.assertFalse(ok)
        self.assertEqual(emit_mock.call_count, 0)

    def test_new_message_ids_have_mapping_and_tts_policy(self) -> None:
        ids = [
            "MSG.HIGH_G_WARNING",
            "MSG.TRADE_DATA_STALE",
            "MSG.PPM_SET_TARGET",
            "MSG.PPM_PIN_ACTION",
            "MSG.PPM_COPY_SYSTEM",
            "MSG.RUNTIME_CRITICAL",
        ]
        for message_id in ids:
            self.assertIsNotNone(get_insight_class(message_id), f"Missing insight mapping for {message_id}")
            policy = get_tts_policy_spec(message_id)
            self.assertEqual(policy.message_id, message_id)
            self.assertNotEqual(policy.intent, "silent")

    def test_prepare_tts_for_new_messages(self) -> None:
        high_g = prepare_tts("MSG.HIGH_G_WARNING", {"raw_text": "Wykryto wysokie przeciazenie grawitacyjne."}) or ""
        stale = prepare_tts("MSG.TRADE_DATA_STALE", {"raw_text": "Dane rynkowe sa nieswieze. Traktuj wynik orientacyjnie."}) or ""
        ppm = prepare_tts("MSG.PPM_SET_TARGET", {"target": "LHS 20"}) or ""
        runtime = prepare_tts("MSG.RUNTIME_CRITICAL", {"raw_text": "Blad krytyczny runtime."}) or ""

        norm_high_g = unicodedata.normalize("NFKD", high_g.lower()).encode("ascii", "ignore").decode("ascii")
        norm_stale = unicodedata.normalize("NFKD", stale.lower()).encode("ascii", "ignore").decode("ascii")
        self.assertIn("wysokie przeciazenie", norm_high_g)
        self.assertIn("nieswieze", norm_stale)
        self.assertTrue(ppm.strip())
        self.assertIn("krytyczny", runtime.lower())


if __name__ == "__main__":
    unittest.main()
