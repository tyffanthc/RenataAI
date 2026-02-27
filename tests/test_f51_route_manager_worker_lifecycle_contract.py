from __future__ import annotations

import threading
import time
import unittest

from app.route_manager import RouteManager


class F51RouteManagerWorkerLifecycleContractTests(unittest.TestCase):
    @staticmethod
    def _wait_until(predicate, *, timeout: float = 1.5, step: float = 0.01) -> bool:
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            if bool(predicate()):
                return True
            time.sleep(step)
        return bool(predicate())

    def test_start_route_thread_rejects_second_start_while_busy(self) -> None:
        manager = RouteManager(route_job_timeout_s=2.0)
        gate = threading.Event()
        started = threading.Event()

        def _slow_job() -> None:
            started.set()
            gate.wait(1.0)

        self.assertTrue(manager.start_route_thread("trade", _slow_job))
        self.assertTrue(started.wait(0.3))
        self.assertTrue(manager.is_busy())
        self.assertEqual(str(manager.current_mode() or ""), "trade")

        self.assertFalse(manager.start_route_thread("neutron", lambda: None))
        self.assertEqual(str(manager.current_mode() or ""), "trade")

        gate.set()
        self.assertTrue(self._wait_until(lambda: not manager.is_busy(), timeout=1.0))

    def test_timeout_watchdog_releases_busy_state_for_hung_job(self) -> None:
        manager = RouteManager(route_job_timeout_s=0.06)
        gate = threading.Event()
        started = threading.Event()

        def _hung_job() -> None:
            started.set()
            gate.wait(1.5)

        self.assertTrue(manager.start_route_thread("trade", _hung_job))
        self.assertTrue(started.wait(0.3))
        old_worker = manager._worker_thread
        self.assertIsNotNone(old_worker)

        self.assertTrue(self._wait_until(lambda: not manager.is_busy(), timeout=0.8))
        self.assertIsNone(manager.current_mode())
        self.assertTrue(bool(old_worker and old_worker.is_alive()))

        quick_done = threading.Event()
        self.assertTrue(manager.start_route_thread("neutron", lambda: quick_done.set()))
        self.assertTrue(quick_done.wait(0.4))
        self.assertTrue(self._wait_until(lambda: not manager.is_busy(), timeout=0.8))

        gate.set()
        if old_worker is not None:
            old_worker.join(timeout=0.8)

    def test_timed_out_old_job_completion_does_not_clobber_new_busy_state(self) -> None:
        manager = RouteManager(route_job_timeout_s=0.06)
        old_gate = threading.Event()
        new_gate = threading.Event()
        old_started = threading.Event()
        new_started = threading.Event()
        old_done = threading.Event()
        new_done = threading.Event()

        def _old_job() -> None:
            try:
                old_started.set()
                old_gate.wait(1.5)
            finally:
                old_done.set()

        def _new_job() -> None:
            try:
                new_started.set()
                new_gate.wait(1.5)
            finally:
                new_done.set()

        self.assertTrue(manager.start_route_thread("trade", _old_job))
        self.assertTrue(old_started.wait(0.3))
        self.assertTrue(self._wait_until(lambda: not manager.is_busy(), timeout=0.8))

        self.assertTrue(manager.start_route_thread("neutron", _new_job))
        self.assertTrue(new_started.wait(0.3))
        self.assertTrue(manager.is_busy())
        self.assertEqual(str(manager.current_mode() or ""), "neutron")

        old_gate.set()
        self.assertTrue(old_done.wait(0.4))
        self.assertTrue(manager.is_busy())
        self.assertEqual(str(manager.current_mode() or ""), "neutron")

        new_gate.set()
        self.assertTrue(new_done.wait(0.4))
        self.assertTrue(self._wait_until(lambda: not manager.is_busy(), timeout=0.8))
        self.assertIsNone(manager.current_mode())


if __name__ == "__main__":
    unittest.main()
