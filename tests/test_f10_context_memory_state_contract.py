from __future__ import annotations

import os
import tempfile
import unittest

import config
from logic.context_state_contract import (
    STATE_SCHEMA_VERSION,
    default_state_contract,
    load_state_contract_file,
    migrate_state_contract_payload,
    restart_loss_audit_contract,
    save_state_contract_file,
)


class F10ContextMemoryStateContractTests(unittest.TestCase):
    def test_migrates_legacy_flat_state_payload_to_layered_contract(self) -> None:
        legacy_payload = {
            "sys": "Sol",
            "milestones": ["Alpha", "Beta"],
            "route_mode": "awareness",
        }

        migrated = migrate_state_contract_payload(legacy_payload)

        self.assertEqual(migrated.get("schema_version"), STATE_SCHEMA_VERSION)
        self.assertIsInstance(migrated.get("ui_state"), dict)
        self.assertIsInstance(migrated.get("preferences"), dict)
        self.assertIsInstance(migrated.get("domain_state"), dict)
        self.assertIsInstance(migrated.get("anti_spam_state"), dict)
        self.assertEqual(migrated["domain_state"].get("sys"), "Sol")
        self.assertEqual(migrated["domain_state"].get("route_mode"), "awareness")

    def test_incompatible_future_schema_falls_back_gracefully(self) -> None:
        future_payload = {
            "schema_version": STATE_SCHEMA_VERSION + 9,
            "ui_state": {"active_tab": "Pulpit"},
            "domain_state": {"sys": "Colonia"},
            "preferences": {"tts_enabled": True},
            "anti_spam_state": {"fss": {"seen": ["X"]}},
        }

        migrated = migrate_state_contract_payload(future_payload)

        self.assertEqual(migrated.get("schema_version"), STATE_SCHEMA_VERSION)
        self.assertEqual(migrated["ui_state"].get("active_tab"), "Pulpit")
        self.assertEqual(migrated["domain_state"].get("sys"), "Colonia")
        self.assertTrue(bool(migrated["preferences"].get("tts_enabled")))

    def test_guardrails_strip_personal_keys(self) -> None:
        payload = default_state_contract()
        payload["domain_state"].update(
            {
                "sys": "Achenar",
                "commander_name": "Cmdr Test",
                "email": "cmdr@example.test",
                "machine_id": "HWID-123",
            }
        )
        payload["preferences"]["user_name"] = "PrivateName"

        migrated = migrate_state_contract_payload(payload)

        self.assertEqual(migrated["domain_state"].get("sys"), "Achenar")
        self.assertNotIn("commander_name", migrated["domain_state"])
        self.assertNotIn("email", migrated["domain_state"])
        self.assertNotIn("machine_id", migrated["domain_state"])
        self.assertNotIn("user_name", migrated["preferences"])

    def test_file_roundtrip_preserves_layered_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "app_state.json")
            contract = default_state_contract()
            contract["ui_state"]["active_tab"] = "Pulpit"
            contract["preferences"]["tts_enabled"] = True
            contract["domain_state"]["sys"] = "Sagittarius A*"
            contract["anti_spam_state"]["fss"] = {"last_key": "sample"}

            expected = save_state_contract_file(path, contract)
            loaded = load_state_contract_file(path)

            self.assertEqual(loaded, expected)

    def test_restart_loss_audit_contract_contains_required_candidates(self) -> None:
        audit = restart_loss_audit_contract()
        required = {
            "exobio_sample_state",
            "fss_progress_and_first_discovery_flags",
            "dss_high_value_footfall_callout_flags",
            "route_milestone_progress_cache",
            "trade_jackpot_cache",
            "smuggler_warned_targets",
            "dispatcher_debouncer_windows",
            "combat_survival_pattern_runtime",
        }
        self.assertTrue(required.issubset(set(audit.keys())))
        for candidate in required:
            decision = str((audit.get(candidate) or {}).get("decision") or "")
            self.assertIn(decision, {"persist", "session-only"})

    def test_config_state_runtime_persists_into_layered_contract(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f10_state.json")
            try:
                config.STATE_FILE = tmp_path
                config.save_state_contract(default_state_contract())

                config.STATE["sys"] = "F10_TEST_SYSTEM"
                config.STATE["route_mode"] = "intent"
                persisted = config.persist_runtime_state()

                self.assertEqual(
                    persisted["domain_state"].get("sys"),
                    "F10_TEST_SYSTEM",
                )
                self.assertEqual(
                    persisted["domain_state"].get("route_mode"),
                    "intent",
                )

                loaded = load_state_contract_file(tmp_path)
                self.assertEqual(loaded["domain_state"].get("sys"), "F10_TEST_SYSTEM")
                self.assertEqual(loaded["domain_state"].get("route_mode"), "intent")
            finally:
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)


if __name__ == "__main__":
    unittest.main()
