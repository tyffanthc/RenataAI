from __future__ import annotations

import unittest

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F11CashInRankingProfilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        app_state.is_docked = False
        app_state.current_system = "F11_RANKING_SYSTEM"
        app_state.current_station = ""
        config.config._settings["cash_in.avoid_carriers_for_uc"] = True
        config.config._settings["cash_in.carrier_ok_for_fast_mode"] = True
        config.config._settings["cash_in.hutton_guard_ls_threshold"] = 500_000
        config.config._settings["cash_in.hutton_guard_score_penalty"] = 18

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.is_docked = self._saved_docked
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station

    @staticmethod
    def _base_payout() -> dict:
        return cash_in_assistant._build_payout_contract(
            gross_value=12_000_000.0,
            tariff_percent=5.0,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-02-20T10:00:00Z",
        )

    def test_safe_prefers_non_carrier_for_uc_and_fast_can_pick_carrier(self) -> None:
        candidates = [
            {
                "name": "Safe Station",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 18.0,
                "distance_ls": 2_000.0,
                "source": "EDSM",
            },
            {
                "name": "Fast Carrier",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 8.0,
                "distance_ls": 2_000.0,
                "source": "SPANSH",
            },
            {
                "name": "No UC",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 1.0,
                "distance_ls": 10.0,
                "source": "EDSM",
            },
        ]
        options, meta = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        safe = next(item for item in options if item.get("profile") == "SAFE")
        fast = next(item for item in options if item.get("profile") == "FAST")
        self.assertEqual(((safe.get("target") or {}).get("name") or ""), "Safe Station")
        self.assertEqual(((fast.get("target") or {}).get("name") or ""), "Fast Carrier")
        self.assertEqual(meta.get("hard_filter_count"), 2)

    def test_fast_respects_carrier_toggle(self) -> None:
        config.config._settings["cash_in.carrier_ok_for_fast_mode"] = False
        candidates = [
            {
                "name": "Safe Station",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 20.0,
                "distance_ls": 2_000.0,
                "source": "EDSM",
            },
            {
                "name": "Fast Carrier",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 5.0,
                "distance_ls": 2_000.0,
                "source": "SPANSH",
            },
        ]
        options, _ = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        fast = next(item for item in options if item.get("profile") == "FAST")
        self.assertEqual(((fast.get("target") or {}).get("name") or ""), "Safe Station")

    def test_hutton_guard_adds_warning_without_rejecting_candidate(self) -> None:
        candidates = [
            {
                "name": "Very Far LS",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 9.0,
                "distance_ls": 7_000_000.0,
                "source": "EDSM",
            }
        ]
        options, _ = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        self.assertGreaterEqual(len(options), 1)
        self.assertTrue(any("distance_ls_high" in (opt.get("warnings") or []) for opt in options))

    def test_secure_prefers_current_docked_station_with_service(self) -> None:
        app_state.is_docked = True
        app_state.current_system = "F11_RANKING_SYSTEM"
        app_state.current_station = "Dock Hub"
        candidates = [
            {
                "name": "Dock Hub",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 0.0,
                "distance_ls": 0.0,
                "source": "RUNTIME_LOCAL",
            },
            {
                "name": "Away Station",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 12.0,
                "distance_ls": 1_000.0,
                "source": "EDSM",
            },
        ]
        options, meta = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        secure = next(item for item in options if item.get("profile") == "SECURE")
        self.assertEqual(((secure.get("target") or {}).get("name") or ""), "Dock Hub")
        self.assertEqual(secure.get("eta_minutes"), 0)
        self.assertFalse(bool(secure.get("secure_fallback_to_safe")))
        self.assertFalse(bool(meta.get("secure_fallback_to_safe")))

    def test_secure_falls_back_to_safe_when_docked_station_lacks_service(self) -> None:
        app_state.is_docked = True
        app_state.current_system = "F11_RANKING_SYSTEM"
        app_state.current_station = "Dock Hub"
        candidates = [
            {
                "name": "Dock Hub",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 0.0,
                "distance_ls": 0.0,
                "source": "RUNTIME_LOCAL",
            },
            {
                "name": "Safe UC",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 11.0,
                "distance_ls": 900.0,
                "source": "EDSM",
            },
        ]
        options, meta = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        secure = next(item for item in options if item.get("profile") == "SECURE")
        self.assertEqual(((secure.get("target") or {}).get("name") or ""), "Safe UC")
        self.assertTrue(bool(secure.get("secure_fallback_to_safe")))
        self.assertTrue(bool(meta.get("secure_fallback_to_safe")))


if __name__ == "__main__":
    unittest.main()
