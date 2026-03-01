from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from gui.tabs.pulpit import PulpitTab
from logic.events import cash_in_assistant


class _DummyPulpit:
    _build_cash_summary_seed = PulpitTab._build_cash_summary_seed
    _refresh_cash_nav_toggle_snapshot = PulpitTab._refresh_cash_nav_toggle_snapshot
    _sync_cash_nav_toggle_buttons = PulpitTab._sync_cash_nav_toggle_buttons
    _persist_cash_nav_settings = PulpitTab._persist_cash_nav_settings
    _apply_cash_nav_toggle = PulpitTab._apply_cash_nav_toggle
    _toggle_cash_nav_ship_lock = PulpitTab._toggle_cash_nav_ship_lock
    _toggle_cash_nav_express_mode = PulpitTab._toggle_cash_nav_express_mode
    _toggle_cash_nav_allow_carriers = PulpitTab._toggle_cash_nav_allow_carriers

    def __init__(self) -> None:
        self._current_cash_in_payload = {
            "system": "F33_PULPIT_ORIGIN",
            "scanned_bodies": 7,
            "total_bodies": 11,
            "signal": "sredni",
            "system_value_estimated": 3_000_000.0,
            "session_value_estimated": 8_000_000.0,
            "trust_status": "TRUST_HIGH",
            "confidence": "high",
        }
        self._current_exploration_summary_payload = {}
        self._cash_service_mode = "uc"
        self._cash_ship_auto_lock_enabled = True
        self._cash_express_mode_enabled = True
        self._cash_allow_carriers_enabled = True

        self.logs: list[str] = []
        self.loading_domains: list[str] = []
        self.info_messages: list[str] = []
        self.refresh_calls: list[dict] = []

    def log(self, text: str) -> None:
        self.logs.append(str(text or ""))

    def _show_loading_panel(self, domain: str, title: str | None = None) -> None:
        self.loading_domains.append(str(domain or ""))

    def _show_info_panel(self, domain: str, message: str, title: str | None = None) -> None:
        self.info_messages.append(f"{domain}:{message}")

    def _request_cash_in_assistant(
        self,
        *,
        mode: str = "manual",
        summary_seed: dict | None = None,
    ) -> bool:
        self.refresh_calls.append(
            {
                "mode": str(mode or ""),
                "summary_seed": dict(summary_seed or {}),
            }
        )
        return True


class F33CashInPulpitTogglesSmartNavTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_needs_large_pad = bool(getattr(app_state, "needs_large_pad", False))
        app_state.set_needs_large_pad(False, source="test.f33.pulpit.setup")
        config.config._settings["cash_in.ship_size_auto_lock_enabled"] = True
        config.config._settings["cash_in.express_mode_enabled"] = True
        config.config._settings["cash_in.carrier_ok_for_fast_mode"] = True
        config.config._settings["cash_in.express_max_distance_ls"] = 5_000.0
        config.config._settings["cash_in.planetary_vista_max_gravity_g"] = 2.0

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.set_needs_large_pad(self._saved_needs_large_pad, source="test.f33.pulpit.teardown")

    @staticmethod
    def _base_payout() -> dict:
        return cash_in_assistant._build_payout_contract(
            gross_value=12_000_000.0,
            tariff_percent=None,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-03-01T12:00:00Z",
        )

    def test_pulpit_ship_toggle_persists_and_refreshes_cashin(self) -> None:
        dummy = _DummyPulpit()

        def _save_patch(patch: dict) -> None:
            config.config._settings.update(dict(patch or {}))

        with patch("gui.tabs.pulpit.config.save", side_effect=_save_patch) as save_mock:
            dummy._toggle_cash_nav_ship_lock()

        self.assertEqual(save_mock.call_count, 1)
        self.assertFalse(bool(config.config._settings.get("cash_in.ship_size_auto_lock_enabled", True)))
        self.assertEqual(dummy.loading_domains, ["cash"])
        self.assertEqual(len(dummy.refresh_calls), 1)
        self.assertEqual(str(dummy.refresh_calls[0].get("mode") or ""), "manual")
        seed = dict(dummy.refresh_calls[0].get("summary_seed") or {})
        self.assertEqual(str(seed.get("system") or ""), "F33_PULPIT_ORIGIN")
        self.assertEqual(float(seed.get("cash_in_session_estimated") or 0.0), 8_000_000.0)

    def test_express_toggle_changes_runtime_ranking(self) -> None:
        candidates = [
            {
                "name": "Near High LS",
                "system_name": "F33_PULPIT_ORIGIN",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "security": "high",
                "distance_ly": 3.0,
                "distance_ls": 35_000.0,
                "source": "EDSM",
            },
            {
                "name": "Far Low LS",
                "system_name": "F33_PULPIT_ORIGIN",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "security": "high",
                "distance_ly": 8.0,
                "distance_ls": 700.0,
                "source": "PLAYERDB",
            },
        ]

        config.config._settings["cash_in.express_mode_enabled"] = True
        options_exp_on, _ = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        express_on = next(item for item in options_exp_on if item.get("profile") == "EXPRESS")
        self.assertEqual(str((express_on.get("target") or {}).get("name") or ""), "Far Low LS")

        config.config._settings["cash_in.express_mode_enabled"] = False
        options_exp_off, _ = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        express_off = next(item for item in options_exp_off if item.get("profile") == "EXPRESS")
        self.assertEqual(str((express_off.get("target") or {}).get("name") or ""), "Near High LS")


if __name__ == "__main__":
    unittest.main()

