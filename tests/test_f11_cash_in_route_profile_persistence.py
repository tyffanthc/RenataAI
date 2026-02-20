from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F11CashInRouteProfilePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_awareness = app_state.get_route_awareness_snapshot()
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._orig_settings = dict(config.config._settings)

        app_state.current_system = "F11_ROUTE_PROFILE_SYSTEM"
        app_state.current_station = ""
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        config.config._settings["cash_in.persist_route_profile_to_route_state"] = False
        app_state.update_route_awareness(
            route_mode="idle",
            route_target="",
            route_progress_percent=0,
            next_system="",
            route_profile="",
            is_off_route=False,
            source="test.f11.route_profile.setup",
        )

    def tearDown(self) -> None:
        app_state.update_route_awareness(
            route_mode=str(self._saved_awareness.get("route_mode") or "idle"),
            route_target=str(self._saved_awareness.get("route_target") or ""),
            route_progress_percent=int(self._saved_awareness.get("route_progress_percent") or 0),
            next_system=str(self._saved_awareness.get("next_system") or ""),
            route_profile=str(self._saved_awareness.get("route_profile") or ""),
            is_off_route=bool(self._saved_awareness.get("is_off_route")),
            source="test.f11.route_profile.teardown",
        )
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        config.config._settings = self._orig_settings

    def test_handoff_persists_profile_when_enabled_and_setter_supports_route_profile(self) -> None:
        calls: list[tuple[str, str, str | None]] = []

        def _setter(target: str, *, source: str = "intent", route_profile: str | None = None) -> dict:
            calls.append((target, source, route_profile))
            return {
                "route_mode": "intent",
                "route_target": target,
                "route_profile": route_profile,
            }

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            {
                "profile": "FAST",
                "target": {"system_name": "Luyten's Star", "name": "Ashby City"},
            },
            set_route_intent=_setter,
            source="test.f11.persist.intent",
            allow_auto_route=False,
            persist_route_profile=True,
        )
        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(str(out.get("route_profile") or ""), "FAST_NEUTRON")
        self.assertTrue(bool(out.get("route_profile_persisted")))
        self.assertEqual(calls, [("Luyten's Star", "test.f11.persist.intent", "FAST_NEUTRON")])

    def test_handoff_without_persistence_keeps_legacy_setter_contract(self) -> None:
        calls: list[tuple[str, str]] = []

        def _setter(target: str, *, source: str = "intent") -> dict:
            calls.append((target, source))
            return {"route_mode": "intent", "route_target": target}

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            {
                "profile": "SECURE",
                "target": {"system_name": "Sirius", "name": "Patterson Enterprise"},
            },
            set_route_intent=_setter,
            source="test.f11.persist.legacy",
            allow_auto_route=False,
            persist_route_profile=False,
        )
        self.assertTrue(bool(out.get("ok")))
        self.assertFalse(bool(out.get("route_profile_persisted")))
        self.assertEqual(calls, [("Sirius", "test.f11.persist.legacy")])

    def test_persist_profile_helper_updates_route_state_only_when_enabled(self) -> None:
        option = {
            "profile": "SECURE",
            "target": {"system_name": "Ross 154", "name": "Miller Depot"},
        }
        disabled = cash_in_assistant.persist_cash_in_route_profile(
            option,
            update_route_awareness=app_state.update_route_awareness,
            source="test.f11.persist.disabled",
            enabled=False,
        )
        self.assertFalse(bool(disabled.get("ok")))
        self.assertEqual(str(disabled.get("reason") or ""), "persistence_disabled")
        self.assertEqual(str(app_state.get_route_awareness_snapshot().get("route_profile") or ""), "")

        enabled = cash_in_assistant.persist_cash_in_route_profile(
            option,
            update_route_awareness=app_state.update_route_awareness,
            source="test.f11.persist.enabled",
            enabled=True,
        )
        self.assertTrue(bool(enabled.get("ok")))
        self.assertEqual(str(enabled.get("route_profile") or ""), "SECURE")
        self.assertEqual(
            str(app_state.get_route_awareness_snapshot().get("route_profile") or ""),
            "SECURE",
        )

    def test_trigger_cash_in_assistant_does_not_persist_route_profile_implicitly(self) -> None:
        config.config._settings["cash_in.persist_route_profile_to_route_state"] = True
        payload = {
            "system": "F11_ROUTE_PROFILE_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 4_100_000.0,
            "cash_in_session_estimated": 14_400_000.0,
            "station_candidates": [
                {
                    "name": "Ray Gateway",
                    "system_name": "F11_ROUTE_PROFILE_SYSTEM",
                    "type": "station",
                    "services": {"has_uc": True, "has_vista": False},
                }
            ],
        }
        with patch("logic.events.cash_in_assistant.emit_insight"):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
        self.assertTrue(ok)
        self.assertEqual(str(app_state.get_route_awareness_snapshot().get("route_profile") or ""), "")


if __name__ == "__main__":
    unittest.main()
