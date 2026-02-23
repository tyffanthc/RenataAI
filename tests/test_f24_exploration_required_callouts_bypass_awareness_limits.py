from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.events import exploration_awareness as awareness


class F24ExplorationRequiredCalloutsBypassAwarenessLimitsTests(unittest.TestCase):
    def tearDown(self) -> None:
        awareness.reset_exploration_awareness()

    @staticmethod
    def _limits(max_per_system: int, max_per_session: int):
        def _getter(key: str, default=None):
            if key == "exploration.awareness.max_callouts_per_system":
                return max_per_system
            if key == "exploration.awareness.max_callouts_per_session":
                return max_per_session
            return default
        return _getter

    def test_required_callouts_bypass_limits_but_keep_dedupe(self) -> None:
        with (
            patch("logic.events.exploration_awareness.config.get", side_effect=self._limits(1, 1)),
            patch("logic.events.exploration_awareness.emit_insight") as emit_mock,
        ):
            # Consume the soft-callout budget.
            a = awareness.emit_callout_or_summary(
                text="Soft",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="SOL",
                body_name="SOL A 1",
                callout_key="soft:a",
            )
            # Required callouts should still pass.
            b = awareness.emit_callout_or_summary(
                text="ELW",
                message_id="MSG.ELW_DETECTED",
                source="test",
                system_name="SOL",
                body_name="SOL A 2",
                callout_key="elw:sol_a_2",
            )
            c = awareness.emit_callout_or_summary(
                text="DSS",
                message_id="MSG.DSS_TARGET_HINT",
                source="test",
                system_name="SOL",
                body_name="SOL A 3",
                callout_key="dss:sol_a_3",
            )
            d = awareness.emit_callout_or_summary(
                text="BIO",
                message_id="MSG.BIO_SIGNALS_HIGH",
                source="test",
                system_name="SOL",
                body_name="SOL A 4",
                callout_key="bio:sol_a_4",
            )
            dup = awareness.emit_callout_or_summary(
                text="BIO duplicate",
                message_id="MSG.BIO_SIGNALS_HIGH",
                source="test",
                system_name="SOL",
                body_name="SOL A 4",
                callout_key="bio:sol_a_4",
            )

        self.assertEqual(a, "callout")
        self.assertEqual(b, "callout")
        self.assertEqual(c, "callout")
        self.assertEqual(d, "callout")
        self.assertEqual(dup, "dropped_duplicate")

        ids = [call.kwargs.get("message_id") for call in emit_mock.call_args_list]
        self.assertEqual(ids, ["MSG.EXOBIO_NEW_ENTRY", "MSG.ELW_DETECTED", "MSG.DSS_TARGET_HINT", "MSG.BIO_SIGNALS_HIGH"])
        self.assertNotIn("MSG.EXPLORATION_SYSTEM_SUMMARY", ids)

        snap = awareness.get_awareness_snapshot("SOL")
        # Required callouts do not consume the awareness budget.
        self.assertEqual(int(snap.get("callouts_emitted") or 0), 1)
        self.assertFalse(bool(snap.get("summary_emitted")))


if __name__ == "__main__":
    unittest.main()
