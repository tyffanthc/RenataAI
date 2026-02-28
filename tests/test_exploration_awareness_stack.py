from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.events import exploration_awareness as awareness


class ExplorationAwarenessStackTests(unittest.TestCase):
    def tearDown(self) -> None:
        awareness.reset_exploration_awareness()

    @staticmethod
    def _config_with_limits(max_per_system: int, max_per_session: int):
        def _getter(key: str, default=None):
            if key == "exploration.awareness.max_callouts_per_system":
                return max_per_system
            if key == "exploration.awareness.max_callouts_per_session":
                return max_per_session
            return default

        return _getter

    def test_emits_summary_once_when_system_limit_is_reached(self) -> None:
        with (
            patch(
                "logic.events.exploration_awareness.config.get",
                side_effect=self._config_with_limits(1, 10),
            ),
            patch("logic.events.exploration_awareness.emit_insight") as emit_mock,
        ):
            first = awareness.emit_callout_or_summary(
                text="Callout A",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="Sol",
                body_name="Sol A 1",
                callout_key="soft:sol_a_1",
            )
            second = awareness.emit_callout_or_summary(
                text="Callout B",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="Sol",
                body_name="Sol A 2",
                callout_key="soft:sol_a_2",
            )
            third = awareness.emit_callout_or_summary(
                text="Callout C",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="Sol",
                body_name="Sol A 3",
                callout_key="soft:sol_a_3",
            )

        self.assertEqual(first, "callout")
        self.assertEqual(second, "summary")
        self.assertEqual(third, "dropped_limit")
        self.assertEqual(emit_mock.call_count, 2)
        self.assertEqual(
            emit_mock.call_args_list[1].kwargs.get("message_id"),
            "MSG.EXPLORATION_AWARENESS_SUMMARY",
        )

        snap = awareness.get_awareness_snapshot("Sol")
        self.assertEqual(snap["callouts_emitted"], 1)
        self.assertTrue(snap["summary_emitted"])
        self.assertEqual(snap["suppressed_count"], 2)

    def test_drops_duplicate_callout_keys(self) -> None:
        with (
            patch(
                "logic.events.exploration_awareness.config.get",
                side_effect=self._config_with_limits(3, 10),
            ),
            patch("logic.events.exploration_awareness.emit_insight") as emit_mock,
        ):
            first = awareness.emit_callout_or_summary(
                text="Callout A",
                message_id="MSG.ELW_DETECTED",
                source="test",
                system_name="Achenar",
                body_name="Achenar 1",
                callout_key="elw:achenar_1",
            )
            duplicate = awareness.emit_callout_or_summary(
                text="Callout A duplicate",
                message_id="MSG.ELW_DETECTED",
                source="test",
                system_name="Achenar",
                body_name="Achenar 1",
                callout_key="elw:achenar_1",
            )

        self.assertEqual(first, "callout")
        self.assertEqual(duplicate, "dropped_duplicate")
        self.assertEqual(emit_mock.call_count, 1)

    def test_session_limit_triggers_summary_for_new_system(self) -> None:
        with (
            patch(
                "logic.events.exploration_awareness.config.get",
                side_effect=self._config_with_limits(5, 2),
            ),
            patch("logic.events.exploration_awareness.emit_insight") as emit_mock,
        ):
            first = awareness.emit_callout_or_summary(
                text="Callout 1",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="SystemA",
                body_name="A1",
                callout_key="k1",
            )
            second = awareness.emit_callout_or_summary(
                text="Callout 2",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="SystemB",
                body_name="B1",
                callout_key="k2",
            )
            third = awareness.emit_callout_or_summary(
                text="Callout 3",
                message_id="MSG.EXOBIO_NEW_ENTRY",
                source="test",
                system_name="SystemC",
                body_name="C1",
                callout_key="k3",
            )

        self.assertEqual(first, "callout")
        self.assertEqual(second, "callout")
        self.assertEqual(third, "summary")
        self.assertEqual(emit_mock.call_count, 3)
        self.assertEqual(
            emit_mock.call_args_list[2].kwargs.get("message_id"),
            "MSG.EXPLORATION_AWARENESS_SUMMARY",
        )


if __name__ == "__main__":
    unittest.main()
