from __future__ import annotations

import time
import unittest

from logic.event_insight_mapping import get_tts_policy_spec
from logic.insight_dispatcher import Insight, _apply_priority_matrix
from logic import insight_dispatcher


class F36ExobioSpeciesCompleteVoicePriorityTests(unittest.TestCase):
    def test_species_complete_policy_is_always_say(self) -> None:
        policy = get_tts_policy_spec("MSG.EXOBIO_SPECIES_COMPLETE")
        self.assertEqual(policy.intent, "context")
        self.assertEqual(policy.category, "explore")
        self.assertEqual(policy.cooldown_policy, "ALWAYS_SAY")

    def test_bypass_priority_matrix_context_prevents_matrix_suppression(self) -> None:
        insight = Insight(
            text="complete",
            message_id="MSG.EXOBIO_SPECIES_COMPLETE",
            source="exploration_bio_events",
            context={"bypass_priority_matrix": True},
            priority="P1_HIGH",
        )
        insight_dispatcher._PRIORITY_MATRIX_RUNTIME["last_voice"] = {
            "message_id": "MSG.EXOBIO_SAMPLE_LOGGED",
            "module_class": "EXPLORATION",
            "class_rank": 2,
            "priority_rank": 1,
            "ts": time.monotonic(),
        }
        allow_tts, allow_reason, forced = _apply_priority_matrix(
            insight,
            allow_tts=True,
            allow_reason="notify_policy_allow",
        )
        self.assertTrue(allow_tts)
        self.assertEqual(allow_reason, "bypass_priority_matrix")
        self.assertFalse(forced)
        insight_dispatcher._PRIORITY_MATRIX_RUNTIME.pop("last_voice", None)


if __name__ == "__main__":
    unittest.main()

