from __future__ import annotations

import unittest


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


class F31MapCoordsOnlyRenderModeContractTests(unittest.TestCase):
    def test_mapa_mode_hides_nodes_without_coords_and_reports_hidden_count(self) -> None:
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

        frame = None
        try:
            provider = _ProviderStub(
                [
                    {
                        "system_name": "F31_MAP_OK",
                        "system_address": 94111,
                        "x": 10.0,
                        "y": 0.0,
                        "z": 20.0,
                        "first_seen_ts": "2026-02-28T12:00:00Z",
                        "last_seen_ts": "2026-02-28T12:00:00Z",
                        "freshness_ts": "2026-02-28T12:00:00Z",
                    },
                    {
                        "system_name": "F31_MAP_NO_X",
                        "system_address": 94112,
                        "x": None,
                        "y": 0.0,
                        "z": 21.0,
                        "first_seen_ts": "2026-02-28T12:01:00Z",
                        "last_seen_ts": "2026-02-28T12:01:00Z",
                        "freshness_ts": "2026-02-28T12:01:00Z",
                    },
                    {
                        "system_name": "F31_MAP_NO_Z",
                        "system_address": 94113,
                        "x": 11.0,
                        "y": 0.0,
                        "z": None,
                        "first_seen_ts": "2026-02-28T12:02:00Z",
                        "last_seen_ts": "2026-02-28T12:02:00Z",
                        "freshness_ts": "2026-02-28T12:02:00Z",
                    },
                ]
            )
            frame = JournalMapTab(root, data_provider=provider)
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()

            frame.render_mode_var.set("Mapa")
            result = frame.reload_from_playerdb()

            self.assertTrue(bool(result.get("ok")))
            self.assertEqual(int(result.get("nodes") or 0), 1)
            self.assertEqual(int(result.get("hidden_without_coords") or 0), 2)
            self.assertIn("ukryto 2 systemow bez koordynatow", str(frame.map_status_var.get()).lower())
            self.assertEqual(len(frame._nodes), 1)
            only_node = next(iter(frame._nodes.values()))
            self.assertEqual(str(getattr(only_node, "system_name", "")), "F31_MAP_OK")
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

    def test_mapa_mode_reports_empty_state_when_no_coords_available(self) -> None:
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

        frame = None
        try:
            provider = _ProviderStub(
                [
                    {
                        "system_name": "F31_MAP_ONLY_NO_COORDS_A",
                        "system_address": 94211,
                        "x": None,
                        "y": 0.0,
                        "z": None,
                        "first_seen_ts": "2026-02-28T12:10:00Z",
                        "last_seen_ts": "2026-02-28T12:10:00Z",
                        "freshness_ts": "2026-02-28T12:10:00Z",
                    },
                    {
                        "system_name": "F31_MAP_ONLY_NO_COORDS_B",
                        "system_address": 94212,
                        "x": None,
                        "y": 0.0,
                        "z": None,
                        "first_seen_ts": "2026-02-28T12:11:00Z",
                        "last_seen_ts": "2026-02-28T12:11:00Z",
                        "freshness_ts": "2026-02-28T12:11:00Z",
                    },
                ]
            )
            frame = JournalMapTab(root, data_provider=provider)
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()

            frame.render_mode_var.set("Mapa")
            result = frame.reload_from_playerdb()

            self.assertTrue(bool(result.get("ok")))
            self.assertEqual(int(result.get("nodes") or 0), 0)
            self.assertEqual(int(result.get("hidden_without_coords") or 0), 2)
            self.assertIn("brak systemow z koordynatami w tym zakresie", str(frame.map_status_var.get()).lower())
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

