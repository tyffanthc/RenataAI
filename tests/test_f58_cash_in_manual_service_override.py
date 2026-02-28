from __future__ import annotations

import unittest
from unittest.mock import patch

from gui.app import RenataApp


class _ImmediateThread:
    def __init__(self, target=None, daemon=None, **_kwargs):
        self._target = target

    def start(self) -> None:
        if callable(self._target):
            self._target()


class _DummyRoot:
    def after(self, _ms: int, callback):
        if callable(callback):
            callback()


class _DummyPulpit:
    def get_current_exploration_summary_payload(self):
        return {
            "system": "F58_SUMMARY_SYSTEM",
            "cash_in_session_estimated": 12_000_000,
        }


class _DummyApp:
    on_generate_cash_in_assistant = RenataApp.on_generate_cash_in_assistant

    def __init__(self) -> None:
        self._cash_in_manual_trigger_active = False
        self.tab_pulpit = _DummyPulpit()
        self.root = _DummyRoot()
        self.status_lines: list[str] = []

    def show_status(self, text: str) -> None:
        self.status_lines.append(str(text or ""))


class F58CashInManualServiceOverrideTests(unittest.TestCase):
    def test_manual_trigger_passes_service_override_to_runtime_payload(self) -> None:
        app = _DummyApp()
        with (
            patch("gui.app.threading.Thread", _ImmediateThread),
            patch("logic.events.cash_in_assistant.trigger_cash_in_assistant", return_value=True) as trigger_mock,
        ):
            app.on_generate_cash_in_assistant(
                mode="manual",
                summary_seed={"system": "F58_MANUAL_SYSTEM", "cash_in_session_estimated": 5_000_000},
                service_override="vista",
            )

        self.assertEqual(trigger_mock.call_count, 1)
        kwargs = dict(trigger_mock.call_args.kwargs or {})
        self.assertEqual(str(kwargs.get("mode") or ""), "manual")
        payload = dict(kwargs.get("summary_payload") or {})
        self.assertEqual(str(payload.get("system") or ""), "F58_MANUAL_SYSTEM")
        self.assertEqual(str(payload.get("cash_in_service") or ""), "vista")
        self.assertFalse(bool(app._cash_in_manual_trigger_active))


if __name__ == "__main__":
    unittest.main()
