import queue
import unittest

from gui import common_route_progress as route_progress
from logic.utils import MSG_QUEUE


def _drain_queue() -> list:
    items = []
    try:
        while True:
            items.append(MSG_QUEUE.get_nowait())
    except queue.Empty:
        return items


class GuiStatusHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        _drain_queue()

    def tearDown(self) -> None:
        _drain_queue()

    def test_emit_status_includes_source_in_log_and_ui_status(self) -> None:
        route_progress.emit_status(
            "WARN",
            "ROUTE_ERROR",
            "Boom",
            source="spansh.riches",
            ui_target="rtr",
            notify_overlay=True,
        )

        items = _drain_queue()
        by_type = {}
        for msg_type, payload in items:
            by_type.setdefault(msg_type, []).append(payload)

        self.assertIn("status_event", by_type)
        self.assertIn("log", by_type)
        self.assertIn("status_rtr", by_type)

        event = by_type["status_event"][-1]
        self.assertEqual(event.get("code"), "ROUTE_ERROR")
        self.assertEqual(event.get("source"), "spansh.riches")

        log_line = by_type["log"][-1]
        self.assertIn("ROUTE_ERROR", log_line)
        self.assertIn("(spansh.riches)", log_line)

        status_text, status_color = by_type["status_rtr"][-1]
        self.assertEqual(status_text, "Boom")
        self.assertEqual(status_color, "orange")

    def test_emit_status_uses_default_text_and_unspecified_source(self) -> None:
        route_progress.emit_status(
            "INFO",
            "ROUTE_FOUND",
            source=None,
            notify_overlay=False,
        )

        items = _drain_queue()
        types = [msg_type for msg_type, _payload in items]
        self.assertNotIn("status_event", types)
        self.assertIn("log", types)

        log_line = [payload for msg_type, payload in items if msg_type == "log"][-1]
        self.assertIn("(unspecified)", log_line)
        self.assertIn(route_progress.STATUS_TEXTS["ROUTE_FOUND"], log_line)


if __name__ == "__main__":
    unittest.main()
