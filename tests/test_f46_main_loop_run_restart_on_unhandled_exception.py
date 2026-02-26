from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app import main_loop


class _DummyWatcher:
    def __init__(self, *args, **kwargs):
        _ = args, kwargs


class _DummyHandler:
    def __init__(self) -> None:
        self.log_dir = None
        self.handle_event = Mock()


class F46MainLoopRunRestartOnUnhandledExceptionTests(unittest.TestCase):
    def _build_loop(self):
        handler_obj = _DummyHandler()
        with (
            patch("app.main_loop.StatusWatcher", _DummyWatcher),
            patch("app.main_loop.MarketWatcher", _DummyWatcher),
            patch("app.main_loop.CargoWatcher", _DummyWatcher),
            patch("app.main_loop.NavRouteWatcher", _DummyWatcher),
            patch("app.main_loop.handler", handler_obj),
        ):
            return main_loop.MainLoop(gui_ref=None, log_dir="C:/dummy"), handler_obj

    def test_run_restarts_loop_after_unhandled_tail_exception(self) -> None:
        loop, _handler = self._build_loop()

        tail_calls = {"count": 0}

        def _tail_side_effect(path: str) -> None:
            tail_calls["count"] += 1
            if tail_calls["count"] == 1:
                raise RuntimeError("boom-tail")
            raise SystemExit("stop-test")

        with (
            patch("app.main_loop.powiedz"),
            patch.object(loop, "_find_latest_file", return_value="C:/dummy/Journal.01.log") as find_mock,
            patch.object(loop, "_bootstrap_state") as bootstrap_mock,
            patch.object(loop, "_tail_file", side_effect=_tail_side_effect) as tail_mock,
            patch.object(loop, "_log_error") as log_error_mock,
            patch.object(loop, "_emit_runtime_critical") as runtime_critical_mock,
            patch("app.main_loop.time.sleep") as sleep_mock,
        ):
            with self.assertRaises(SystemExit):
                loop.run()

        self.assertGreaterEqual(find_mock.call_count, 2)
        self.assertEqual(bootstrap_mock.call_count, 2)
        self.assertEqual(tail_mock.call_count, 2)
        log_error_mock.assert_called_once()
        self.assertIn("[BŁĄD MainLoop/run] boom-tail", str(log_error_mock.call_args.args[0]))
        runtime_critical_mock.assert_called_once()
        self.assertEqual(
            runtime_critical_mock.call_args.kwargs.get("component"),
            "journal_stream",
        )
        self.assertTrue(sleep_mock.called, "Expected retry backoff sleep after run-loop exception")


if __name__ == "__main__":
    unittest.main()
