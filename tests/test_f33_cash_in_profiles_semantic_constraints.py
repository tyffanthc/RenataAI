from __future__ import annotations

import unittest

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F33CashInProfilesSemanticConstraintsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)

        app_state.current_system = "F33_PROFILE_ORIGIN"
        app_state.current_station = ""
        app_state.is_docked = False

        config.config._settings["cash_in.carrier_ok_for_fast_mode"] = True
        config.config._settings["cash_in.express_mode_enabled"] = True
        config.config._settings["cash_in.express_max_distance_ls"] = 5_000.0
        config.config._settings["cash_in.planetary_vista_max_gravity_g"] = 2.0
        config.config._settings["cash_in.hutton_guard_ls_threshold"] = 500_000.0
        config.config._settings["cash_in.hutton_guard_score_penalty"] = 18

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked

    @staticmethod
    def _base_payout() -> dict:
        return cash_in_assistant._build_payout_contract(
            gross_value=10_000_000.0,
            tariff_percent=None,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-03-01T12:00:00Z",
        )

    def test_legacy_profile_aliases_resolve_to_semantic_names(self) -> None:
        self.assertEqual(cash_in_assistant._normalize_cash_in_profile("1"), "NEAREST")
        self.assertEqual(cash_in_assistant._normalize_cash_in_profile("2"), "SECURE")
        self.assertEqual(cash_in_assistant._normalize_cash_in_profile("3"), "EXPRESS")
        self.assertEqual(cash_in_assistant._normalize_cash_in_profile("SECURE_PORT"), "SECURE")
        self.assertEqual(cash_in_assistant._normalize_cash_in_profile("CARRIER_FRIENDLY"), "EXPRESS")

    def test_profiled_options_expose_four_semantic_profiles(self) -> None:
        candidates = [
            {
                "name": "Near Carrier",
                "system_name": "F33_PROFILE_ORIGIN",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 7.0,
                "distance_ls": 2_000.0,
                "source": "SPANSH",
            },
            {
                "name": "Secure NPC",
                "system_name": "F33_PROFILE_ORIGIN",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "security": "high",
                "distance_ly": 11.0,
                "distance_ls": 1_200.0,
                "source": "EDSM",
            },
            {
                "name": "Express NPC",
                "system_name": "F33_PROFILE_ORIGIN",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "security": "medium",
                "distance_ly": 15.0,
                "distance_ls": 400.0,
                "source": "PLAYERDB",
            },
        ]
        options, meta = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        profiles = [str(item.get("profile") or "") for item in options]
        self.assertEqual(profiles, ["SECURE", "NEAREST", "EXPRESS", "PLANETARY_VISTA"])
        self.assertEqual(str((options[0].get("target") or {}).get("name") or ""), "Secure NPC")
        self.assertEqual(str((options[1].get("target") or {}).get("name") or ""), "Near Carrier")
        self.assertEqual(str((options[2].get("target") or {}).get("name") or ""), "Express NPC")
        self.assertTrue(bool(meta.get("planetary_vista_fallback_to_nearest")))

    def test_planetary_vista_respects_max_gravity(self) -> None:
        candidates = [
            {
                "name": "Vista Ground HighG",
                "system_name": "F33_PROFILE_ORIGIN",
                "type": "settlement",
                "services": {"has_uc": False, "has_vista": True},
                "is_planetary": True,
                "gravity_g": 2.4,
                "distance_ly": 2.0,
                "distance_ls": 800.0,
                "source": "EDSM",
            },
            {
                "name": "Vista Ground SafeG",
                "system_name": "F33_PROFILE_ORIGIN",
                "type": "settlement",
                "services": {"has_uc": False, "has_vista": True},
                "is_planetary": True,
                "gravity_g": 1.6,
                "distance_ly": 10.0,
                "distance_ls": 1_200.0,
                "source": "EDSM",
            },
        ]
        options, meta = cash_in_assistant._build_profiled_options(
            service="vista",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        planetary = next(item for item in options if item.get("profile") == "PLANETARY_VISTA")
        self.assertEqual(str((planetary.get("target") or {}).get("name") or ""), "Vista Ground SafeG")
        self.assertEqual(int(meta.get("planetary_vista_candidates_count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
