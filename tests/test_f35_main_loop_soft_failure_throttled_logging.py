from __future__ import annotations

import unittest
from unittest.mock import patch

from app.main_loop import MainLoop


class _DummyWatcher:
    def __init__(self, *args, **kwargs):
        _ = args, kwargs


class _DummyHandlerLogDirRaises:
    @property
    def log_dir(self):
        return None

    @log_dir.setter
    def log_dir(self, _value):
        raise RuntimeError("cannot set log_dir")


class F35MainLoopSoftFailureThrottledLoggingTests(unittest.TestCase):
    def _build_mainloop_with_patched_deps(self, *, handler_obj):
        with (
            patch("app.main_loop.StatusWatcher", _DummyWatcher),
            patch("app.main_loop.MarketWatcher", _DummyWatcher),
            patch("app.main_loop.CargoWatcher", _DummyWatcher),
            patch("app.main_loop.NavRouteWatcher", _DummyWatcher),
            patch("app.main_loop.handler", handler_obj),
        ):
            return MainLoop(gui_ref=None, log_dir="C:/dummy")

    def test_init_logdir_set_failure_logs_with_correct_throttled_signature(self) -> None:
        with patch("app.main_loop.log_event_throttled") as log_mock:
            self._build_mainloop_with_patched_deps(handler_obj=_DummyHandlerLogDirRaises())

        log_mock.assert_called_once()
        args = log_mock.call_args.args
        kwargs = log_mock.call_args.kwargs
        self.assertEqual(str(args[0]), "MAINLOOP_HANDLER_LOGDIR_SET_FAILED")
        self.assertEqual(int(args[1]), 120000)
        self.assertEqual(str(args[2]), "WARN")
        self.assertIn("failed to set handler.log_dir", str(args[3]))
        self.assertEqual(str(kwargs.get("context") or ""), "main_loop.handler.log_dir")

    def test_runtime_critical_emit_failure_logs_with_correct_throttled_signature(self) -> None:
        with (
            patch("app.main_loop.log_event_throttled") as log_mock,
            patch("app.main_loop.emit_insight", side_effect=RuntimeError("emit failed")),
        ):
            loop = self._build_mainloop_with_patched_deps(handler_obj=object())
            loop._emit_runtime_critical("Boom", component="journal_stream")

        log_mock.assert_called_once()
        args = log_mock.call_args.args
        kwargs = log_mock.call_args.kwargs
        self.assertEqual(str(args[0]), "MAINLOOP_RUNTIME_CRITICAL_EMIT_FAILED")
        self.assertEqual(int(args[1]), 120000)
        self.assertEqual(str(args[2]), "WARN")
        self.assertIn("runtime critical insight emit failed", str(args[3]))
        self.assertEqual(
            str(kwargs.get("context") or ""),
            "main_loop.runtime_critical.emit:journal_stream",
        )


if __name__ == "__main__":
    unittest.main()

