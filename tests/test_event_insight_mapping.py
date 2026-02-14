from __future__ import annotations

import unittest

from logic.event_insight_mapping import get_insight_class, resolve_emit_contract


class EventInsightMappingTests(unittest.TestCase):
    def test_required_core_message_ids_have_mapping(self) -> None:
        required = [
            "MSG.NEXT_HOP",
            "MSG.JUMPED_SYSTEM",
            "MSG.DOCKED",
            "MSG.UNDOCKED",
            "MSG.FUEL_CRITICAL",
            "MSG.FSS_PROGRESS_25",
            "MSG.FSS_PROGRESS_50",
            "MSG.FSS_PROGRESS_75",
            "MSG.FSS_LAST_BODY",
            "MSG.SYSTEM_FULLY_SCANNED",
            "MSG.FIRST_DISCOVERY_OPPORTUNITY",
            "MSG.DSS_TARGET_HINT",
            "MSG.DSS_COMPLETED",
            "MSG.DSS_PROGRESS",
            "MSG.FIRST_MAPPED",
            "MSG.EXOBIO_SAMPLE_LOGGED",
            "MSG.EXOBIO_RANGE_READY",
            "MSG.EXOBIO_NEW_ENTRY",
        ]
        for message_id in required:
            spec = get_insight_class(message_id)
            self.assertIsNotNone(spec, f"Missing mapping for {message_id}")
            assert spec is not None
            self.assertTrue(spec.canonical_event)
            self.assertTrue(spec.kind)
            self.assertTrue(spec.decision_space)

    def test_resolve_emit_contract_applies_defaults_from_mapping(self) -> None:
        result = resolve_emit_contract(
            message_id="MSG.FSS_PROGRESS_25",
            context={"system": "SOL"},
            event_type="SYSTEM_SCANNED",
            dedup_key=None,
            priority=None,
            cooldown_scope=None,
            cooldown_seconds=None,
        )
        self.assertEqual(result["priority"], "P2_NORMAL")
        self.assertEqual(result["cooldown_scope"], "entity")
        self.assertEqual(result["cooldown_seconds"], 120.0)
        self.assertEqual(result["dedup_key"], "fss25:SOL")
        ctx = result.get("context") or {}
        self.assertEqual(ctx.get("canonical_event"), "SYSTEM_SCANNED")
        self.assertEqual(ctx.get("insight_kind"), "exploration")
        self.assertEqual(ctx.get("decision_space"), "scan_progress")


if __name__ == "__main__":
    unittest.main()
