from __future__ import annotations

import os
import types
import unittest

from app.state import app_state


class F20MapTkinterShellAndPanZoomContractTests(unittest.TestCase):
    def test_logbook_tab_integrates_map_subtab_contract(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "logbook.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()

        self.assertIn("from gui.tabs.journal_map import JournalMapTab", content)
        self.assertIn("self.tab_map = JournalMapTab(self.sub_notebook, app=self.app, logbook_owner=self)", content)
        self.assertIn('self.sub_notebook.add(self.tab_map, text="Mapa")', content)
        self.assertIn('if subtab_key in {"entries", "feed", "map"}', content)
        self.assertIn('if selected == str(self.tab_map):', content)
        self.assertIn('if self._pending_subtab_key == "map":', content)

    def test_journal_map_tab_shell_and_pan_zoom_runtime(self) -> None:
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

        saved_star_pos = getattr(app_state, "current_star_pos", None)
        saved_system = getattr(app_state, "current_system", None)
        try:
            app_state.current_system = "F20_TEST_CURRENT"
            app_state.current_star_pos = [42.0, 0.0, -7.0]

            frame = JournalMapTab(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()

            self.assertTrue(hasattr(frame, "left_frame"))
            self.assertTrue(hasattr(frame, "center_frame"))
            self.assertTrue(hasattr(frame, "right_frame"))
            self.assertTrue(hasattr(frame, "map_canvas"))

            # Reset and zoom
            frame.reset_view()
            base_scale = float(frame.view_scale)
            wheel_in = types.SimpleNamespace(x=200, y=200, delta=120)
            frame._on_canvas_mousewheel(wheel_in)
            self.assertGreater(float(frame.view_scale), base_scale)

            # Pan drag changes offsets
            before_off = (float(frame.view_offset_x), float(frame.view_offset_y))
            frame._on_canvas_press(types.SimpleNamespace(x=100, y=100))
            frame._on_canvas_drag(types.SimpleNamespace(x=140, y=130))
            frame._on_canvas_release(types.SimpleNamespace(x=140, y=130))
            after_off = (float(frame.view_offset_x), float(frame.view_offset_y))
            self.assertNotEqual(before_off, after_off)

            # Simple graph data should render without crash
            frame.set_graph_data(
                nodes=[
                    {"key": "A", "system_name": "A", "x": 0.0, "y": 0.0},
                    {"key": "B", "system_name": "B", "x": 10.0, "y": 5.0},
                ],
                edges=[
                    {"from_key": "A", "to_key": "B"},
                ],
            )
            root.update_idletasks()
            self.assertEqual(len(frame._nodes), 2)
            self.assertEqual(len(frame._edges), 1)

            # Center on current system should use app_state.current_star_pos (x,z -> 2D)
            frame.center_on_current_system()
            root.update_idletasks()
            self.assertIn("wycentrowano", str(frame.map_status_var.get()).lower())
        finally:
            app_state.current_star_pos = saved_star_pos
            app_state.current_system = saved_system
            try:
                frame.destroy()  # type: ignore[name-defined]
            except Exception:
                pass
            try:
                root.destroy()  # type: ignore[name-defined]
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
