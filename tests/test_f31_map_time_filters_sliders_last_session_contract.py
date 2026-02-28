from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone


class _ProviderStub:
    def __init__(self, nodes: list[dict]) -> None:
        self._nodes = [dict(r) for r in (nodes or [])]

    def get_system_nodes(self, **_kwargs):
        return (list(self._nodes), {"count": len(self._nodes)})

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


class F31MapTimeFiltersSlidersLastSessionContractTests(unittest.TestCase):
    def test_last_session_toggle_disables_sliders_and_filters_nodes_to_runtime_window(self) -> None:
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
            now = datetime.now(timezone.utc)
            ts_old = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")
            ts_recent = (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
            provider = _ProviderStub(
                [
                    {
                        "system_name": "F31_SESSION_OLD",
                        "system_address": 93201,
                        "system_id64": 93201,
                        "x": 0.0,
                        "y": 0.0,
                        "z": 0.0,
                        "first_seen_ts": ts_old,
                        "last_seen_ts": ts_old,
                        "freshness_ts": ts_old,
                    },
                    {
                        "system_name": "F31_SESSION_RECENT",
                        "system_address": 93202,
                        "system_id64": 93202,
                        "x": 10.0,
                        "y": 0.0,
                        "z": 10.0,
                        "first_seen_ts": ts_recent,
                        "last_seen_ts": ts_recent,
                        "freshness_ts": ts_recent,
                    },
                ]
            )

            frame = JournalMapTab(root, data_provider=provider)
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            frame.render_mode_var.set("Mapa")

            frame.last_session_only_var.set(True)
            frame._on_last_session_toggled()
            out = frame.reload_from_playerdb()
            self.assertTrue(bool(out.get("ok")))

            self.assertEqual(str(frame.time_range_slider.cget("state")), "disabled")
            self.assertEqual(str(frame.freshness_slider.cget("state")), "disabled")

            names = {str(getattr(node, "system_name", "")) for node in frame._nodes.values()}
            self.assertIn("F31_SESSION_RECENT", names)
            self.assertNotIn("F31_SESSION_OLD", names)
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

    def test_persisted_state_roundtrip_includes_last_session_and_slider_labels(self) -> None:
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
            frame = JournalMapTab(root, data_provider=_ProviderStub([]))
            frame._cancel_pending_after_jobs()
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            frame.apply_persisted_ui_state(
                {
                    "filters": {
                        "time_range": "365d",
                        "freshness": "<=24h",
                        "last_session_only": True,
                    }
                }
            )

            self.assertEqual(str(frame.time_range_var.get()), "365d")
            self.assertEqual(str(frame.freshness_var.get()), "<=24h")
            self.assertTrue(bool(frame.last_session_only_var.get()))
            self.assertEqual(str(frame.time_range_label_var.get()), "365d")
            self.assertEqual(str(frame.freshness_label_var.get()), "<=24h")
            self.assertEqual(str(frame.time_range_slider.cget("state")), "disabled")
            self.assertEqual(str(frame.freshness_slider.cget("state")), "disabled")

            exported = frame.export_persisted_ui_state()
            self.assertTrue(bool(((exported.get("filters") or {}).get("last_session_only"))))
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
