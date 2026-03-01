from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F32CashInPayloadTargetSystemReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)

        app_state.current_system = "F32_PAYLOAD_ORIGIN"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

    def test_payload_exposes_target_system_name_when_top_target_is_real(self) -> None:
        payload = {
            "system": "F32_PAYLOAD_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 4_000_000.0,
            "cash_in_session_estimated": 12_000_000.0,
            "service": "uc",
            "station_candidates": [
                {
                    "name": "F32 Ready Port",
                    "system_name": "F32_TARGET_SYSTEM",
                    "type": "station",
                    "services": {"has_uc": True, "has_vista": False},
                    "distance_ly": 7.0,
                    "distance_ls": 900.0,
                    "source": "EDSM",
                }
            ],
        }
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        self.assertEqual(str(structured.get("target_system_name") or ""), "F32_TARGET_SYSTEM")
        self.assertEqual(str(ctx.get("target_system_name") or ""), "F32_TARGET_SYSTEM")

    def test_payload_target_system_name_empty_when_no_real_target(self) -> None:
        payload = {
            "system": "F32_PAYLOAD_ORIGIN",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 1_000_000.0,
            "cash_in_session_estimated": 3_000_000.0,
            "service": "uc",
            # Brak UC => fallback legacy options bez targetu real.
            "station_candidates": [
                {
                    "name": "F32 No UC Port",
                    "system_name": "F32_NO_UC_SYS",
                    "type": "station",
                    "services": {"has_uc": False, "has_vista": True},
                    "distance_ly": 5.0,
                    "source": "OFFLINE_INDEX",
                }
            ],
        }
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        self.assertEqual(str(structured.get("target_system_name") or ""), "")
        self.assertEqual(str(ctx.get("target_system_name") or ""), "")


if __name__ == "__main__":
    unittest.main()

