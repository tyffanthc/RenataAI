from __future__ import annotations

import unittest

from app.state import app_state
from gui import common_route_progress as route_progress


class F56RouteMilestonePhaseSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_route_systems = list(route_progress._ACTIVE_ROUTE_SYSTEMS)
        self._saved_route_source = route_progress._ACTIVE_ROUTE_SOURCE
        with app_state.lock:
            self._saved_spansh_milestone_mode = app_state.spansh_milestone_mode

    def tearDown(self) -> None:
        route_progress._ACTIVE_ROUTE_SYSTEMS = list(self._saved_route_systems)
        route_progress._ACTIVE_ROUTE_SOURCE = self._saved_route_source
        with app_state.lock:
            app_state.spansh_milestone_mode = self._saved_spansh_milestone_mode

    def test_resolve_milestone_phase_returns_boost_for_neutron_intermediate_target(self) -> None:
        route_progress._ACTIVE_ROUTE_SYSTEMS = ["A", "B", "C", "D"]
        route_progress._ACTIVE_ROUTE_SOURCE = "neu"
        with app_state.lock:
            app_state.spansh_milestone_mode = "neutron"

        phase = route_progress._resolve_milestone_phase(1)
        self.assertEqual(phase, "boost")

    def test_resolve_milestone_phase_returns_goal_for_neutron_final_target(self) -> None:
        route_progress._ACTIVE_ROUTE_SYSTEMS = ["A", "B", "C", "D"]
        route_progress._ACTIVE_ROUTE_SOURCE = "neu"
        with app_state.lock:
            app_state.spansh_milestone_mode = "neutron"

        phase = route_progress._resolve_milestone_phase(3)
        self.assertEqual(phase, "goal")

    def test_resolve_milestone_phase_defaults_to_goal_for_non_neutron_route(self) -> None:
        route_progress._ACTIVE_ROUTE_SYSTEMS = ["A", "B", "C"]
        route_progress._ACTIVE_ROUTE_SOURCE = "trade"
        with app_state.lock:
            app_state.spansh_milestone_mode = None

        phase = route_progress._resolve_milestone_phase(1)
        self.assertEqual(phase, "goal")


if __name__ == "__main__":
    unittest.main()

