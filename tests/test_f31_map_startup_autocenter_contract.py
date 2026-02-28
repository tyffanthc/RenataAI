from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.state import app_state


class _ProviderStub:
    def __init__(self, nodes: list[dict]) -> None:
        self._nodes = [dict(r) for r in (nodes or [])]

    def get_system_nodes(self, **_kwargs):
        return (list(self._nodes), {"count": len(self._nodes)})

    def get_edges(self, **_kwargs):
        return ([], {"count": 0, "available": False, "reason": "stub"})

    def get_station_service_summary_batch(self, _nodes, **_kwargs):
        return ({}, {"count": 0})

    def get_action_layers_summary_batch(self, _nodes, **_kwargs):
        return ({}, {"count": 0})

    def get_known_commodities(self, **_kwargs):
        return ([], {"count": 0})

    def get_stations_for_system(self, **_kwargs):
        return ([], {"count": 0})


class F31MapStartupAutocenterContractTests(unittest.TestCase):
    def test_startup_autocenter_retries_after_canvas_becomes_ready(self) -> None:
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
            app_state.current_system = "F31_RETRY_TARGET"
            app_state.current_star_pos = [999.0, 0.0, -999.0]
            provider = _ProviderStub(
                [
                    {
                        "system_name": "F31_RETRY_TARGET",
                        "system_address": 93113,
                        "system_id64": 93113,
                        "x": 18.0,
                        "y": 0.0,
                        "z": -4.0,
                        "first_seen_ts": "2026-02-28T12:20:00Z",
                        "last_seen_ts": "2026-02-28T12:20:00Z",
                        "source": "journal",
                        "confidence": "observed",
                        "freshness_ts": "2026-02-28T12:20:00Z",
                    }
                ]
            )

            frame = JournalMapTab(root, data_provider=provider)
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            frame.render_mode_var.set("Mapa")
            frame.reset_view()

            orig_w = frame.map_canvas.winfo_width
            orig_h = frame.map_canvas.winfo_height
            frame.map_canvas.winfo_width = lambda: 1  # type: ignore[assignment]
            frame.map_canvas.winfo_height = lambda: 1  # type: ignore[assignment]
            try:
                first = frame.reload_from_playerdb()
            finally:
                frame.map_canvas.winfo_width = orig_w  # type: ignore[assignment]
                frame.map_canvas.winfo_height = orig_h  # type: ignore[assignment]

            self.assertTrue(bool((first.get("startup_center") or {}).get("applied")))
            self.assertEqual(str((first.get("startup_center") or {}).get("reason") or ""), "current_system_node")
            self.assertFalse(bool(getattr(frame, "_startup_autocenter_pending", False)))
            self.assertTrue(bool(getattr(frame, "_startup_autocenter_done", False)))
            self.assertTrue(bool(getattr(frame, "_startup_autocenter_recenter_pending", False)))

            try:
                root.deiconify()
            except Exception:
                pass
            root.geometry("1200x700")
            root.update()
            frame._on_canvas_configure(None)

            self.assertTrue(bool(getattr(frame, "_startup_autocenter_done", False)))
            self.assertFalse(bool(getattr(frame, "_startup_autocenter_recenter_pending", False)))
            node = next((n for n in frame._nodes.values() if str(getattr(n, "system_name", "")) == "F31_RETRY_TARGET"), None)
            self.assertIsNotNone(node)
            sx, sy = frame.world_to_screen(float(node.x), float(node.y))  # type: ignore[union-attr]
            canvas_w = max(1, int(frame.map_canvas.winfo_width() or 1))
            canvas_h = max(1, int(frame.map_canvas.winfo_height() or 1))
            self.assertLess(abs(float(sx) - (canvas_w / 2.0)), 1.5)
            self.assertLess(abs(float(sy) - (canvas_h / 2.0)), 1.5)
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

    def test_startup_reload_autocenters_on_current_system_when_visible(self) -> None:
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
            app_state.current_system = "F31_CENTER_TARGET"
            app_state.current_star_pos = [9999.0, 0.0, 9999.0]
            provider = _ProviderStub(
                [
                    {
                        "system_name": "F31_CENTER_TARGET",
                        "system_address": 93111,
                        "system_id64": 93111,
                        "x": 42.0,
                        "y": 0.0,
                        "z": -7.0,
                        "first_seen_ts": "2026-02-28T12:00:00Z",
                        "last_seen_ts": "2026-02-28T12:00:00Z",
                        "source": "journal",
                        "confidence": "observed",
                        "freshness_ts": "2026-02-28T12:00:00Z",
                    }
                ]
            )

            frame = JournalMapTab(root, data_provider=provider)
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()

            frame.render_mode_var.set("Mapa")
            frame.reset_view()
            result = frame.reload_from_playerdb()
            self.assertTrue(bool((result.get("startup_center") or {}).get("applied")))
            self.assertEqual(str((result.get("startup_center") or {}).get("reason") or ""), "current_system_node")
            self.assertTrue(bool(getattr(frame, "_startup_autocenter_done", False)))

            node = next((n for n in frame._nodes.values() if str(getattr(n, "system_name", "")) == "F31_CENTER_TARGET"), None)
            self.assertIsNotNone(node)
            sx, sy = frame.world_to_screen(float(node.x), float(node.y))  # type: ignore[union-attr]
            canvas_w = max(1, int(frame.map_canvas.winfo_width() or 1))
            canvas_h = max(1, int(frame.map_canvas.winfo_height() or 1))
            self.assertLess(abs(float(sx) - (canvas_w / 2.0)), 1.5)
            self.assertLess(abs(float(sy) - (canvas_h / 2.0)), 1.5)
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

    def test_startup_autocenter_is_blocked_after_manual_pan_before_reload(self) -> None:
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
            app_state.current_system = "F31_BLOCKED_TARGET"
            app_state.current_star_pos = [111.0, 0.0, 222.0]
            provider = _ProviderStub(
                [
                    {
                        "system_name": "F31_BLOCKED_TARGET",
                        "system_address": 93112,
                        "system_id64": 93112,
                        "x": 12.0,
                        "y": 0.0,
                        "z": 24.0,
                        "first_seen_ts": "2026-02-28T12:10:00Z",
                        "last_seen_ts": "2026-02-28T12:10:00Z",
                        "source": "journal",
                        "confidence": "observed",
                        "freshness_ts": "2026-02-28T12:10:00Z",
                    }
                ]
            )

            frame = JournalMapTab(root, data_provider=provider)
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()
            frame.render_mode_var.set("Mapa")
            frame.reset_view()

            frame._on_canvas_press(SimpleNamespace(x=100, y=100))
            frame._on_canvas_drag(SimpleNamespace(x=120, y=120))
            frame._on_canvas_release(None)

            self.assertTrue(bool(getattr(frame, "_startup_autocenter_user_blocked", False)))
            self.assertFalse(bool(getattr(frame, "_startup_autocenter_pending", True)))

            result = frame.reload_from_playerdb()
            self.assertFalse(bool((result.get("startup_center") or {}).get("applied")))
            self.assertEqual(str((result.get("startup_center") or {}).get("reason") or ""), "user_blocked")
            self.assertFalse(bool(getattr(frame, "_startup_autocenter_done", False)))
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
