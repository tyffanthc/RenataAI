from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F33CashInClipboardAutoTargetAndTtsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._saved_needs_large_pad = bool(getattr(app_state, "needs_large_pad", False))

        app_state.current_system = "F33_CLIP_ORIGIN"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        app_state.set_needs_large_pad(False, source="test.f33.clip.setup")

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False
        config.config._settings["cash_in.clipboard_auto_target_enabled"] = True
        config.config._settings["cash_in.ship_size_auto_lock_enabled"] = True

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        app_state.set_needs_large_pad(self._saved_needs_large_pad, source="test.f33.clip.teardown")

    def test_auto_copy_target_system_and_secure_clipboard_tts(self) -> None:
        payload = {
            "system": "F33_CLIP_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 5_000_000.0,
            "cash_in_session_estimated": 14_000_000.0,
            "service": "uc",
            "station_candidates": [
                {
                    "name": "F33 Secure Port",
                    "system_name": "F33_SECURE_SYS",
                    "type": "station",
                    "security": "high",
                    "services": {"has_uc": True, "has_vista": False},
                    "distance_ly": 9.0,
                    "distance_ls": 1200.0,
                    "source": "EDSM",
                }
            ],
        }

        with (
            patch("logic.events.cash_in_assistant.try_copy_to_clipboard", return_value={"ok": True}) as copy_mock,
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        copy_mock.assert_called_once_with(
            "F33_SECURE_SYS",
            context="cash_in.assistant.target_system",
        )
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        raw_text = str(ctx.get("raw_text") or "").lower()
        structured = dict(ctx.get("cash_in_payload") or {})

        self.assertIn("bezpieczny port", raw_text)
        self.assertIn("system w schowku", raw_text)
        self.assertIn("f33_secure_sys", raw_text)
        self.assertEqual(str(ctx.get("target_system_name") or ""), "F33_SECURE_SYS")
        self.assertEqual(str(ctx.get("target_station_name") or ""), "F33 Secure Port")
        self.assertEqual(str(structured.get("target_system_name") or ""), "F33_SECURE_SYS")
        self.assertEqual(str(structured.get("target_station_name") or ""), "F33 Secure Port")
        self.assertTrue(bool(ctx.get("clipboard_target_system_attempted")))
        self.assertTrue(bool(ctx.get("clipboard_target_system_copied")))
        self.assertEqual(str(ctx.get("clipboard_target_system_reason") or ""), "ok")

    def test_tts_reports_outpost_rejected_by_ship_constraints(self) -> None:
        app_state.set_needs_large_pad(True, source="test.f33.clip.large_ship")
        payload = {
            "system": "F33_CLIP_ORIGIN",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 2_500_000.0,
            "cash_in_session_estimated": 7_000_000.0,
            "service": "uc",
            "station_candidates": [
                {
                    "name": "F33 Near Outpost",
                    "system_name": "F33_OUTPOST_SYS",
                    "type": "outpost",
                    "security": "high",
                    "max_landing_pad_size": "M",
                    "services": {"has_uc": True, "has_vista": False},
                    "distance_ly": 3.0,
                    "distance_ls": 900.0,
                    "source": "OFFLINE_INDEX",
                },
                {
                    "name": "F33 Large Secure Port",
                    "system_name": "F33_LARGE_SYS",
                    "type": "station",
                    "security": "high",
                    "max_landing_pad_size": "L",
                    "services": {"has_uc": True, "has_vista": False},
                    "distance_ly": 11.0,
                    "distance_ls": 1400.0,
                    "source": "EDSM",
                },
            ],
        }

        with (
            patch("logic.events.cash_in_assistant.try_copy_to_clipboard", return_value={"ok": True}),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        raw_text = str(ctx.get("raw_text") or "").lower()
        structured = dict(ctx.get("cash_in_payload") or {})
        edge_meta = dict(structured.get("edge_case_meta") or {})
        reasons = [str(item) for item in (edge_meta.get("reasons") or [])]

        self.assertIn("outpost", raw_text)
        self.assertIn("ograniczenia statku", raw_text)
        self.assertIn("system w schowku", raw_text)
        self.assertIn("outpost_rejected_by_ship_constraints", reasons)
        self.assertTrue(bool(ctx.get("clipboard_target_system_copied")))


if __name__ == "__main__":
    unittest.main()

