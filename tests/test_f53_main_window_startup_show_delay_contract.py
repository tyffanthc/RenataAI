from __future__ import annotations

import unittest
from unittest.mock import patch

import main


class _FakeRoot:
    def __init__(self) -> None:
        self.withdraw_calls = 0
        self.update_idletasks_calls = 0
        self.deiconify_calls = 0
        self.mainloop_calls = 0
        self.after_calls: list[tuple[int, object]] = []

    def withdraw(self) -> None:
        self.withdraw_calls += 1

    def update_idletasks(self) -> None:
        self.update_idletasks_calls += 1

    def deiconify(self) -> None:
        self.deiconify_calls += 1

    def after(self, delay_ms: int, callback) -> None:
        self.after_calls.append((int(delay_ms), callback))

    def mainloop(self) -> None:
        self.mainloop_calls += 1


class _FakeRootUpdateFail(_FakeRoot):
    def update_idletasks(self) -> None:
        raise RuntimeError("update fail")


class _FakeRootBothFail(_FakeRoot):
    def update_idletasks(self) -> None:
        raise RuntimeError("update fail")

    def deiconify(self) -> None:
        raise RuntimeError("deiconify fail")


class _FakeThread:
    def __init__(self, *, target=None, daemon: bool = False, **_kwargs) -> None:
        self.target = target
        self.daemon = bool(daemon)
        self.started = False

    def start(self) -> None:
        self.started = True


class _FakeLoop:
    def __init__(self, _app, _log_dir) -> None:
        self.run = lambda: None


class F53MainWindowStartupShowDelayContractTests(unittest.TestCase):
    def test_show_main_window_safe_still_deiconifies_when_update_fails(self) -> None:
        root = _FakeRootUpdateFail()
        main._show_main_window_safe(root)
        self.assertEqual(root.deiconify_calls, 1)

    def test_show_main_window_safe_swallow_exceptions(self) -> None:
        root = _FakeRootBothFail()
        main._show_main_window_safe(root)  # no raise

    def test_run_schedules_window_show_with_nonzero_delay(self) -> None:
        root = _FakeRoot()
        thread_box: dict[str, _FakeThread] = {}

        def _thread_factory(*args, **kwargs):
            t = _FakeThread(*args, **kwargs)
            thread_box["thread"] = t
            return t

        with (
            patch("main.tk.Tk", return_value=root),
            patch("main.RenataApp", return_value=object()),
            patch("main.powiedz"),
            patch("main.MainLoop", side_effect=lambda app, log_dir: _FakeLoop(app, log_dir)),
            patch("main.threading.Thread", side_effect=_thread_factory),
            patch.object(main.config, "get", return_value="C:/tmp/journal"),
        ):
            main.run()

        self.assertEqual(root.withdraw_calls, 1)
        self.assertEqual(root.mainloop_calls, 1)
        self.assertEqual(len(root.after_calls), 1)
        delay_ms, callback = root.after_calls[0]
        self.assertEqual(delay_ms, main.MAIN_WINDOW_SHOW_DELAY_MS)
        self.assertGreater(delay_ms, 0)
        self.assertTrue(callable(callback))

        created = thread_box.get("thread")
        self.assertIsNotNone(created)
        self.assertTrue(bool(created and created.daemon))
        self.assertTrue(bool(created and created.started))


if __name__ == "__main__":
    unittest.main()
