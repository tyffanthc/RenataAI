from __future__ import annotations

import unittest

from app.route_manager import route_manager
from app.state import app_state
from logic.events import navigation_events
from logic.trade import build_sell_assist_decision_space, handoff_sell_assist_to_route_intent


class F2QualityGatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_awareness = app_state.get_route_awareness_snapshot()
        self._saved_nav_route = dict(getattr(app_state, "nav_route", {}) or {})
        self._saved_current_system = str(getattr(app_state, "current_system", "") or "")
        self._saved_route = list(route_manager.route)
        self._saved_route_type = route_manager.route_type
        self._saved_route_index = int(route_manager.current_index)
        self._saved_milestones = list(getattr(app_state, "spansh_milestones", []) or [])
        self._saved_milestone_mode = getattr(app_state, "spansh_milestone_mode", None)

        route_manager.clear_route()
        app_state.clear_spansh_milestones(source="test.f2.quality.setup")
        app_state.clear_nav_route(source="test.f2.quality.setup")
        app_state.update_route_awareness(
            route_mode="idle",
            route_target="",
            route_progress_percent=0,
            next_system="",
            is_off_route=False,
            source="test.f2.quality.setup",
        )

    def tearDown(self) -> None:
        app_state.set_system(self._saved_current_system)
        app_state.update_route_awareness(
            route_mode=str(self._saved_awareness.get("route_mode") or "idle"),
            route_target=str(self._saved_awareness.get("route_target") or ""),
            route_progress_percent=int(self._saved_awareness.get("route_progress_percent") or 0),
            next_system=str(self._saved_awareness.get("next_system") or ""),
            is_off_route=bool(self._saved_awareness.get("is_off_route")),
            source="test.f2.quality.teardown",
        )

        if self._saved_nav_route.get("systems"):
            app_state.set_nav_route(
                endpoint=self._saved_nav_route.get("endpoint"),
                systems=self._saved_nav_route.get("systems"),
                source="test.f2.quality.teardown",
            )
        else:
            app_state.clear_nav_route(source="test.f2.quality.teardown")

        if self._saved_milestones:
            app_state.set_spansh_milestones(
                self._saved_milestones,
                mode=self._saved_milestone_mode,
                source="test.f2.quality.teardown",
            )
        else:
            app_state.clear_spansh_milestones(source="test.f2.quality.teardown")

        if self._saved_route:
            route_manager.set_route(self._saved_route, route_type=str(self._saved_route_type or "test"))
            route_manager.current_index = min(self._saved_route_index, len(self._saved_route))
        else:
            route_manager.clear_route()

    def test_sell_to_intent_to_awareness_cross_module(self) -> None:
        rows = [
            {
                "from_system": "SOL",
                "from_station": "Galileo",
                "to_system": "LHS 20",
                "to_station": "Ohm City",
                "total_profit": 1_300_000,
                "profit": 5500,
                "amount": 240,
                "distance_ly": 40.0,
                "jumps": 1,
                "source_status": "ONLINE_LIVE",
                "confidence": "high",
                "data_age_seconds": 600,
                "updated_ago": "10m",
            },
            {
                "from_system": "LHS 20",
                "from_station": "Ohm City",
                "to_system": "TAU CETI",
                "to_station": "Ortiz Moreno City",
                "total_profit": 1_000_000,
                "profit": 4100,
                "amount": 240,
                "distance_ly": 50.0,
                "jumps": 2,
                "source_status": "ONLINE_LIVE",
                "confidence": "high",
                "data_age_seconds": 900,
                "updated_ago": "15m",
            },
        ]

        decision = build_sell_assist_decision_space(rows, jump_range=48.0)
        options = decision.get("options") or []

        self.assertIn(len(options), {2, 3})
        self.assertEqual((decision.get("skip_action") or {}).get("label"), "Pomijam")

        selected = options[0]
        target = str(selected.get("to_system") or "").strip()
        self.assertTrue(target)

        handoff = handoff_sell_assist_to_route_intent(
            selected,
            set_route_intent=app_state.set_route_intent,
            source="test.f2.quality.handoff",
        )
        self.assertTrue(handoff.get("ok"))
        snap_intent = app_state.get_route_awareness_snapshot()
        self.assertEqual(str(snap_intent.get("route_mode")), "intent")
        self.assertEqual(str(snap_intent.get("route_target") or ""), target)
        self.assertFalse(bool(snap_intent.get("is_off_route")))

        app_state.set_system("SOL")
        navigation_events.handle_navroute_update(
            {
                "event": "NavRoute",
                "EndSystem": target,
                "Route": [
                    {"StarSystem": "SOL"},
                    {"StarSystem": target},
                ],
            },
            gui_ref=None,
        )

        snap_awareness = app_state.get_route_awareness_snapshot()
        self.assertEqual(str(snap_awareness.get("route_mode")), "awareness")
        self.assertEqual(str(snap_awareness.get("route_target") or ""), target)
        self.assertFalse(bool(snap_awareness.get("is_off_route")))


if __name__ == "__main__":
    unittest.main()
