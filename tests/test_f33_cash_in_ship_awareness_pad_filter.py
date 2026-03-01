from __future__ import annotations

import unittest

import config
from app.state import app_state
from logic.cash_in_station_candidates import filter_candidates_by_pad_requirement
from logic.events import cash_in_assistant


class F33CashInShipAwarenessPadFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_needs_large_pad = bool(getattr(app_state, "needs_large_pad", False))
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)

        app_state.current_system = "F33_ORIGIN"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.set_needs_large_pad(False, source="test.f33.setup")
        config.config._settings["cash_in.ship_size_auto_lock_enabled"] = True

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.set_needs_large_pad(self._saved_needs_large_pad, source="test.f33.teardown")

    @staticmethod
    def _base_payout() -> dict:
        return cash_in_assistant._build_payout_contract(
            gross_value=10_000_000.0,
            tariff_percent=5.0,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-03-01T12:00:00Z",
        )

    def test_loadout_sets_needs_large_pad_for_large_ship(self) -> None:
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "Ship": "Anaconda", "Modules": []},
            source="test.f33.loadout.large",
        )
        self.assertTrue(bool(getattr(app_state, "needs_large_pad", False)))

    def test_loadout_clears_needs_large_pad_for_non_large_ship(self) -> None:
        app_state.set_needs_large_pad(True, source="test.f33.prime")
        app_state.update_mode_signal_from_journal(
            {"event": "Loadout", "Ship": "CobraMkIII", "Modules": []},
            source="test.f33.loadout.small",
        )
        self.assertFalse(bool(getattr(app_state, "needs_large_pad", True)))

    def test_pad_filter_rejects_outpost_and_small_pad_when_required(self) -> None:
        rows = [
            {"name": "Near Outpost", "system_name": "A", "type": "outpost", "services": {"has_uc": True}},
            {"name": "Medium Port", "system_name": "A", "type": "station", "max_landing_pad_size": "M"},
            {"name": "Large Port", "system_name": "A", "type": "station", "max_landing_pad_size": "L"},
        ]
        out = filter_candidates_by_pad_requirement(
            rows,
            needs_large_pad=True,
            auto_lock_enabled=True,
        )
        names = [str(item.get("name") or "") for item in out]
        self.assertEqual(names, ["Large Port"])

    def test_profiled_options_respect_large_pad_lock_and_override(self) -> None:
        candidates = [
            {
                "name": "Near Outpost",
                "system_name": "F33_ORIGIN",
                "type": "outpost",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 4.0,
                "distance_ls": 800.0,
                "source": "OFFLINE_INDEX",
                "max_landing_pad_size": "M",
            },
            {
                "name": "Far Large Port",
                "system_name": "F33_ORIGIN",
                "type": "station",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 12.0,
                "distance_ls": 1200.0,
                "source": "EDSM",
                "max_landing_pad_size": "L",
            },
        ]

        app_state.set_needs_large_pad(True, source="test.f33.pad_lock_on")
        config.config._settings["cash_in.ship_size_auto_lock_enabled"] = True
        options_locked, meta_locked = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        nearest_locked = next(item for item in options_locked if item.get("profile") == "NEAREST")
        self.assertEqual(str((nearest_locked.get("target") or {}).get("name") or ""), "Far Large Port")
        self.assertTrue(bool(meta_locked.get("ship_pad_filter_applied")))
        self.assertGreaterEqual(int(meta_locked.get("ship_pad_filtered_out_count") or 0), 1)

        config.config._settings["cash_in.ship_size_auto_lock_enabled"] = False
        options_override, meta_override = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=self._base_payout(),
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        nearest_override = next(item for item in options_override if item.get("profile") == "NEAREST")
        self.assertEqual(str((nearest_override.get("target") or {}).get("name") or ""), "Near Outpost")
        self.assertFalse(bool(meta_override.get("ship_pad_filter_applied")))


if __name__ == "__main__":
    unittest.main()

