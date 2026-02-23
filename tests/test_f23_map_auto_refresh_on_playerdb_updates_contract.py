from __future__ import annotations

import os
import time
import unittest


class _DummyOwner:
    def __init__(self) -> None:
        self.active_subtab_key = "feed"

    def _resolve_active_subtab_key(self) -> str:
        return str(self.active_subtab_key)

    def _persist_ui_state(self) -> None:
        return None


class F23MapAutoRefreshOnPlayerdbUpdatesContractTests(unittest.TestCase):
    def test_queue_and_router_contract_strings_present(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_path = os.path.join(project_root, "gui", "app.py")
        router_path = os.path.join(project_root, "logic", "event_handler.py")

        with open(app_path, "r", encoding="utf-8", errors="ignore") as handle:
            app_content = handle.read()
        with open(router_path, "r", encoding="utf-8", errors="ignore") as handle:
            router_content = handle.read()

        self.assertIn('elif msg_type == "playerdb_updated":', app_content)
        self.assertIn("notify_playerdb_updated", app_content)
        self.assertIn('"playerdb_updated"', router_content)
        self.assertIn("_emit_playerdb_updated(", router_content)

    def test_journal_map_deferred_then_debounced_refresh(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            from gui.tabs.journal_map import JournalMapTab

            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")

        owner = _DummyOwner()
        frame = None
        try:
            frame = JournalMapTab(root, logbook_owner=owner)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            # Cancel startup reload scheduled by the widget; this test controls reload timing.
            frame._cancel_pending_after_jobs()
            frame._cancel_auto_refresh_debounce()
            frame._auto_refresh_debounce_ms = 10

            calls: list[str] = []

            def _fake_reload():
                calls.append("reload")
                return {"ok": True}

            frame.reload_from_playerdb = _fake_reload  # type: ignore[assignment]

            # 1) Update while map subtab is inactive -> deferred (no immediate reload).
            owner.active_subtab_key = "feed"
            result = frame.notify_playerdb_updated({"source": "journal", "event_name": "FSDJump"})
            self.assertTrue(bool(result.get("ok")))
            self.assertTrue(bool(result.get("deferred")))
            self.assertFalse(bool(result.get("scheduled")))
            self.assertEqual(calls, [])

            # 2) Activate map subtab -> debounced refresh runs.
            owner.active_subtab_key = "map"
            frame.on_parent_map_subtab_activated()
            root.update()
            time.sleep(0.16)
            root.update()
            self.assertEqual(calls, ["reload"])
            self.assertFalse(bool(frame._auto_refresh_dirty))

            # 3) Multiple quick updates while active collapse into one reload (debounce).
            frame._auto_refresh_debounce_ms = 20
            frame.notify_playerdb_updated({"source": "journal", "event_name": "Docked"})
            frame.notify_playerdb_updated({"source": "market_json", "event_name": "Market"})
            root.update()
            time.sleep(0.05)
            root.update()
            self.assertEqual(calls, ["reload", "reload"])
        finally:
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
