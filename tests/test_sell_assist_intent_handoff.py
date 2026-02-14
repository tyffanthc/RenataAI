import unittest

from app.route_manager import route_manager
from app.state import app_state
from logic.trade import handoff_sell_assist_to_route_intent


class SellAssistIntentHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_awareness = app_state.get_route_awareness_snapshot()
        self._saved_route = list(getattr(route_manager, "route", []) or [])
        self._saved_route_type = getattr(route_manager, "route_type", None)
        self._saved_route_index = int(getattr(route_manager, "current_index", 0) or 0)

    def tearDown(self) -> None:
        app_state.update_route_awareness(
            route_mode=str(self._saved_awareness.get("route_mode") or "idle"),
            route_target=str(self._saved_awareness.get("route_target") or ""),
            route_progress_percent=int(self._saved_awareness.get("route_progress_percent") or 0),
            next_system=str(self._saved_awareness.get("next_system") or ""),
            is_off_route=bool(self._saved_awareness.get("is_off_route")),
            source="test.sell_assist_handoff.teardown",
        )
        if self._saved_route_type is None and not self._saved_route:
            route_manager.clear_route()
        else:
            route_manager.set_route(self._saved_route, self._saved_route_type or "trade")
            route_manager.current_index = int(self._saved_route_index)

    def test_handoff_sets_intent_with_target_system(self) -> None:
        calls: list[tuple[str, str]] = []

        def _setter(target: str, *, source: str = "intent") -> dict:
            calls.append((target, source))
            return {"route_mode": "intent", "route_target": target}

        out = handoff_sell_assist_to_route_intent(
            {"to_system": "Lalande 5761", "to_station": "Pook Hub"},
            set_route_intent=_setter,
            source="test.sell_assist",
            allow_auto_route=False,
        )
        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(out.get("target_system"), "Lalande 5761")
        self.assertEqual(out.get("target_station"), "Pook Hub")
        self.assertEqual(calls, [("Lalande 5761", "test.sell_assist")])

    def test_handoff_rejects_auto_route_flag(self) -> None:
        with self.assertRaises(ValueError):
            handoff_sell_assist_to_route_intent(
                {"to_system": "LHS 20"},
                set_route_intent=lambda *_a, **_k: {},
                allow_auto_route=True,
            )

    def test_handoff_without_target_returns_error(self) -> None:
        out = handoff_sell_assist_to_route_intent(
            {"label": "Najszybciej"},
            set_route_intent=lambda *_a, **_k: {},
            allow_auto_route=False,
        )
        self.assertFalse(bool(out.get("ok")))
        self.assertEqual(out.get("reason"), "target_missing")

    def test_handoff_does_not_mutate_route_manager(self) -> None:
        route_manager.set_route(["A", "B", "C"], "trade")
        route_manager.current_index = 1
        before_route = list(route_manager.route)
        before_type = route_manager.route_type
        before_idx = route_manager.current_index

        out = handoff_sell_assist_to_route_intent(
            {"to_system": "Barnard's Star", "to_station": "Levi-Strauss Installation"},
            set_route_intent=app_state.set_route_intent,
            source="test.sell_assist.handoff",
            allow_auto_route=False,
        )
        self.assertTrue(bool(out.get("ok")))
        snap = app_state.get_route_awareness_snapshot()
        self.assertEqual(str(snap.get("route_mode")), "intent")
        self.assertEqual(str(snap.get("route_target")), "Barnard's Star")
        self.assertEqual(route_manager.route, before_route)
        self.assertEqual(route_manager.route_type, before_type)
        self.assertEqual(route_manager.current_index, before_idx)


if __name__ == "__main__":
    unittest.main()
