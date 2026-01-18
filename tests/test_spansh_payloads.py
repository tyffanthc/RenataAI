import unittest

import config
from logic import spansh_payloads


class DummyAppState:
    def __init__(self, current_system: str = "Sol") -> None:
        self.current_system = current_system


class DummyShipState:
    def __init__(self, jump_range_current_ly: float | None) -> None:
        self.jump_range_current_ly = jump_range_current_ly


class SpanshPayloadContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = config.config._settings.copy()

    def tearDown(self) -> None:
        config.config._settings = self._orig

    def _set_range_config(self, auto: bool, allow_override: bool, fallback: float) -> None:
        config.config._settings["planner_auto_use_ship_jump_range"] = auto
        config.config._settings["planner_allow_manual_range_override"] = allow_override
        config.config._settings["planner_fallback_range_ly"] = fallback

    def test_start_system_fallback(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_riches_payload(
            start="",
            cel="Colonia",
            jump_range=None,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=True,
            use_map=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        self.assertEqual(payload.get("from"), "Sol")

    def test_auto_range_uses_ship_jr(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_ammonia_payload(
            start="Sol",
            cel="Colonia",
            jump_range=None,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        self.assertEqual(payload.get("range"), 55.5)

    def test_auto_range_fallback(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=None)
        self._set_range_config(auto=True, allow_override=True, fallback=33.3)

        payload = spansh_payloads.build_ammonia_payload(
            start="Sol",
            cel="Colonia",
            jump_range=None,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        self.assertEqual(payload.get("range"), 33.3)

    def test_types_riches(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_riches_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=True,
            use_map=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        self.assertIsInstance(payload.get("radius"), float)
        self.assertIsInstance(payload.get("max_results"), int)
        self.assertIsInstance(payload.get("max_distance"), int)
        self.assertIsInstance(payload.get("min_value"), int)
        self.assertIsInstance(payload.get("loop"), bool)
        self.assertIsInstance(payload.get("avoid_thargoids"), bool)

    def test_ammonia_argument_mapping(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_ammonia_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        self.assertEqual(payload.get("min_value"), 123)
        self.assertEqual(payload.get("loop"), True)
        self.assertEqual(payload.get("avoid_thargoids"), False)

    def test_riches_payload_snapshot(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_riches_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=250000,
            loop=True,
            use_map=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        expected = {
            "from": "Sol",
            "to": "Colonia",
            "range": 42.5,
            "radius": 50.0,
            "max_results": 25,
            "max_distance": 5000,
            "min_value": 250000,
            "loop": True,
            "use_mapping_value": True,
            "avoid_thargoids": False,
        }
        self.assertEqual(payload, expected)

    def test_ammonia_payload_snapshot(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_ammonia_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=True,
            avoid_tharg=False,
            app_state=app_state,
            ship_state=ship_state,
        )

        expected = {
            "from": "Sol",
            "to": "Colonia",
            "range": 42.5,
            "radius": 50.0,
            "max_results": 25,
            "max_distance": 5000,
            "min_value": 123,
            "loop": True,
            "avoid_thargoids": False,
        }
        self.assertEqual(payload, expected)

    def test_elw_payload_snapshot(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_elw_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=1,
            loop=False,
            avoid_tharg=True,
            app_state=app_state,
            ship_state=ship_state,
        )

        expected = {
            "from": "Sol",
            "to": "Colonia",
            "range": 42.5,
            "radius": 50.0,
            "max_results": 25,
            "max_distance": 5000,
            "min_value": 1,
            "loop": False,
            "avoid_thargoids": True,
            "body_types": "Earth-like world",
        }
        self.assertEqual(payload, expected)

    def test_hmc_payload_snapshot(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_hmc_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=1,
            loop=False,
            avoid_tharg=True,
            app_state=app_state,
            ship_state=ship_state,
        )

        expected = {
            "from": "Sol",
            "to": "Colonia",
            "range": 42.5,
            "radius": 50.0,
            "max_results": 25,
            "max_distance": 5000,
            "min_value": 1,
            "loop": False,
            "avoid_thargoids": True,
            "body_types": ["Rocky body", "High metal content world"],
        }
        self.assertEqual(payload, expected)

    def test_exomastery_payload_snapshot(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_exomastery_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_landmark_value=200000,
            loop=False,
            avoid_tharg=True,
            app_state=app_state,
            ship_state=ship_state,
        )

        expected = {
            "from": "Sol",
            "to": "Colonia",
            "range": 42.5,
            "radius": 50.0,
            "max_results": 25,
            "max_distance": 5000,
            "min_landmark_value": 200000,
            "loop": False,
            "avoid_thargoids": True,
        }
        self.assertEqual(payload, expected)

    def test_trade_max_age_not_sent(self) -> None:
        payload = spansh_payloads.build_trade_payload(
            start_system="Sol",
            start_station="Jameson Memorial",
            capital=1_000_000,
            max_hop=25.5,
            cargo=256,
            max_hops=10,
            max_dta=1000,
            max_age=7,
            flags={"avoid_loops": True},
            app_state=DummyAppState(current_system="Sol"),
        )

        self.assertNotIn("max_age", payload)
        self.assertNotIn("max_age_days", payload)

    def test_trade_payload_snapshot(self) -> None:
        payload = spansh_payloads.build_trade_payload(
            start_system="Sol",
            start_station="Jameson Memorial",
            capital=1_000_000,
            max_hop=25.5,
            cargo=256,
            max_hops=10,
            max_dta=1000,
            max_age=0,
            flags={
                "large_pad": True,
                "planetary": False,
                "player_owned": True,
                "restricted": False,
                "prohibited": True,
                "avoid_loops": True,
                "allow_permits": False,
            },
            app_state=DummyAppState(current_system="Sol"),
        )

        expected = {
            "max_hops": 10,
            "max_hop_distance": 25.5,
            "system": "Sol",
            "station": "Jameson Memorial",
            "starting_capital": 1000000,
            "max_cargo": 256,
            "max_system_distance": 1000,
            "requires_large_pad": 1,
            "allow_prohibited": 1,
            "allow_planetary": 0,
            "allow_player_owned": 1,
            "allow_restricted_access": 0,
            "unique": 1,
            "permit": 0,
        }
        self.assertEqual(payload, expected)

    def test_neutron_payload_types(self) -> None:
        app_state = DummyAppState(current_system="Sol")
        ship_state = DummyShipState(jump_range_current_ly=55.5)
        self._set_range_config(auto=True, allow_override=True, fallback=30.0)

        payload = spansh_payloads.build_neutron_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            eff=60.0,
            app_state=app_state,
            ship_state=ship_state,
        )

        self.assertEqual(payload.get("range"), "42.5")
        self.assertEqual(payload.get("efficiency"), "60.0")


if __name__ == "__main__":
    unittest.main()
