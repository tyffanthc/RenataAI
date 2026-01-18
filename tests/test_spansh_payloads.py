import unittest

import config
from logic import spansh_payloads


class DummyAppState:
    def __init__(self, current_system: str = "Sol") -> None:
        self.current_system = current_system


class DummyShipState:
    def __init__(self, jump_range_current_ly: float | None) -> None:
        self.jump_range_current_ly = jump_range_current_ly


def _fields_to_dict(fields):
    out = {}
    for key, value in fields:
        if key in out:
            if isinstance(out[key], list):
                out[key].append(value)
            else:
                out[key] = [out[key], value]
        else:
            out[key] = value
    return out


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

        fields = _fields_to_dict(payload.form_fields)
        self.assertEqual(fields.get("from"), "Sol")

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

        fields = _fields_to_dict(payload.form_fields)
        self.assertEqual(fields.get("range"), "55.5")

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

        fields = _fields_to_dict(payload.form_fields)
        self.assertEqual(fields.get("range"), "33.3")

    def test_neutron_supercharge_modes(self) -> None:
        payload_normal = spansh_payloads.build_neutron_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            eff=60.0,
            supercharge_mode="normal",
        )
        payload_overcharge = spansh_payloads.build_neutron_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            eff=60.0,
            supercharge_mode="overcharge",
        )

        fields_normal = _fields_to_dict(payload_normal.form_fields)
        fields_over = _fields_to_dict(payload_overcharge.form_fields)

        self.assertEqual(payload_normal.endpoint_path, "/route")
        self.assertEqual(fields_normal.get("supercharge_multiplier"), "4")
        self.assertEqual(fields_over.get("supercharge_multiplier"), "6")
        self.assertEqual(fields_normal.get("range"), "42.5")
        self.assertEqual(fields_normal.get("efficiency"), "60")

    def test_neutron_via_multi_field_order(self) -> None:
        payload = spansh_payloads.build_neutron_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            eff=60.0,
            supercharge_mode="normal",
            via=["Djabal", "TY Bootis"],
        )
        via_fields = [value for key, value in payload.form_fields if key == "via"]
        self.assertEqual(via_fields, ["Djabal", "TY Bootis"])

    def test_riches_flags_and_endpoint(self) -> None:
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
        )
        fields = _fields_to_dict(payload.form_fields)

        self.assertEqual(payload.endpoint_path, "/riches/route")
        self.assertEqual(fields.get("loop"), "1")
        self.assertEqual(fields.get("use_mapping_value"), "1")
        self.assertEqual(fields.get("avoid_thargoids"), "0")

    def test_ammonia_elw_hmc_payloads(self) -> None:
        ammonia = spansh_payloads.build_ammonia_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=123,
            loop=False,
            avoid_tharg=True,
        )
        elw = spansh_payloads.build_elw_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=1,
            loop=False,
            avoid_tharg=True,
        )
        hmc = spansh_payloads.build_hmc_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=1,
            loop=False,
            avoid_tharg=True,
        )

        ammonia_fields = _fields_to_dict(ammonia.form_fields)
        elw_fields = _fields_to_dict(elw.form_fields)
        hmc_fields = _fields_to_dict(hmc.form_fields)

        self.assertEqual(ammonia.endpoint_path, "/riches/route")
        self.assertEqual(elw.endpoint_path, "/riches/route")
        self.assertEqual(hmc.endpoint_path, "/riches/route")

        self.assertEqual(ammonia_fields.get("min_value"), "1")
        self.assertEqual(elw_fields.get("min_value"), "1")
        self.assertEqual(hmc_fields.get("min_value"), "1")

        self.assertEqual(ammonia_fields.get("body_types"), "Ammonia world")
        self.assertEqual(elw_fields.get("body_types"), "Earth-like world")
        self.assertEqual(
            hmc_fields.get("body_types"),
            ["Rocky body", "High metal content world"],
        )

    def test_exomastery_min_value_key(self) -> None:
        payload = spansh_payloads.build_exomastery_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.5,
            radius=50,
            max_sys=25,
            max_dist=5000,
            min_value=200000,
            loop=False,
            avoid_tharg=True,
        )
        fields = _fields_to_dict(payload.form_fields)

        self.assertEqual(payload.endpoint_path, "/exobiology/route")
        self.assertEqual(fields.get("min_value"), "200000")
        self.assertNotIn("min_landmark_value", fields)

    def test_trade_payload_fields(self) -> None:
        payload = spansh_payloads.build_trade_payload(
            start_system="Sol",
            start_station="Jameson Memorial",
            capital=1_000_000,
            max_hop=25.5,
            cargo=256,
            max_hops=10,
            max_dta=1000,
            max_age=7,
            flags={
                "large_pad": True,
                "planetary": False,
                "player_owned": True,
                "restricted": False,
                "prohibited": True,
                "avoid_loops": True,
                "allow_permits": False,
            },
        )

        fields = _fields_to_dict(payload.form_fields)

        self.assertEqual(payload.endpoint_path, "/trade/route")
        self.assertEqual(fields.get("max_price_age"), "7")
        self.assertEqual(fields.get("requires_large_pad"), "1")
        self.assertEqual(fields.get("allow_planetary"), "0")
        self.assertEqual(fields.get("allow_player_owned"), "1")
        self.assertEqual(fields.get("allow_restricted_access"), "0")
        self.assertEqual(fields.get("allow_prohibited"), "1")
        self.assertEqual(fields.get("unique"), "1")
        self.assertEqual(fields.get("permit"), "0")


if __name__ == "__main__":
    unittest.main()
