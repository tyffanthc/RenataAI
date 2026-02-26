from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from app.state import app_state
from logic.events import cash_in_assistant


class F49AppStateRuntimeLockAccessorsAndHotspotsTests(unittest.TestCase):
    def setUp(self) -> None:
        with app_state.lock:
            self._saved_bootstrap_replay = bool(getattr(app_state, "bootstrap_replay", False))
            self._saved_current_system = str(getattr(app_state, "current_system", "") or "")
            self._saved_has_live_system_event = bool(getattr(app_state, "has_live_system_event", False))

    def tearDown(self) -> None:
        with app_state.lock:
            app_state.bootstrap_replay = self._saved_bootstrap_replay
            app_state.current_system = self._saved_current_system
            app_state.has_live_system_event = self._saved_has_live_system_event

    def test_app_state_runtime_accessors_roundtrip(self) -> None:
        app_state.set_bootstrap_replay(True)
        self.assertTrue(app_state.is_bootstrap_replay())

        app_state.set_bootstrap_replay(False)
        self.assertFalse(app_state.is_bootstrap_replay())

        with app_state.lock:
            app_state.current_system = "F49_TEST_SYSTEM"
            app_state.has_live_system_event = True

        self.assertEqual(app_state.get_current_system_name(), "F49_TEST_SYSTEM")
        self.assertTrue(app_state.has_live_system_event_flag())

    def test_detect_offline_or_interrupted_uses_app_state_helpers(self) -> None:
        with (
            patch.object(app_state, "is_bootstrap_replay", return_value=False) as bootstrap_mock,
            patch.object(app_state, "has_live_system_event_flag", return_value=False) as live_mock,
            patch.object(app_state, "get_current_system_name", return_value="unknown") as system_mock,
        ):
            self.assertTrue(cash_in_assistant._detect_offline_or_interrupted({}))

        bootstrap_mock.assert_called_once()
        live_mock.assert_called_once()
        system_mock.assert_called_once()

    def test_startjump_callout_bootstrap_guard_uses_accessor(self) -> None:
        with (
            patch.object(app_state, "is_bootstrap_replay", return_value=True) as bootstrap_mock,
            patch.object(app_state, "get_current_system_name") as system_mock,
        ):
            ok = cash_in_assistant.trigger_startjump_cash_in_callout(
                event={"event": "StartJump", "JumpType": "Hyperspace"},
                gui_ref=None,
            )

        self.assertFalse(ok)
        bootstrap_mock.assert_called_once()
        system_mock.assert_not_called()

    def test_app_state_accessors_thread_stress_smoke(self) -> None:
        errors: list[BaseException] = []
        bootstrap_reads: list[bool] = []
        system_reads: list[str] = []
        live_reads: list[bool] = []
        start_barrier = threading.Barrier(3)

        def writer() -> None:
            try:
                start_barrier.wait(timeout=2.0)
                for i in range(3000):
                    app_state.set_bootstrap_replay(bool(i % 2))
                    with app_state.lock:
                        app_state.current_system = f"F49_SYS_{i % 17}"
                        app_state.has_live_system_event = bool((i // 3) % 2)
                    if i % 17 == 0:
                        threading.Event().wait(0.0)
            except BaseException as exc:  # pragma: no cover - captured for assertion
                errors.append(exc)

        def reader() -> None:
            try:
                start_barrier.wait(timeout=2.0)
                for _ in range(3000):
                    bootstrap_reads.append(app_state.is_bootstrap_replay())
                    system_reads.append(app_state.get_current_system_name())
                    live_reads.append(app_state.has_live_system_event_flag())
            except BaseException as exc:  # pragma: no cover - captured for assertion
                errors.append(exc)

        t_writer = threading.Thread(target=writer, daemon=True)
        t_reader = threading.Thread(target=reader, daemon=True)
        t_writer.start()
        t_reader.start()
        start_barrier.wait(timeout=2.0)
        t_writer.join(timeout=5.0)
        t_reader.join(timeout=5.0)

        self.assertFalse(t_writer.is_alive(), "Writer thread should finish in stress smoke test.")
        self.assertFalse(t_reader.is_alive(), "Reader thread should finish in stress smoke test.")
        self.assertEqual(errors, [])
        self.assertEqual(len(bootstrap_reads), 3000)
        self.assertEqual(len(system_reads), 3000)
        self.assertEqual(len(live_reads), 3000)
        self.assertTrue(all(isinstance(v, bool) for v in bootstrap_reads))
        self.assertTrue(all(isinstance(v, str) for v in system_reads))
        self.assertTrue(all(isinstance(v, bool) for v in live_reads))


if __name__ == "__main__":
    unittest.main()
