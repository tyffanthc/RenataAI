from __future__ import annotations

import os
import tempfile
import unittest

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


class F20MapTravelNodesAndJumpsRendererContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        # Build a short travel sequence in playerdb (systems only; no jumps table baseline).
        events = [
            {
                "event": "Location",
                "timestamp": "2026-02-22T10:00:00Z",
                "StarSystem": "F20_TRAVEL_A",
                "SystemAddress": 7101,
                "SystemId64": 7101,
                "StarPos": [0.0, 0.0, 0.0],
            },
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T10:05:00Z",
                "StarSystem": "F20_TRAVEL_B",
                "SystemAddress": 7102,
                "SystemId64": 7102,
                "StarPos": [10.0, 0.0, 2.0],
            },
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T10:10:00Z",
                "StarSystem": "F20_TRAVEL_C",
                "SystemAddress": 7103,
                "SystemId64": 7103,
                "StarPos": [22.0, 0.0, 5.0],
            },
        ]
        for ev in events:
            player_local_db.ingest_journal_event(ev, path=db_path)

    def test_journal_map_travel_renderer_loads_nodes_and_fallback_edges(self) -> None:
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

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            self._seed_playerdb(db_path)
            provider = MapDataProvider(db_path=db_path)

            frame = None
            try:
                frame = JournalMapTab(root, data_provider=provider)
                frame.pack(fill="both", expand=True)
                root.update_idletasks()
                root.geometry("1100x650")
                root.update()

                result = frame.reload_from_playerdb()
                root.update_idletasks()

                self.assertTrue(bool(result.get("ok")))
                self.assertTrue(bool(result.get("travel_enabled")))
                self.assertGreaterEqual(int(result.get("nodes") or 0), 3)
                self.assertGreaterEqual(int(result.get("edges") or 0), 2)
                self.assertEqual(str(result.get("edges_mode") or ""), "sequential_fallback")

                self.assertGreaterEqual(len(frame._nodes), 3)
                self.assertGreaterEqual(len(frame._edges), 2)
                self.assertEqual(str((frame._travel_edges_meta or {}).get("render_mode") or ""), "sequential_fallback")

                status = str(frame.map_status_var.get() or "").lower()
                self.assertIn("travel", status)
                self.assertIn("fallback sekwencyjny", status)

                # canvas should contain tagged items for nodes/edges
                node_items = frame.map_canvas.find_withtag("map_node")
                edge_items = frame.map_canvas.find_withtag("map_edge")
                self.assertGreater(len(node_items), 0)
                self.assertGreater(len(edge_items), 0)
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

    def test_contract_strings_present_in_journal_map_impl(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "journal_map.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as h:
            content = h.read()
        self.assertIn("def reload_from_playerdb", content)
        self.assertIn("_travel_layout_from_system_rows", content)
        self.assertIn("_build_fallback_sequential_edges", content)
        self.assertIn("sequential_fallback", content)
        self.assertIn("map_edge", content)
        self.assertIn("map_node", content)


if __name__ == "__main__":
    unittest.main()
