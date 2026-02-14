import unittest

import config
from app.route_manager import route_manager
from app.state import app_state
from logic.events import navigation_events


class RouteAwarenessStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = app_state.get_route_awareness_snapshot()
        self._saved_keys = {
            "route_mode": config.STATE.get("route_mode"),
            "route_target": config.STATE.get("route_target"),
            "route_progress_percent": config.STATE.get("route_progress_percent"),
            "route_next_system": config.STATE.get("route_next_system"),
            "route_is_off_route": config.STATE.get("route_is_off_route"),
        }
        self._saved_nav_route = dict(getattr(app_state, "nav_route", {}) or {})
        self._saved_system = getattr(app_state, "current_system", "")
        route_manager.clear_route()
        app_state.clear_spansh_milestones(source="test.setup")
        app_state.update_route_awareness(
            route_mode="idle",
            route_target="",
            route_progress_percent=0,
            next_system="",
            is_off_route=False,
            source="test.setup",
        )

    def tearDown(self) -> None:
        route_manager.clear_route()
        app_state.clear_spansh_milestones(source="test.teardown")
        app_state.set_nav_route(
            endpoint=self._saved_nav_route.get("endpoint"),
            systems=self._saved_nav_route.get("systems") or [],
            source="test.teardown.restore",
        )
        app_state.set_system(self._saved_system or "Unknown")
        app_state.update_route_awareness(
            route_mode=str(self._saved.get("route_mode") or "idle"),
            route_target=str(self._saved.get("route_target") or ""),
            route_progress_percent=int(self._saved.get("route_progress_percent") or 0),
            next_system=str(self._saved.get("next_system") or ""),
            is_off_route=bool(self._saved.get("is_off_route")),
            source="test.teardown",
        )
        for key, value in self._saved_keys.items():
            if value is None and key in config.STATE:
                config.STATE.pop(key, None)
            else:
                config.STATE[key] = value

    def test_set_route_intent_sets_intent_mode(self) -> None:
        app_state.set_route_intent("Colonia", source="test.intent")
        snap = app_state.get_route_awareness_snapshot()
        self.assertEqual(snap.get("route_mode"), "intent")
        self.assertEqual(snap.get("route_target"), "Colonia")
        self.assertEqual(snap.get("next_system"), "Colonia")
        self.assertEqual(int(snap.get("route_progress_percent") or 0), 0)
        self.assertFalse(bool(snap.get("is_off_route")))

    def test_update_route_awareness_clamps_progress(self) -> None:
        app_state.update_route_awareness(
            route_mode="awareness",
            route_target="Sagittarius A*",
            route_progress_percent=180,
            next_system="Dryau Ausms KG-Y d7561",
            is_off_route=False,
            source="test.clamp",
        )
        snap = app_state.get_route_awareness_snapshot()
        self.assertEqual(snap.get("route_mode"), "awareness")
        self.assertEqual(int(snap.get("route_progress_percent") or 0), 100)

    def test_navroute_update_sets_awareness_when_no_spansh_route(self) -> None:
        app_state.set_system("Alpha")
        navigation_events.handle_navroute_update(
            {
                "event": "NavRoute",
                "EndSystem": "Gamma",
                "Route": [
                    {"StarSystem": "Alpha"},
                    {"StarSystem": "Beta"},
                    {"StarSystem": "Gamma"},
                ],
            }
        )
        snap = app_state.get_route_awareness_snapshot()
        self.assertEqual(snap.get("route_mode"), "awareness")
        self.assertEqual(snap.get("route_target"), "Gamma")
        self.assertEqual(snap.get("next_system"), "Beta")
        self.assertEqual(int(snap.get("route_progress_percent") or 0), 0)


if __name__ == "__main__":
    unittest.main()
