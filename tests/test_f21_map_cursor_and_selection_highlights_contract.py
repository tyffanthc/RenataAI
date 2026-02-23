from __future__ import annotations

import types
import unittest

from app.state import app_state


class F21MapCursorAndSelectionHighlightsContractTests(unittest.TestCase):
    def test_map_cursor_and_selected_current_rings_runtime(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            from gui.tabs.journal_map import JournalMapTab, COLOR_CURRENT_RING, COLOR_SELECTED_RING

            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")

        saved_system = getattr(app_state, "current_system", None)
        frame = None
        try:
            app_state.current_system = "F21_CURRENT"

            frame = JournalMapTab(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1100x700")
            root.update()

            # Default cursor should be system arrow.
            self.assertEqual(str(frame.map_canvas.cget("cursor")), "arrow")

            # Pan cursor appears only during drag.
            frame._on_canvas_press(types.SimpleNamespace(x=100, y=100))
            self.assertEqual(str(frame.map_canvas.cget("cursor")), "arrow")
            frame._on_canvas_drag(types.SimpleNamespace(x=120, y=125))
            self.assertEqual(str(frame.map_canvas.cget("cursor")), "fleur")
            frame._on_canvas_release(types.SimpleNamespace(x=120, y=125))
            self.assertEqual(str(frame.map_canvas.cget("cursor")), "arrow")

            # Render node and mark it as both selected and current.
            frame.set_graph_data(nodes=[{"key": "A", "system_name": "F21_CURRENT", "x": 0.0, "y": 0.0}], edges=[])
            frame._selected_node_key = "A"
            frame._redraw_scene()
            root.update_idletasks()

            selected_items = frame.map_canvas.find_withtag("node_selected_ring")
            current_items = frame.map_canvas.find_withtag("node_current_ring")
            self.assertGreaterEqual(len(selected_items), 1)
            self.assertGreaterEqual(len(current_items), 1)

            selected_outline = str(frame.map_canvas.itemcget(selected_items[0], "outline"))
            current_outline = str(frame.map_canvas.itemcget(current_items[0], "outline"))
            self.assertEqual(selected_outline.lower(), COLOR_SELECTED_RING.lower())
            self.assertEqual(current_outline.lower(), COLOR_CURRENT_RING.lower())
        finally:
            app_state.current_system = saved_system
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass
            try:
                root.destroy()  # type: ignore[name-defined]
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

