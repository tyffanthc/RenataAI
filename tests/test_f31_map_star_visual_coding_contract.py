from __future__ import annotations

import unittest


class _ProviderStub:
    def get_system_nodes(self, **_kwargs):
        return ([], {"count": 0})

    def get_edges(self, **_kwargs):
        return ([], {"count": 0, "available": False, "reason": "stub"})

    def get_station_layer_flags_for_systems(self, **_kwargs):
        return ({}, {"count": 0})

    def get_system_action_flags(self, **_kwargs):
        return ({}, {"count": 0})

    def get_known_commodities(self, **_kwargs):
        return ([], {"count": 0})

    def get_stations_for_system(self, **_kwargs):
        return ([], {"count": 0})


class F31MapStarVisualCodingContractTests(unittest.TestCase):
    def test_neutron_star_has_distinct_glyph_and_star_info_in_tooltip_and_details(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            from gui.tabs.journal_map import COLOR_BG, COLOR_STAR_NEUTRON, JournalMapTab

            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")

        frame = None
        try:
            frame = JournalMapTab(root, data_provider=_ProviderStub())
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            frame.set_graph_data(
                nodes=[
                    {
                        "key": "N1",
                        "system_name": "F31_NEUTRON_SYSTEM",
                        "x": 10.0,
                        "y": 10.0,
                        "z": 0.0,
                        "primary_star_type": "N",
                        "is_neutron": 1,
                        "is_black_hole": 0,
                        "freshness_ts": "2026-02-28T12:00:00Z",
                        "first_seen_ts": "2026-02-28T12:00:00Z",
                        "last_seen_ts": "2026-02-28T12:00:00Z",
                    }
                ],
                edges=[],
            )
            root.update_idletasks()

            glyphs = frame.map_canvas.find_withtag("map_node")
            self.assertGreaterEqual(len(glyphs), 1)
            neutron_fill = str(frame.map_canvas.itemcget(glyphs[0], "fill") or "")
            neutron_outline = str(frame.map_canvas.itemcget(glyphs[0], "outline") or "")
            self.assertEqual(neutron_fill, COLOR_BG)
            self.assertEqual(neutron_outline, COLOR_STAR_NEUTRON)

            node = frame._nodes.get("N1")
            self.assertIsNotNone(node)
            tooltip = frame._tooltip_text_for_node(node)  # type: ignore[arg-type]
            self.assertIn("Gwiazda: N", tooltip)

            sel = frame.select_system_node("N1")
            self.assertTrue(bool(sel.get("ok")))
            details = str(frame.system_details_var.get() or "")
            self.assertIn("Gwiazda: N", details)
        finally:
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass
            try:
                root.destroy()  # type: ignore[name-defined]
            except Exception:
                pass

    def test_black_hole_star_has_distinct_outline_color(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            from gui.tabs.journal_map import COLOR_BG, COLOR_STAR_BLACK_HOLE, JournalMapTab

            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")

        frame = None
        try:
            frame = JournalMapTab(root, data_provider=_ProviderStub())
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            frame.set_graph_data(
                nodes=[
                    {
                        "key": "B1",
                        "system_name": "F31_BLACKHOLE_SYSTEM",
                        "x": 20.0,
                        "y": 20.0,
                        "z": 0.0,
                        "primary_star_type": "Black Hole",
                        "is_neutron": 0,
                        "is_black_hole": 1,
                        "freshness_ts": "2026-02-28T12:00:00Z",
                        "first_seen_ts": "2026-02-28T12:00:00Z",
                        "last_seen_ts": "2026-02-28T12:00:00Z",
                    }
                ],
                edges=[],
            )
            root.update_idletasks()

            glyphs = frame.map_canvas.find_withtag("map_node")
            self.assertGreaterEqual(len(glyphs), 1)
            fill = str(frame.map_canvas.itemcget(glyphs[0], "fill") or "")
            outline = str(frame.map_canvas.itemcget(glyphs[0], "outline") or "")
            self.assertEqual(fill, COLOR_BG)
            self.assertEqual(outline, COLOR_STAR_BLACK_HOLE)
        finally:
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
