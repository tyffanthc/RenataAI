from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.main_loop import MainLoop
from app.state import app_state


class _DummyWatcher:
    def __init__(self, *args, **kwargs):
        _ = args, kwargs


class _DummyHandler:
    def __init__(self) -> None:
        self.log_dir = None
        self.handle_event = Mock()


class _IterableFileNoReadlines:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.readlines_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)

    def readlines(self):
        self.readlines_called = True
        raise AssertionError("Bootstrap should not use readlines(); it should stream tail lines.")


class F38MainLoopBootstrapTailLinesMemorySafeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_bootstrap_replay = getattr(app_state, "bootstrap_replay", False)

    def tearDown(self) -> None:
        app_state.bootstrap_replay = self._saved_bootstrap_replay

    def _build_mainloop(self, *, handler_obj):
        with (
            patch("app.main_loop.StatusWatcher", _DummyWatcher),
            patch("app.main_loop.MarketWatcher", _DummyWatcher),
            patch("app.main_loop.CargoWatcher", _DummyWatcher),
            patch("app.main_loop.NavRouteWatcher", _DummyWatcher),
            patch("app.main_loop.handler", handler_obj),
        ):
            return MainLoop(gui_ref=None, log_dir="C:/dummy")

    def test_bootstrap_reads_only_tail_lines_without_readlines(self) -> None:
        all_lines = [
            '{"event":"Fileheader"}\n',
            '{"event":"Music"}\n',
            '{"event":"Loadout"}\n',
            '{"event":"Location"}\n',
            '{"event":"Scan"}\n',
        ]
        expected_tail = all_lines[-3:]
        fake_file = _IterableFileNoReadlines(all_lines)
        handler_obj = _DummyHandler()

        with (
            patch("builtins.open", return_value=fake_file),
            patch("app.main_loop.powiedz"),
            patch("logic.events.exploration_bio_events.bootstrap_exobio_state_from_journal_lines") as exobio_bootstrap,
            patch(
                "logic.events.exploration_value_recovery.bootstrap_system_value_from_journal_lines",
                return_value={},
            ) as value_bootstrap,
        ):
            loop = self._build_mainloop(handler_obj=handler_obj)
            loop._bootstrap_state("C:/dummy/Journal.01.log", max_lines=3)

        self.assertFalse(fake_file.readlines_called)

        exobio_bootstrap.assert_called_once()
        self.assertEqual(list(exobio_bootstrap.call_args.args[0]), expected_tail)
        self.assertEqual(int(exobio_bootstrap.call_args.kwargs.get("max_lines") or 0), 3)

        value_bootstrap.assert_called_once()
        self.assertEqual(list(value_bootstrap.call_args.args[0]), expected_tail)
        self.assertEqual(int(value_bootstrap.call_args.kwargs.get("max_lines") or 0), 3)


if __name__ == "__main__":
    unittest.main()
