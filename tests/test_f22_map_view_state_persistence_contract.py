from __future__ import annotations

import os
import unittest


class _DummyOwner:
    def __init__(self) -> None:
        self.persist_calls = 0

    def _persist_ui_state(self) -> None:
        self.persist_calls += 1


class F22MapViewStatePersistenceContractTests(unittest.TestCase):
    def test_logbook_ui_state_hooks_include_map_state(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "logbook.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()

        self.assertIn('self._pending_map_ui_state: dict[str, Any] = {}', content)
        self.assertIn('map_state = journal_state.get("map")', content)
        self.assertIn("self.tab_map.apply_persisted_ui_state(self._pending_map_ui_state)", content)
        self.assertIn('"map": map_state', content)
        self.assertIn("export_persisted_ui_state", content)

    def test_journal_map_tab_exports_and_applies_persisted_state(self) -> None:
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

            frame.apply_persisted_ui_state(
                {
                    "layers": {
                        "travel": True,
                        "stations": False,
                        "trade": True,
                        "cash_in": True,
                        "exobio": True,
                        "exploration": False,
                        "incidents": True,
                        "combat": False,
                    },
                    "filters": {
                        "time_range": "7d",
                        "freshness": "<=24h",
                        "source_include_enriched": True,
                    },
                    "legend": {"collapsed": True},
                }
            )
            root.update_idletasks()

            self.assertTrue(bool(frame.layer_travel_var.get()))
            self.assertFalse(bool(frame.layer_stations_var.get()))
            self.assertTrue(bool(frame.layer_trade_var.get()))
            self.assertTrue(bool(frame.layer_cashin_var.get()))
            self.assertTrue(bool(frame.layer_exobio_var.get()))
            self.assertFalse(bool(frame.layer_exploration_var.get()))
            self.assertTrue(bool(frame.layer_incidents_var.get()))
            self.assertFalse(bool(frame.layer_combat_var.get()))
            self.assertEqual(str(frame.time_range_var.get()), "7d")
            self.assertEqual(str(frame.freshness_var.get()), "<=24h")
            self.assertTrue(bool(frame.source_include_enriched_var.get()))
            self.assertTrue(bool(frame.legend_collapsed_var.get()))
            self.assertEqual(str(frame.legend_toggle_text_var.get()), "Pokaz")

            exported = frame.export_persisted_ui_state()
            self.assertIsInstance(exported, dict)
            self.assertEqual((((exported.get("layers") or {}).get("stations"))), False)
            self.assertEqual((((exported.get("filters") or {}).get("time_range"))), "7d")
            self.assertEqual((((exported.get("filters") or {}).get("freshness"))), "<=24h")
            self.assertTrue(bool(((exported.get("filters") or {}).get("source_include_enriched"))))
            self.assertTrue(bool(((exported.get("legend") or {}).get("collapsed"))))

            # User-driven changes should notify owner persistence hook.
            frame.reload_from_playerdb = lambda: {"ok": True}  # type: ignore[assignment]
            before = owner.persist_calls
            frame._toggle_legend()
            frame._on_filter_changed()
            self.assertGreaterEqual(owner.persist_calls, before + 2)
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
