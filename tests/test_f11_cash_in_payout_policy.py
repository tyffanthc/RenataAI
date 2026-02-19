from __future__ import annotations

import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import cash_in_assistant


class F11CashInPayoutPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_system = getattr(app_state, "current_system", None)
        self._saved_last_sig = getattr(app_state, "last_cash_in_signature", None)
        self._saved_skip_sig = getattr(app_state, "cash_in_skip_signature", None)
        app_state.current_system = "F11_CASH_IN_POLICY_TEST_SYSTEM"
        app_state.last_cash_in_signature = None
        app_state.cash_in_skip_signature = None

    def tearDown(self) -> None:
        app_state.current_system = self._saved_system
        app_state.last_cash_in_signature = self._saved_last_sig
        app_state.cash_in_skip_signature = self._saved_skip_sig

    def test_uc_fleet_carrier_has_fixed_25_fee_and_tariff_is_meta_only(self) -> None:
        contract = cash_in_assistant._build_payout_contract(
            gross_value=10_000_000.0,
            tariff_percent=15.0,
            vista_fc_policy_mode="ASSUMED_100",
            freshness_ts="2026-02-19T19:00:00Z",
        )
        uc_fc = dict((contract.get("contracts") or {}).get("uc_fleet_carrier") or {})

        self.assertEqual(uc_fc.get("service"), "UC")
        self.assertEqual(uc_fc.get("target_type"), "fleet_carrier")
        self.assertEqual(uc_fc.get("status"), "CONFIRMED")
        self.assertEqual(int(uc_fc.get("brutto") or 0), 10_000_000)
        self.assertEqual(int(uc_fc.get("fee") or 0), 2_500_000)
        self.assertEqual(int(uc_fc.get("netto") or 0), 7_500_000)
        self.assertFalse(bool((uc_fc.get("tariff_meta") or {}).get("applies_to_payout")))
        self.assertEqual(float((uc_fc.get("tariff_meta") or {}).get("tariff_percent") or 0.0), 15.0)

    def test_vista_fleet_carrier_unknown_falls_back_to_assumed_100(self) -> None:
        contract = cash_in_assistant._build_payout_contract(
            gross_value=8_000_000.0,
            tariff_percent=None,
            vista_fc_policy_mode="UNKNOWN",
            freshness_ts="2026-02-19T20:00:00Z",
        )
        vista_fc = dict((contract.get("contracts") or {}).get("vista_fleet_carrier") or {})

        self.assertEqual(vista_fc.get("service"), "VISTA")
        self.assertEqual(vista_fc.get("target_type"), "fleet_carrier")
        self.assertEqual(vista_fc.get("status"), "UNKNOWN")
        self.assertTrue(bool(vista_fc.get("assumption")))
        self.assertTrue(bool(vista_fc.get("fallback_applied")))
        self.assertEqual(int(vista_fc.get("brutto") or 0), 8_000_000)
        self.assertEqual(int(vista_fc.get("fee") or 0), 0)
        self.assertEqual(int(vista_fc.get("netto") or 0), 8_000_000)

    def test_trigger_payload_contains_runtime_brutto_fee_netto_contract(self) -> None:
        payload = {
            "system": "F11_CASH_IN_POLICY_TEST_SYSTEM",
            "cash_in_signal": "wysoki",
            "cash_in_system_estimated": 6_000_000.0,
            "cash_in_session_estimated": 14_000_000.0,
            "tariff_percent": 8.5,
            "vista_fc_policy_mode": "UNKNOWN",
            "freshness_ts": "2026-02-19T21:00:00Z",
        }
        with patch("logic.events.cash_in_assistant.emit_insight") as emit_mock:
            ok = cash_in_assistant.trigger_cash_in_assistant(mode="manual", summary_payload=payload)

        self.assertTrue(ok)
        self.assertEqual(emit_mock.call_count, 1)
        ctx = dict(emit_mock.call_args.kwargs.get("context") or {})
        structured = dict(ctx.get("cash_in_payload") or {})
        payout = dict(structured.get("payout_contract") or {})
        self.assertIn("brutto", payout)
        self.assertIn("fee", payout)
        self.assertIn("netto", payout)
        contracts = dict(payout.get("contracts") or {})
        self.assertIn("uc_fleet_carrier", contracts)
        self.assertIn("vista_fleet_carrier", contracts)


if __name__ == "__main__":
    unittest.main()

