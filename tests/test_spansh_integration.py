import os
import unittest

import config
from logic import spansh_payloads
from logic.spansh_client import SpanshClient


def _integration_enabled() -> bool:
    return os.getenv("SPANSH_INTEGRATION") == "1"


def _base_url() -> str:
    raw = os.getenv("SPANSH_BASE_URL", "https://spansh.co.uk")
    raw = raw.rstrip("/")
    if not raw.endswith("/api"):
        return f"{raw}/api"
    return raw


def _has_non_empty_list(result) -> bool:
    if isinstance(result, list):
        return len(result) > 0
    if isinstance(result, dict):
        for val in result.values():
            if isinstance(val, list) and len(val) > 0:
                return True
    return False


@unittest.skipUnless(_integration_enabled(), "SPANSH_INTEGRATION not enabled")
class SpanshIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = config.config._settings.copy()
        config.config._settings["spansh_base_url"] = _base_url()
        self.client = SpanshClient()

    def tearDown(self) -> None:
        config.config._settings = self._orig

    def test_neutron_integration(self) -> None:
        payload = spansh_payloads.build_neutron_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            eff=60.0,
        )
        result = self.client.route(
            mode="neutron",
            payload=payload,
            referer="https://spansh.co.uk/plotter",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))

    def test_riches_integration(self) -> None:
        payload = spansh_payloads.build_riches_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=5,
            max_dist=5000,
            min_value=250000,
            loop=False,
            use_map=True,
            avoid_tharg=True,
        )
        result = self.client.route(
            mode="riches",
            payload=payload,
            referer="https://spansh.co.uk/riches",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))

    def test_ammonia_integration(self) -> None:
        payload = spansh_payloads.build_ammonia_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=5,
            max_dist=5000,
            min_value=100000,
            loop=False,
            avoid_tharg=True,
        )
        result = self.client.route(
            mode="ammonia",
            payload=payload,
            referer="https://spansh.co.uk/ammonia",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))

    def test_elw_integration(self) -> None:
        payload = spansh_payloads.build_elw_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=5,
            max_dist=5000,
            min_value=1,
            loop=False,
            avoid_tharg=True,
        )
        result = self.client.route(
            mode="riches",
            payload=payload,
            referer="https://spansh.co.uk/riches",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))

    def test_hmc_integration(self) -> None:
        payload = spansh_payloads.build_hmc_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=5,
            max_dist=5000,
            min_value=1,
            loop=False,
            avoid_tharg=True,
        )
        result = self.client.route(
            mode="riches",
            payload=payload,
            referer="https://spansh.co.uk/riches",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))

    def test_exomastery_integration(self) -> None:
        payload = spansh_payloads.build_exomastery_payload(
            start="Sol",
            cel="Colonia",
            jump_range=42.0,
            radius=50,
            max_sys=5,
            max_dist=5000,
            min_landmark_value=200000,
            loop=False,
            avoid_tharg=True,
        )
        result = self.client.route(
            mode="exobiology",
            payload=payload,
            referer="https://spansh.co.uk/exobiology",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))

    def test_trade_integration(self) -> None:
        payload = spansh_payloads.build_trade_payload(
            start_system="Sol",
            start_station="Jameson Memorial",
            capital=1_000_000,
            max_hop=25.0,
            cargo=64,
            max_hops=4,
            max_dta=1000,
            max_age=0,
            flags={"avoid_loops": True},
        )
        result = self.client.route(
            mode="trade",
            payload=payload,
            referer="https://spansh.co.uk/trade",
            gui_ref=None,
        )
        self.assertTrue(result is not None)
        self.assertTrue(_has_non_empty_list(result))


if __name__ == "__main__":
    unittest.main()
