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
        config.config._settings["cash_in.express_max_distance_ls"] = 5_000.0
        config.config._settings["cash_in.planetary_vista_max_gravity_g"] = 2.0
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

    def test_nearest_allows_carrier_and_express_prefers_short_ls(self) -> None:
        candidates = [
            {
                "name": "Safe Station",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 18.0,
                "distance_ls": 400.0,
                "source": "EDSM",
                "security": "high",
            },
            {
                "name": "Fast Carrier",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 8.0,
                "distance_ls": 2_200.0,
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
        nearest = next(item for item in options if item.get("profile") == "NEAREST")
        express = next(item for item in options if item.get("profile") == "EXPRESS")
        self.assertEqual(((nearest.get("target") or {}).get("name") or ""), "Fast Carrier")
        self.assertEqual(((express.get("target") or {}).get("name") or ""), "Safe Station")
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
        fast = next(item for item in options if item.get("profile") == "EXPRESS")
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
                "security": "high",
            },
            {
                "name": "Away Station",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 12.0,
                "distance_ls": 1_000.0,
                "source": "EDSM",
                "security": "medium",
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
                "security": "low",
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

    def test_options_include_ui_transparency_contract_shape(self) -> None:
        candidates = [
            {
                "name": "Safe Station",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 18.0,
                "distance_ls": 2_000.0,
                "source": "EDSM",
                "freshness_ts": "2026-02-21T12:00:00Z",
            },
            {
                "name": "Fast Carrier",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 8.0,
                "distance_ls": 2_000.0,
                "source": "SPANSH",
                "freshness_ts": "2026-02-21T12:00:00Z",
            },
        ]
        options, _ = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        enriched = cash_in_assistant._apply_ui_transparency_contract(options)
        self.assertGreaterEqual(len(enriched), 2)
        first = dict(enriched[0])
        self.assertEqual(first.get("ui_contract_version"), "F11_UI_V1")
        ui = dict(first.get("ui_contract") or {})
        self.assertIn(ui.get("label"), {"NEAREST", "SECURE", "EXPRESS", "PLANETARY_VISTA"})
        self.assertIn("target", ui)
        self.assertIn("payout", ui)
        self.assertIn("eta", ui)
        self.assertIn("risk", ui)
        self.assertEqual(list(ui.get("actions") or []), ["set_route", "copy_next_hop", "skip"])

    def test_ui_contract_marks_vista_fc_assumption_with_freshness(self) -> None:
        candidates = [
            {
                "name": "Vista FC",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "fleet_carrier",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 3.0,
                "distance_ls": 900.0,
                "source": "SPANSH",
                "freshness_ts": "2026-02-21T13:40:00Z",
            }
        ]
        payout = cash_in_assistant._build_payout_contract(
            gross_value=10_000_000.0,
            tariff_percent=None,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-02-21T13:40:00Z",
        )
        options, _ = cash_in_assistant._build_profiled_options(
            service="vista",
            candidates=candidates,
            payout_contract=payout,
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        enriched = cash_in_assistant._apply_ui_transparency_contract(options)
        self.assertGreaterEqual(len(enriched), 1)
        ui = dict((enriched[0].get("ui_contract") or {}))
        payout_ui = dict(ui.get("payout") or {})
        self.assertEqual(str(payout_ui.get("assumption_label") or ""), "assumption")
        self.assertTrue(bool(str(payout_ui.get("freshness_ts") or "").strip()))

    def test_planetary_vista_profile_prefers_planetary_candidate_within_gravity_cap(self) -> None:
        candidates = [
            {
                "name": "Vista Orbital",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "station",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 4.0,
                "distance_ls": 800.0,
                "source": "SPANSH",
                "is_planetary": False,
            },
            {
                "name": "Vista Ground Alpha",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "settlement",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 9.0,
                "distance_ls": 1_200.0,
                "source": "EDSM",
                "is_planetary": True,
                "gravity_g": 1.4,
            },
            {
                "name": "Vista Ground HighG",
                "system_name": "F11_RANKING_SYSTEM",
                "type": "settlement",
                "services": {"has_uc": False, "has_vista": True},
                "distance_ly": 2.0,
                "distance_ls": 900.0,
                "source": "EDSM",
                "is_planetary": True,
                "gravity_g": 2.7,
            },
        ]
        payout = cash_in_assistant._build_payout_contract(
            gross_value=8_000_000.0,
            tariff_percent=None,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-02-21T13:40:00Z",
        )
        options, meta = cash_in_assistant._build_profiled_options(
            service="vista",
            candidates=candidates,
            payout_contract=payout,
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        planetary = next(item for item in options if item.get("profile") == "PLANETARY_VISTA")
        self.assertEqual(str((planetary.get("target") or {}).get("name") or ""), "Vista Ground Alpha")
        self.assertFalse(bool(planetary.get("planetary_vista_fallback_to_nearest")))
        self.assertEqual(int(meta.get("planetary_vista_candidates_count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
