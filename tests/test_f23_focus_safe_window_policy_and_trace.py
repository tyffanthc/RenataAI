from __future__ import annotations

import unittest

from gui import window_focus


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def deiconify(self) -> None:
        self.calls.append("deiconify")

    def lift(self) -> None:
        self.calls.append("lift")

    def focus_set(self) -> None:
        self.calls.append("focus_set")

    def focus_force(self) -> None:
        self.calls.append("focus_force")

    def title(self) -> str:
        return "Fake"


class F23FocusSafeWindowPolicyTests(unittest.TestCase):
    def test_blocks_force_focus_for_non_user_initiated_path(self) -> None:
        win = _FakeWindow()
        ok = window_focus.request_window_focus(
            win,
            source="test.runtime.path",
            user_initiated=False,
            force=True,
        )
        self.assertFalse(ok)
        self.assertEqual(win.calls, [])

    def test_bring_window_to_front_uses_safe_focus_set_for_user_action(self) -> None:
        win = _FakeWindow()
        ok = window_focus.bring_window_to_front(
            win,
            source="test.user.dialog",
            user_initiated=True,
            deiconify=True,
            request_focus=True,
            force_focus=False,
        )
        self.assertTrue(ok)
        self.assertEqual(win.calls, ["deiconify", "lift", "focus_set"])

    def test_bring_window_to_front_can_skip_focus_request(self) -> None:
        win = _FakeWindow()
        ok = window_focus.bring_window_to_front(
            win,
            source="test.overlay",
            user_initiated=True,
            deiconify=False,
            request_focus=False,
        )
        self.assertTrue(ok)
        self.assertEqual(win.calls, ["lift"])


if __name__ == "__main__":
    unittest.main()

