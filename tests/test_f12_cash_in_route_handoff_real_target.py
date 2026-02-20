from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F12CashInRouteHandoffRealTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.cross_system_discovery_enabled"] = True

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

    def test_handoff_rejects_target_without_station_name(self) -> None:
        option = {
            "profile": "SAFE",
            "target": {"system_name": "LHS 20"},
        }
        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            option,
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(out.get("ok")))
        self.assertEqual(str(out.get("reason") or ""), "target_missing_station")

    def test_handoff_rejects_placeholder_target_even_if_system_and_station_exist(self) -> None:
        option = {
            "profile": "FAST",
            "target": {"system_name": "LHS 20", "name": "Ray Gateway"},
            "fallback_target_attached": True,
        }
        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            option,
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(out.get("ok")))
        self.assertEqual(str(out.get("reason") or ""), "target_not_real")

    def test_resolve_marks_real_target_for_ranked_option(self) -> None:
        option = {
            "profile": "FAST",
            "target": {"system_name": "LHS 20", "name": "Ray Gateway"},
        }
        target = cash_in_assistant.resolve_cash_in_option_target(option)
        self.assertTrue(bool(target.get("target_is_real")))
        self.assertEqual(str(target.get("target_quality") or ""), "real_target")

    def test_no_service_candidates_do_not_get_placeholder_target_in_runtime(self) -> None:
        payload = {
            "system": "F12_HOFFMAN",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 1_500_000.0,
            "cash_in_session_estimated": 6_200_000.0,
            "service": "uc",
            "station_candidates": [
                {
                    "name": "Candidate Without UC",
                    "system_name": "F12_HOFFMAN",
                    "type": "station",
                    "services": {"has_uc": False, "has_vista": True},
                    "distance_ly": 3.0,
                    "source": "EDSM",
                }
            ],
        }
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        self.assertGreaterEqual(len(options), 1)
        first = dict(options[0])
        self.assertFalse(bool(first.get("fallback_target_attached")))
        self.assertEqual(str(first.get("target_system") or ""), "")
        self.assertEqual(str((first.get("target") or {}).get("system_name") or ""), "")

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            first,
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(out.get("ok")))
        self.assertEqual(str(out.get("reason") or ""), "target_missing_system")


if __name__ == "__main__":
    unittest.main()

