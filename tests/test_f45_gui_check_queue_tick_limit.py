from __future__ import annotations

import queue
import unittest
from unittest.mock import patch

from gui import app as gui_app
from logic import utils


def _drain_msg_queue() -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    while True:
        try:
            item = utils.MSG_QUEUE.get_nowait()
        except queue.Empty:
            break
        if isinstance(item, tuple) and len(item) == 2:
            items.append((str(item[0]), item[1]))
    return items


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay_ms: int, callback) -> None:
        self.after_calls.append((int(delay_ms), callback))


class _FakePulpit:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def log(self, content) -> None:
        self.logs.append(str(content))


class _FakeRenataApp:
    def __init__(self) -> None:
        self.root = _FakeRoot()
        self.tab_pulpit = _FakePulpit()
        self.check_queue = lambda: None


class F45GuiCheckQueueTickLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        _drain_msg_queue()

    def tearDown(self) -> None:
        _drain_msg_queue()

    def test_check_queue_limits_items_per_tick_and_reschedules_immediately_when_backlog_exists(self) -> None:
        for idx in range(50):
            utils.MSG_QUEUE.put(("log", f"msg-{idx}"))

        fake_app = _FakeRenataApp()

        with patch("gui.app.app_state.refresh_mode_state"):
            gui_app.RenataApp.check_queue(fake_app)

        self.assertEqual(len(fake_app.tab_pulpit.logs), gui_app._QUEUE_TICK_MAX_ITEMS)
        self.assertEqual(len(fake_app.root.after_calls), 1)
        self.assertEqual(fake_app.root.after_calls[0][0], gui_app._QUEUE_TICK_BACKLOG_DELAY_MS)

        remaining = _drain_msg_queue()
        self.assertEqual(len(remaining), 50 - gui_app._QUEUE_TICK_MAX_ITEMS)

    def test_check_queue_uses_idle_delay_when_queue_fully_drained_within_tick(self) -> None:
        for idx in range(3):
            utils.MSG_QUEUE.put(("log", f"small-{idx}"))

        fake_app = _FakeRenataApp()

        with patch("gui.app.app_state.refresh_mode_state"):
            gui_app.RenataApp.check_queue(fake_app)

        self.assertEqual(len(fake_app.tab_pulpit.logs), 3)
        self.assertEqual(len(fake_app.root.after_calls), 1)
        self.assertEqual(fake_app.root.after_calls[0][0], gui_app._QUEUE_TICK_IDLE_DELAY_MS)
        self.assertEqual(_drain_msg_queue(), [])


if __name__ == "__main__":
    unittest.main()
