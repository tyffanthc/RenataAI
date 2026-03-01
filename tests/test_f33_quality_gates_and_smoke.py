from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.events import cash_in_assistant


class F33QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_settings = dict(config.config._settings)
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_station = getattr(app_state, "current_station", None)
        self._saved_docked = getattr(app_state, "is_docked", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        self._saved_needs_large_pad = bool(getattr(app_state, "needs_large_pad", False))

        app_state.current_system = "F33_QG_ORIGIN"
        app_state.current_station = ""
        app_state.is_docked = False
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None
        app_state.set_needs_large_pad(False, source="test.f33.qg.setup")

        config.config._settings["cash_in_assistant_enabled"] = True
        config.config._settings["cash_in.ship_size_auto_lock_enabled"] = True
        config.config._settings["cash_in.express_mode_enabled"] = True
        config.config._settings["cash_in.carrier_ok_for_fast_mode"] = True
        config.config._settings["cash_in.express_max_distance_ls"] = 5_000.0
        config.config._settings["cash_in.planetary_vista_max_gravity_g"] = 2.0
        config.config._settings["cash_in.clipboard_auto_target_enabled"] = True
        config.config._settings["cash_in.station_candidates_lookup_enabled"] = False
        config.config._settings["cash_in.cross_system_discovery_enabled"] = False

    def tearDown(self) -> None:
        config.config._settings = self._orig_settings
        app_state.current_system = self._saved_system
        app_state.current_station = self._saved_station
        app_state.is_docked = self._saved_docked
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig
        app_state.set_needs_large_pad(self._saved_needs_large_pad, source="test.f33.qg.teardown")

    @staticmethod
    def _payload_base() -> dict:
        return {
            "system": "F33_QG_ORIGIN",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 6_000_000.0,
            "cash_in_session_estimated": 18_000_000.0,
            "service": "uc",
            "confidence": "high",
        }

    def test_quality_gate_ship_filter_clipboard_and_outpost_tts_branch(self) -> None:
        app_state.set_needs_large_pad(True, source="test.f33.qg.large_ship")
        payload = dict(self._payload_base())
        payload["station_candidates"] = [
            {
                "name": "F33 QG Near Outpost",
                "system_name": "F33_QG_OUTPOST",
                "type": "outpost",
                "max_landing_pad_size": "M",
                "security": "high",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 2.0,
                "distance_ls": 700.0,
                "source": "OFFLINE_INDEX",
            },
            {
                "name": "F33 QG Large Port",
                "system_name": "F33_QG_LARGE",
                "type": "station",
                "max_landing_pad_size": "L",
                "security": "high",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 12.0,
                "distance_ls": 1400.0,
                "source": "EDSM",
            },
        ]

        with (
            patch("logic.events.cash_in_assistant.try_copy_to_clipboard", return_value={"ok": True}) as copy_mock,
            patch("logic.events.cash_in_assistant.emit_insight") as emit_mock,
        ):
            ok = cash_in_assistant.trigger_cash_in_assistant(
                mode="manual",
                summary_payload=payload,
            )

        self.assertTrue(ok)
        copy_mock.assert_called_once_with(
            "F33_QG_LARGE",
            context="cash_in.assistant.target_system",
        )
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        ranking_meta = dict(structured.get("ranking_meta") or {})
        edge_meta = dict(structured.get("edge_case_meta") or {})
        reasons = [str(item) for item in (edge_meta.get("reasons") or [])]
        raw_text = str(ctx.get("raw_text") or "").lower()

        self.assertEqual(str(ctx.get("target_system_name") or ""), "F33_QG_LARGE")
        self.assertTrue(bool(ctx.get("clipboard_target_system_copied")))
        self.assertTrue(bool(ranking_meta.get("ship_pad_filter_applied")))
        self.assertGreaterEqual(int(ranking_meta.get("ship_pad_filtered_out_count") or 0), 1)
        self.assertIn("outpost_rejected_by_ship_constraints", reasons)
        self.assertIn("outpost", raw_text)
        self.assertIn("ograniczenia statku", raw_text)

    def test_smoke_profiles_constraints_and_express_toggle(self) -> None:
        candidates = [
            {
                "name": "F33 QG Nearest Carrier",
                "system_name": "F33_QG_SYS",
                "type": "fleet_carrier",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 4.0,
                "distance_ls": 1800.0,
                "source": "SPANSH",
            },
            {
                "name": "F33 QG Secure Port",
                "system_name": "F33_QG_SYS",
                "type": "station",
                "security": "high",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 9.0,
                "distance_ls": 1100.0,
                "source": "EDSM",
            },
            {
                "name": "F33 QG Express Port",
                "system_name": "F33_QG_SYS",
                "type": "station",
                "security": "medium",
                "services": {"has_uc": True, "has_vista": False},
                "distance_ly": 14.0,
                "distance_ls": 300.0,
                "source": "PLAYERDB",
            },
            {
                "name": "F33 QG Vista Ground",
                "system_name": "F33_QG_SYS",
                "type": "settlement",
                "is_planetary": True,
                "gravity_g": 1.5,
                "security": "high",
                "services": {"has_uc": True, "has_vista": True},
                "distance_ly": 13.0,
                "distance_ls": 1400.0,
                "source": "EDSM",
            },
        ]
        payout = cash_in_assistant._build_payout_contract(
            gross_value=12_000_000.0,
            tariff_percent=5.0,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-03-01T10:00:00Z",
        )

        config.config._settings["cash_in.express_mode_enabled"] = True
        options_on, meta_on = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=payout,
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        profiles = [str(item.get("profile") or "") for item in options_on]
        self.assertEqual(profiles, ["SECURE", "NEAREST", "EXPRESS", "PLANETARY_VISTA"])
        nearest_on = next(item for item in options_on if item.get("profile") == "NEAREST")
        secure_on = next(item for item in options_on if item.get("profile") == "SECURE")
        express_on = next(item for item in options_on if item.get("profile") == "EXPRESS")
        vista_on = next(item for item in options_on if item.get("profile") == "PLANETARY_VISTA")
        self.assertEqual(str((nearest_on.get("target") or {}).get("name") or ""), "F33 QG Nearest Carrier")
        self.assertEqual(str((secure_on.get("target") or {}).get("name") or ""), "F33 QG Secure Port")
        self.assertEqual(str((express_on.get("target") or {}).get("name") or ""), "F33 QG Express Port")
        self.assertEqual(str((vista_on.get("target") or {}).get("name") or ""), "F33 QG Vista Ground")
        self.assertTrue(bool(meta_on.get("express_mode_enabled")))

        config.config._settings["cash_in.express_mode_enabled"] = False
        options_off, meta_off = cash_in_assistant._build_profiled_options(
            service="uc",
            candidates=candidates,
            payout_contract=payout,
            trust_status="TRUST_HIGH",
            confidence="high",
        )
        express_off = next(item for item in options_off if item.get("profile") == "EXPRESS")
        self.assertEqual(str((express_off.get("target") or {}).get("name") or ""), "F33 QG Nearest Carrier")
        self.assertFalse(bool(meta_off.get("express_mode_enabled")))


if __name__ == "__main__":
    unittest.main()

