from __future__ import annotations

import unittest
from unittest.mock import patch

from app.status_watchers import StatusWatcher


class _DummyHandler:
    def on_status_update(self, _data, _gui_ref):
        raise RuntimeError("boom")


class _DummyConfig:
    def get(self, _key, default=None):
        return default


class F34StatusWatcherDispatchSoftFailureLoggingTests(unittest.TestCase):
    def test_dispatch_soft_failure_helper_logs_with_valid_signature(self) -> None:
        watcher = StatusWatcher(
            handler=_DummyHandler(),
            gui_ref=None,
            app_state=None,
            config=_DummyConfig(),
        )

        with patch("app.status_watchers.log_event_throttled") as log_mock:
            watcher._log_dispatch_soft_failure("status_update")

        log_mock.assert_called_once()
        args = log_mock.call_args.args
        kwargs = log_mock.call_args.kwargs
        self.assertGreaterEqual(len(args), 4)
        self.assertEqual(str(args[0]), "WATCHER_DISPATCH_STATUS_STATUS_UPDATE")
        self.assertEqual(int(args[1]), 120000)
        self.assertEqual(str(args[2]), "WARN")
        self.assertIn("dispatch status_update failed", str(args[3]))
        self.assertEqual(str(kwargs.get("context") or ""), "watcher.status.dispatch:status_update")

    def test_status_watcher_poll_logs_soft_failure_without_typeerror(self) -> None:
        watcher = StatusWatcher(
            handler=_DummyHandler(),
            gui_ref=None,
            app_state=None,
            config=_DummyConfig(),
        )

        with (
            patch.object(watcher, "_should_poll", return_value=True),
            patch.object(watcher, "_load_json_safely", return_value={"ok": True}),
            patch("app.status_watchers.log_event_throttled") as log_mock,
        ):
            # Regression: old argument order caused TypeError before entering log_event_throttled.
            watcher.poll()

        log_mock.assert_called_once()
        args = log_mock.call_args.args
        kwargs = log_mock.call_args.kwargs
        self.assertGreaterEqual(len(args), 4)
        self.assertEqual(str(args[0]), "WATCHER_DISPATCH_STATUS_STATUS_UPDATE")
        self.assertEqual(int(args[1]), 120000)
        self.assertEqual(str(args[2]), "WARN")
        self.assertIn("dispatch status_update failed", str(args[3]))
        self.assertEqual(str(kwargs.get("context") or ""), "watcher.status.dispatch:status_update")


if __name__ == "__main__":
    unittest.main()
