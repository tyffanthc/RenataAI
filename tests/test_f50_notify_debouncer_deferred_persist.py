from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from logic.utils import notify as notify_module


class _FakeTimer:
    created: list["_FakeTimer"] = []

    def __init__(self, delay: float, fn):
        self.delay = float(delay)
        self.fn = fn
        self.daemon = False
        self._started = False
        self._canceled = False
        _FakeTimer.created.append(self)

    def start(self) -> None:
        self._started = True

    def is_alive(self) -> bool:
        return self._started and not self._canceled

    def cancel(self) -> None:
        self._canceled = True


class F50NotifyDebouncerDeferredPersistTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeTimer.created = []

    def test_can_send_defers_subsequent_persist_via_timer(self) -> None:
        debouncer = notify_module.NotificationDebouncer()
        with debouncer._lock:
            debouncer._loaded_from_contract = True

        with (
            patch("logic.utils.notify.config.update_anti_spam_state") as update_mock,
            patch.object(notify_module.NotificationDebouncer, "_persist_min_interval_sec", return_value=0.0),
            patch("logic.utils.notify.threading.Timer", side_effect=lambda d, f: _FakeTimer(d, f)),
        ):
            self.assertTrue(debouncer.can_send("F50_A", 10.0))
            self.assertEqual(update_mock.call_count, 1, "First persist should remain synchronous.")
            self.assertEqual(len(_FakeTimer.created), 0, "No timer needed for first persist.")

            self.assertTrue(debouncer.can_send("F50_B", 10.0))
            self.assertEqual(
                update_mock.call_count,
                1,
                "Second changed key should not persist synchronously on caller path.",
            )
            self.assertEqual(len(_FakeTimer.created), 1, "Expected deferred persist timer to be scheduled.")
            self.assertTrue(_FakeTimer.created[0]._started)

            _FakeTimer.created[0].fn()
            self.assertGreaterEqual(update_mock.call_count, 2, "Timer callback should flush deferred persist.")

        debouncer.reset()

    def test_burst_can_send_batches_persist_off_caller_path_after_first_write(self) -> None:
        debouncer = notify_module.NotificationDebouncer()
        with debouncer._lock:
            debouncer._loaded_from_contract = True

        with (
            patch("logic.utils.notify.config.update_anti_spam_state") as update_mock,
            patch.object(notify_module.NotificationDebouncer, "_persist_min_interval_sec", return_value=0.0),
            patch("logic.utils.notify.threading.Timer", side_effect=lambda d, f: _FakeTimer(d, f)),
        ):
            for i in range(50):
                self.assertTrue(debouncer.can_send(f"F50_BURST_{i}", 10.0))

            self.assertEqual(
                update_mock.call_count,
                1,
                "Burst should keep only the first persist on caller path.",
            )
            self.assertEqual(len(_FakeTimer.created), 1, "Burst should coalesce into a single pending timer.")
            self.assertTrue(_FakeTimer.created[0]._started)
            self.assertGreaterEqual(_FakeTimer.created[0].delay, 0.0)

            _FakeTimer.created[0].fn()
            self.assertGreaterEqual(update_mock.call_count, 2, "Deferred timer should flush burst changes.")

        debouncer.reset()

    def test_stale_timer_callback_after_reset_is_ignored(self) -> None:
        debouncer = notify_module.NotificationDebouncer()
        with debouncer._lock:
            debouncer._loaded_from_contract = True

        with (
            patch("logic.utils.notify.config.update_anti_spam_state") as update_mock,
            patch.object(notify_module.NotificationDebouncer, "_persist_min_interval_sec", return_value=0.0),
            patch("logic.utils.notify.threading.Timer", side_effect=lambda d, f: _FakeTimer(d, f)),
        ):
            self.assertTrue(debouncer.can_send("F50_RESET_A", 10.0))
            self.assertTrue(debouncer.can_send("F50_RESET_B", 10.0))
            self.assertEqual(update_mock.call_count, 1)
            self.assertEqual(len(_FakeTimer.created), 1)
            stale_timer = _FakeTimer.created[0]

            debouncer.reset()
            self.assertTrue(stale_timer._canceled)

            stale_timer.fn()
            self.assertEqual(
                update_mock.call_count,
                1,
                "Canceled/stale timer callback should not persist stale debouncer payload after reset.",
            )

            _FakeTimer.created = []
            with debouncer._lock:
                debouncer._loaded_from_contract = True
            self.assertTrue(debouncer.can_send("F50_RESET_C", 10.0))
            self.assertEqual(update_mock.call_count, 2)

        debouncer.reset()

    def test_burst_can_send_after_first_write_stays_fast_under_slow_persist_io(self) -> None:
        debouncer = notify_module.NotificationDebouncer()
        with debouncer._lock:
            debouncer._loaded_from_contract = True

        def _slow_update(_patch):
            time.sleep(0.03)
            return {}

        with (
            patch("logic.utils.notify.config.update_anti_spam_state", side_effect=_slow_update) as update_mock,
            patch.object(notify_module.NotificationDebouncer, "_persist_min_interval_sec", return_value=2.0),
            patch("logic.utils.notify.threading.Timer", side_effect=lambda d, f: _FakeTimer(d, f)),
        ):
            t_first_start = time.perf_counter()
            self.assertTrue(debouncer.can_send("F50_LATENCY_0", 10.0))
            t_first_elapsed = time.perf_counter() - t_first_start

            t_burst_start = time.perf_counter()
            for i in range(1, 50):
                self.assertTrue(debouncer.can_send(f"F50_LATENCY_{i}", 10.0))
            t_burst_elapsed = time.perf_counter() - t_burst_start

            self.assertGreaterEqual(t_first_elapsed, 0.025, "First write should include simulated slow persist I/O.")
            self.assertLess(
                t_burst_elapsed,
                0.35,
                "Burst caller-path should stay responsive (deferred persist instead of per-call sync I/O).",
            )
            self.assertEqual(
                update_mock.call_count,
                1,
                "After first write, burst should not trigger additional synchronous contract writes.",
            )
            self.assertEqual(len(_FakeTimer.created), 1, "Burst should keep a single deferred timer pending.")

        debouncer.reset()


if __name__ == "__main__":
    unittest.main()
