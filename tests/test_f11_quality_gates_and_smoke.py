from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
from app.state import app_state
from logic.exit_summary import ExitSummaryData
from logic.events import cash_in_assistant


class F11QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._orig_settings = dict(config.config._settings)
        app_state.current_system = "F11_QUALITY_SYSTEM"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        config.config._settings["cash_in.show_tariff_meta"] = True
        config.config._settings["cash_in.startjump_callout_enabled"] = True
        config.config._settings["cash_in.startjump_callout_cooldown_sec"] = 35.0

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        config.config._settings = self._orig_settings

    @staticmethod
    def _summary_payload() -> dict:
        return {
            "system": "F11_QUALITY_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 6_500_000.0,
            "cash_in_session_estimated": 18_900_000.0,
            "confidence": "high",
            "service": "uc",
            "tariff_percent": 8.5,
            "freshness_ts": "2026-02-22T10:30:00Z",
            "station_candidates": [
                {
                    "name": "Ray Gateway",
                    "system_name": "F11_QUALITY_SYSTEM",
                    "type": "station",
                    "services": ["Universal Cartographics"],
                    "distance_ly": 11.0,
                    "distance_ls": 1_200.0,
                    "source": "EDSM",
                },
                {
                    "name": "FC K7Q-AAA",
                    "system_name": "F11_QUALITY_SYSTEM",
                    "type": "fleet_carrier",
                    "services": ["Universal Cartographics", "Vista Genomics"],
                    "distance_ly": 8.0,
                    "distance_ls": 1_700.0,
                    "source": "SPANSH",
                },
            ],
        }

    def test_f11_gate_payload_ui_contract_shape(self) -> None:
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._summary_payload(),
            )

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        self.assertGreaterEqual(len(options), 2)
        self.assertLessEqual(len(options), 4)
        for option in options:
            self.assertEqual(str(option.get("ui_contract_version") or ""), "F11_UI_V1")
            ui = dict(option.get("ui_contract") or {})
            self.assertIn(
                str(ui.get("label") or ""),
                {
                    "SAFE",
                    "FAST",
                    "SECURE",
                    "NEAREST",
                    "SECURE_PORT",
                    "CARRIER_FRIENDLY",
                    "EXPRESS",
                    "PLANETARY_VISTA",
                },
            )
            self.assertTrue(isinstance(ui.get("target"), dict))
            self.assertTrue(isinstance(ui.get("payout"), dict))
            self.assertTrue(isinstance(ui.get("eta"), dict))
            self.assertTrue(isinstance(ui.get("risk"), dict))
            self.assertEqual(list(ui.get("actions") or []), ["set_route", "copy_next_hop", "skip"])

    def test_f11_gate_route_handoff_requires_user_action(self) -> None:
        calls: list[tuple[str, str]] = []

        def _setter(target: str, *, source: str = "intent") -> dict:
            calls.append((target, source))
            return {"route_mode": "intent", "route_target": target}

        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=self._summary_payload(),
            )
        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        first_option = dict((structured.get("options") or [])[0] or {})

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            first_option,
            set_route_intent=_setter,
            source="test.f11.quality.intent",
            allow_auto_route=False,
        )
        self.assertTrue(bool(out.get("ok")))
        self.assertTrue(bool(str(out.get("target_system") or "").strip()))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "test.f11.quality.intent")

        with self.assertRaises(ValueError):
            cash_in_assistant.handoff_cash_in_to_route_intent(
                first_option,
                set_route_intent=_setter,
                source="test.f11.quality.intent",
                allow_auto_route=True,
            )

    def test_f11_gate_startjump_confidence_and_antispam(self) -> None:
        with (
            patch.object(
                app_state.exit_summary,
                "build_summary_data",
                return_value=ExitSummaryData(system_name="F11_QUALITY_SYSTEM", total_value=4_400_000.0),
            ),
            patch.object(
                app_state,
                "system_value_engine",
                new=SimpleNamespace(calculate_totals=lambda: {"total": 21_700_000.0}),
            ),
            patch(
                "logic.events.cash_in_assistant.DEBOUNCER.is_allowed",
                side_effect=[True, False],
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            first = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"},
            )
            second = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"},
            )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(emit_mock.call_count, 1)
        kwargs = emit_mock.call_args.kwargs
        self.assertEqual(kwargs.get("message_id"), "MSG.CASH_IN_STARTJUMP")
        ctx = dict(kwargs.get("context") or {})
        self.assertEqual(str(ctx.get("confidence") or ""), "high")
        self.assertIn("Cr", str(ctx.get("raw_text") or ""))


if __name__ == "__main__":
    unittest.main()
