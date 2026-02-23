from __future__ import annotations

import math
import unittest

from app.state import app_state


class F22MapCenterOnCurrentSystemTravelLayoutFixContractTests(unittest.TestCase):
    def test_center_on_current_system_uses_rendered_node_in_travel_layout(self) -> None:
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

        saved_system = getattr(app_state, "current_system", None)
        saved_star_pos = getattr(app_state, "current_star_pos", None)
        frame = None
        try:
            app_state.current_system = "F22_CENTER_TARGET"
            # Intentionally different from rendered node coords to catch old bug (StarPos path).
            app_state.current_star_pos = [9999.0, 0.0, 9999.0]

            frame = JournalMapTab(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()
            frame.reset_view()

            frame.set_graph_data(
                nodes=[
                    {"key": "A", "system_name": "Alpha", "x": 5.0, "y": 5.0},
                    {"key": "B", "system_name": "F22_CENTER_TARGET", "x": 42.0, "y": -7.0},
                ],
                edges=[],
            )
            root.update_idletasks()

            frame.center_on_current_system()
            root.update_idletasks()

            sx, sy = frame.world_to_screen(42.0, -7.0)
            canvas_w = max(1, int(frame.map_canvas.winfo_width() or 1))
            canvas_h = max(1, int(frame.map_canvas.winfo_height() or 1))
            self.assertLess(abs(float(sx) - (canvas_w / 2.0)), 1.5)
            self.assertLess(abs(float(sy) - (canvas_h / 2.0)), 1.5)

            # Ensure it did not center on StarPos fallback.
            sx_wrong, sy_wrong = frame.world_to_screen(9999.0, 9999.0)
            self.assertTrue(
                math.fabs(float(sx_wrong) - (canvas_w / 2.0)) > 10.0
                or math.fabs(float(sy_wrong) - (canvas_h / 2.0)) > 10.0
            )

            status = str(frame.map_status_var.get() or "").lower()
            self.assertIn("wycentrowano", status)
            self.assertIn("f22_center_target".lower(), status)
        finally:
            app_state.current_system = saved_system
            app_state.current_star_pos = saved_star_pos
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass
            try:
                root.destroy()  # type: ignore[name-defined]
            except Exception:
                pass

    def test_center_on_current_system_reports_when_not_visible_in_filtered_view(self) -> None:
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

        saved_system = getattr(app_state, "current_system", None)
        saved_star_pos = getattr(app_state, "current_star_pos", None)
        frame = None
        try:
            app_state.current_system = "F22_MISSING_SYSTEM"
            app_state.current_star_pos = [1.0, 0.0, 2.0]

            frame = JournalMapTab(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            frame.set_graph_data(nodes=[{"key": "A", "system_name": "Alpha", "x": 0.0, "y": 0.0}], edges=[])
            frame.center_on_current_system()
            status = str(frame.map_status_var.get() or "").lower()
            self.assertIn("nie jest widoczny", status)
        finally:
            app_state.current_system = saved_system
            app_state.current_star_pos = saved_star_pos
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
