from __future__ import annotations

import unittest
from unittest.mock import patch

from app.route_manager import route_manager
from app.state import app_state
from logic.events import cash_in_assistant


class F11CashInRouteHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_awareness = app_state.get_route_awareness_snapshot()
        self._saved_route = list(getattr(route_manager, "route", []) or [])
        self._saved_route_type = getattr(route_manager, "route_type", None)
        self._saved_route_index = int(getattr(route_manager, "current_index", 0) or 0)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

    def tearDown(self) -> None:
        app_state.update_route_awareness(
            route_mode=str(self._saved_awareness.get("route_mode") or "idle"),
            route_target=str(self._saved_awareness.get("route_target") or ""),
            route_progress_percent=int(self._saved_awareness.get("route_progress_percent") or 0),
            next_system=str(self._saved_awareness.get("next_system") or ""),
            is_off_route=bool(self._saved_awareness.get("is_off_route")),
            source="test.cash_in_handoff.teardown",
        )
        if self._saved_route_type is None and not self._saved_route:
            route_manager.clear_route()
        else:
            route_manager.set_route(self._saved_route, self._saved_route_type or "trade")
            route_manager.current_index = int(self._saved_route_index)
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

    def test_handoff_sets_intent_from_selected_option_target(self) -> None:
        calls: list[tuple[str, str]] = []

        def _setter(target: str, *, source: str = "intent") -> dict:
            calls.append((target, source))
            return {"route_mode": "intent", "route_target": target}

        option = {
            "profile": "FAST",
            "target": {
                "system_name": "Lalande 5761",
                "name": "Pook Hub",
            },
        }
        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            option,
            set_route_intent=_setter,
            source="test.cash_in.intent",
            allow_auto_route=False,
        )

        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(out.get("target_system"), "Lalande 5761")
        self.assertEqual(out.get("target_station"), "Pook Hub")
        self.assertEqual(out.get("route_profile"), "FAST_NEUTRON")
        self.assertEqual(calls, [("Lalande 5761", "test.cash_in.intent")])

    def test_handoff_rejects_auto_route_flag(self) -> None:
        with self.assertRaises(ValueError):
            cash_in_assistant.handoff_cash_in_to_route_intent(
                {"target": {"system_name": "LHS 20"}},
                set_route_intent=lambda *_a, **_k: {},
                allow_auto_route=True,
            )

    def test_handoff_without_target_returns_error(self) -> None:
        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            {"label": "SAFE"},
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(out.get("ok")))
        self.assertEqual(out.get("reason"), "target_missing_system")

    def test_handoff_does_not_mutate_route_manager(self) -> None:
        route_manager.set_route(["A", "B", "C"], "trade")
        route_manager.current_index = 1
        before_route = list(route_manager.route)
        before_type = route_manager.route_type
        before_idx = route_manager.current_index

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            {
                "profile": "SAFE",
                "target": {"system_name": "Barnard's Star", "name": "Miller Depot"},
            },
            set_route_intent=app_state.set_route_intent,
            source="test.cash_in.handoff",
            allow_auto_route=False,
        )
        self.assertTrue(bool(out.get("ok")))
        snap = app_state.get_route_awareness_snapshot()
        self.assertEqual(str(snap.get("route_mode")), "intent")
        self.assertEqual(str(snap.get("route_target")), "Barnard's Star")
        self.assertEqual(route_manager.route, before_route)
        self.assertEqual(route_manager.route_type, before_type)
        self.assertEqual(route_manager.current_index, before_idx)

    def test_trigger_cash_in_assistant_does_not_set_route_intent_implicitly(self) -> None:
        app_state.update_route_awareness(
            route_mode="idle",
            route_target="",
            route_progress_percent=0,
            next_system="",
            is_off_route=False,
            source="test.cash_in.auto_guard.reset",
        )
        payload = {
            "system": "F11_HOFFMAN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 4_000_000.0,
            "cash_in_session_estimated": 12_000_000.0,
            "station_candidates": [
                {
                    "name": "Ray Gateway",
                    "system_name": "Diagaundri",
                    "type": "station",
                    "services": {"has_uc": True, "has_vista": False},
                }
            ],
        }
        with patch("logic.events.cash_in_assistant.emit_insight"):
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)
        self.assertTrue(ok)
        snap = app_state.get_route_awareness_snapshot()
        self.assertEqual(str(snap.get("route_mode") or ""), "idle")
        self.assertEqual(str(snap.get("route_target") or ""), "")

    def test_fallback_legacy_options_do_not_attach_placeholder_target(self) -> None:
        payload = {
            "system": "F11_HOFFMAN",
            "cash_in_signal": "sredni",
            "cash_in_system_estimated": 1_200_000.0,
            "cash_in_session_estimated": 5_500_000.0,
            # Brak service match dla UC => fallback legacy options.
            "station_candidates": [
                {
                    "name": "Fallback Hub",
                    "system_name": "Diagaundri",
                    "type": "station",
                    "services": {"has_uc": False, "has_vista": False},
                    "distance_ly": 7.0,
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
        target = dict(first.get("target") or {})
        self.assertEqual(str(target.get("system_name") or ""), "")
        self.assertEqual(str(target.get("name") or ""), "")

        out = cash_in_assistant.handoff_cash_in_to_route_intent(
            first,
            set_route_intent=app_state.set_route_intent,
            source="test.cash_in.fallback_target",
            allow_auto_route=False,
        )
        self.assertFalse(bool(out.get("ok")))
        self.assertEqual(str(out.get("reason") or ""), "target_missing_system")


if __name__ == "__main__":
    unittest.main()
