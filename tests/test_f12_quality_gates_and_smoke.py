from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F12QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._orig_settings = dict(config.config._settings)

        app_state.current_system = "F12_QUALITY_SYSTEM"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

        config.config._settings["cash_in.station_candidates_lookup_enabled"] = True
        config.config._settings["cash_in.station_candidates_limit"] = 24
        config.config._settings["cash_in.cross_system_discovery_enabled"] = True
        config.config._settings["cash_in.cross_system_radius_ly"] = 120.0
        config.config._settings["cash_in.cross_system_max_systems"] = 8
        config.config._settings["features.providers.edsm_enabled"] = True
        config.config._settings["features.providers.system_lookup_online"] = True
        config.config._settings["features.trade.station_lookup_online"] = True

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        config.config._settings = self._orig_settings

    @staticmethod
    def _base_payload() -> dict:
        return {
            "system": "F12_QUALITY_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 7_200_000.0,
            "cash_in_session_estimated": 26_000_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_f12_quality_gate_cross_system_real_target_handoff(self) -> None:
        payload = self._base_payload()
        local_no_service = [
            {
                "name": "Local Non-UC",
                "system_name": "F12_QUALITY_SYSTEM",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 1.0,
                "source": "EDSM",
            }
        ]
        cross_candidates = [
            {
                "name": "Remote UC Hub",
                "system_name": "F12_REMOTE_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 34.0,
                "distance_ls": 1300.0,
                "source": "EDSM",
            }
        ]
        cross_meta = {"systems_requested": 4, "systems_with_candidates": 1}

        with (
            patch(
                "logic.events.cash_in_assistant.station_candidates_for_system_from_providers",
                return_value=local_no_service,
            ),
            patch(
                "logic.events.cash_in_assistant.station_candidates_cross_system_from_providers",
                return_value=(cross_candidates, cross_meta),
            ),
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        station_meta = dict(structured.get("station_candidates_meta") or {})
        self.assertEqual(str(station_meta.get("cross_system_lookup_status") or ""), "cross_system")
        self.assertEqual(int(station_meta.get("cross_system_systems_requested") or 0), 4)

        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        self.assertGreaterEqual(len(options), 1)
        first = dict(options[0])
        target = cash_in_assistant.resolve_cash_in_option_target(first)
        self.assertTrue(bool(target.get("target_is_real")))

        handoff = cash_in_assistant.handoff_cash_in_to_route_intent(
            first,
            set_route_intent=lambda target, **_kwargs: {"route_target": target},
            allow_auto_route=False,
        )
        self.assertTrue(bool(handoff.get("ok")))
        self.assertEqual(str(handoff.get("target_system") or ""), "F12_REMOTE_SYSTEM")
        self.assertEqual(str(handoff.get("target_station") or ""), "Remote UC Hub")

    def test_f12_quality_gate_no_service_candidates_blocks_route_handoff(self) -> None:
        payload = self._base_payload()
        payload["station_candidates"] = [
            {
                "name": "Only Vista Candidate",
                "system_name": "F12_QUALITY_SYSTEM",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 8.0,
                "source": "EDSM",
            }
        ]
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False

        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
        self.assertTrue(ok)

        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        options = [dict(item) for item in (structured.get("options") or []) if isinstance(item, dict)]
        self.assertGreaterEqual(len(options), 1)
        first = dict(options[0])
        target = cash_in_assistant.resolve_cash_in_option_target(first)
        self.assertFalse(bool(target.get("target_is_real")))

        handoff = cash_in_assistant.handoff_cash_in_to_route_intent(
            first,
            set_route_intent=lambda *_args, **_kwargs: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(handoff.get("ok")))
        self.assertEqual(str(handoff.get("reason") or ""), "target_missing_system")

    def test_f12_quality_gate_placeholder_target_rejected(self) -> None:
        option = {
            "profile": "FAST",
            "target": {
                "system_name": "F12_REMOTE_SYSTEM",
                "name": "Remote UC Hub",
            },
            "fallback_target_attached": True,
        }
        handoff = cash_in_assistant.handoff_cash_in_to_route_intent(
            option,
            set_route_intent=lambda *_args, **_kwargs: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(handoff.get("ok")))
        self.assertEqual(str(handoff.get("reason") or ""), "target_not_real")


if __name__ == "__main__":
    unittest.main()

