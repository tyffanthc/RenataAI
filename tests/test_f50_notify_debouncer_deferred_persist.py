from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
