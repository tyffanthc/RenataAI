from __future__ import annotations

import unittest
from unittest.mock import patch

from gui import app as gui_app


class _FakeRootTimers:
    def __init__(self) -> None:
        self._seq = 0
        self.after_calls: list[tuple[int, int, object]] = []
        self.after_cancel_calls: list[int] = []
        self.quit_calls = 0

    def after(self, delay_ms: int, callback):
        self._seq += 1
        timer_id = int(self._seq)
        self.after_calls.append((timer_id, int(delay_ms), callback))
        return timer_id

    def after_cancel(self, timer_id) -> None:
        self.after_cancel_calls.append(int(timer_id))

    def quit(self) -> None:
        self.quit_calls += 1


class F52GuiAfterTimerLifecycleContractTests(unittest.TestCase):
    def test_debug_panel_schedule_cancels_previous_timer(self) -> None:
        fake = type("FakeApp", (), {})()
        fake.root = _FakeRootTimers()
        fake._debug_panel_enabled = True
        fake._debug_panel_refresh_ms = 400
        fake._debug_panel_after_id = None
        fake._update_debug_panel = lambda: None
        fake._cancel_debug_panel_update = lambda: gui_app.RenataApp._cancel_debug_panel_update(fake)

        gui_app.RenataApp._schedule_debug_panel_update(fake)
        first_id = int(fake._debug_panel_after_id)
        gui_app.RenataApp._schedule_debug_panel_update(fake)
        second_id = int(fake._debug_panel_after_id)

        self.assertNotEqual(first_id, second_id)
        self.assertIn(first_id, fake.root.after_cancel_calls)
        self.assertEqual(len(fake.root.after_calls), 2)
        self.assertEqual(fake.root.after_calls[0][1], 400)
        self.assertEqual(fake.root.after_calls[1][1], 400)

    def test_queue_schedule_cancels_previous_timer(self) -> None:
        fake = type("FakeApp", (), {})()
        fake.root = _FakeRootTimers()
        fake._queue_check_after_id = None
        fake.check_queue = lambda: None
        fake._cancel_queue_check = lambda: gui_app.RenataApp._cancel_queue_check(fake)

        gui_app.RenataApp._schedule_queue_check(fake, 100)
        first_id = int(fake._queue_check_after_id)
        gui_app.RenataApp._schedule_queue_check(fake, 250)
        second_id = int(fake._queue_check_after_id)

        self.assertNotEqual(first_id, second_id)
        self.assertIn(first_id, fake.root.after_cancel_calls)
        self.assertEqual([delay for _, delay, _ in fake.root.after_calls], [100, 250])

    def test_main_close_cancels_timers_before_quit(self) -> None:
        fake = type("FakeApp", (), {})()
        fake.root = _FakeRootTimers()
        fake._debug_panel_after_id = 11
        fake._queue_check_after_id = 22
        fake._cancel_debug_panel_update = lambda: gui_app.RenataApp._cancel_debug_panel_update(fake)
        fake._cancel_queue_check = lambda: gui_app.RenataApp._cancel_queue_check(fake)

        with patch("gui.app.save_window_geometry"):
            gui_app.RenataApp._on_main_close(fake)

        self.assertIn(11, fake.root.after_cancel_calls)
        self.assertIn(22, fake.root.after_cancel_calls)
        self.assertEqual(fake.root.quit_calls, 1)
        self.assertIsNone(fake._debug_panel_after_id)
        self.assertIsNone(fake._queue_check_after_id)


if __name__ == "__main__":
    unittest.main()
