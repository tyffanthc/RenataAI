from __future__ import annotations

import os
import tempfile
import unittest

import config
from logic.context_state_contract import default_state_contract, load_state_contract_file


class F10DomainStateLastContextTests(unittest.TestCase):
    def test_last_context_persists_in_domain_state(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_domain_last_context.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())

                payload = {
                    "route": ["Diaguandri", "Njulngan"],
                    "text": "Route: Diaguandri\nNjulngan",
                    "sig": "trade.abc123",
                    "source": "trade",
                    "updated_at": 123,
                }
                config.update_last_context(
                    last_route=payload,
                    last_commodity={
                        "name": "Platinum",
                        "from_system": "Diaguandri",
                        "to_system": "Njulngan",
                        "source": "spansh.trade.selection",
                        "updated_at": "2026-02-19T20:30:00",
                    },
                    last_plan_id="trade:abc123",
                )

                context = config.get_last_context()
                self.assertEqual((context.get("last_route") or {}).get("sig"), "trade.abc123")
                self.assertEqual((context.get("last_commodity") or {}).get("name"), "Platinum")
                self.assertEqual(context.get("last_plan_id"), "trade:abc123")

                persisted = load_state_contract_file(tmp_path)
                domain_state = persisted.get("domain_state") or {}
                self.assertEqual((domain_state.get("last_route") or {}).get("source"), "trade")
                self.assertEqual((domain_state.get("last_commodity") or {}).get("name"), "Platinum")
                self.assertEqual(domain_state.get("last_plan_id"), "trade:abc123")
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_last_route_restore_hook_loads_persisted_payload(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_domain_last_route_restore.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())
                config.update_last_context(
                    last_route={
                        "route": ["Sol", "Achenar"],
                        "text": "Route: Sol\nAchenar",
                        "sig": "route.sig.restore",
                        "source": "neutron",
                        "updated_at": 555,
                    },
                    last_plan_id="neutron:route.sig.restore",
                )

                from gui import common_route_progress as route_progress

                route_progress.set_last_route_data([], "", "")
                restored = route_progress.load_last_route_context_from_domain_state(force=True)
                self.assertTrue(restored)
                self.assertEqual(route_progress.get_last_route_systems(), ["Sol", "Achenar"])
                self.assertEqual(route_progress.get_last_route_text(), "Route: Sol\nAchenar")
                self.assertEqual(route_progress.get_last_route_sig(), "route.sig.restore")
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_domain_context_hooks_present_in_gui_modules(self) -> None:
        project_root = os.path.dirname(os.path.dirname(__file__))
        route_progress_path = os.path.join(project_root, "gui", "common_route_progress.py")
        trade_path = os.path.join(project_root, "gui", "tabs", "spansh", "trade.py")

        with open(route_progress_path, "r", encoding="utf-8", errors="ignore") as handle:
            route_progress_content = handle.read()
        self.assertIn("_persist_last_route_context", route_progress_content)
        self.assertIn("load_last_route_context_from_domain_state()", route_progress_content)
        self.assertIn("config.update_last_context(last_route=payload, last_plan_id=plan_id)", route_progress_content)

        with open(trade_path, "r", encoding="utf-8", errors="ignore") as handle:
            trade_content = handle.read()
        self.assertIn("def _persist_last_commodity_context", trade_content)
        self.assertIn("config.update_last_context(last_commodity=payload)", trade_content)


if __name__ == "__main__":
    unittest.main()
