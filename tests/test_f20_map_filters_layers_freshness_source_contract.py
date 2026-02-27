from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F20MapFiltersLayersFreshnessSourceContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        fresh_ts = _iso(now - timedelta(hours=1))
        old_ts = _iso(now - timedelta(days=10))

        # Fresh system with market + UC
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": fresh_ts,
                "StarSystem": "F20_FLT_FRESH",
                "SystemAddress": 99101,
                "SystemId64": 99101,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": fresh_ts,
                "StarSystem": "F20_FLT_FRESH",
                "SystemAddress": 99101,
                "StationName": "Fresh Port",
                "StationType": "Orbis Starport",
                "MarketID": 9910101,
                "DistFromStarLS": 500,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": fresh_ts,
                "StarSystem": "F20_FLT_FRESH",
                "StationName": "Fresh Port",
                "MarketID": 9910101,
                "Items": [{"Name_Localised": "Gold", "BuyPrice": 8000, "SellPrice": 11000}],
            },
            path=db_path,
        )

        # Old system with market + Vista
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": old_ts,
                "StarSystem": "F20_FLT_OLD",
                "SystemAddress": 99102,
                "SystemId64": 99102,
                "StarPos": [20.0, 0.0, 3.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": old_ts,
                "StarSystem": "F20_FLT_OLD",
                "SystemAddress": 99102,
                "StationName": "Old Vista Hub",
                "StationType": "Coriolis Starport",
                "MarketID": 9910201,
                "DistFromStarLS": 1500,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": old_ts,
                "StarSystem": "F20_FLT_OLD",
                "StationName": "Old Vista Hub",
                "MarketID": 9910201,
                "Items": [{"Name_Localised": "Silver", "BuyPrice": 3000, "SellPrice": 5400}],
            },
            path=db_path,
        )

    def test_filters_layers_and_freshness_change_map_view(self) -> None:
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
                root.geometry("1200x720")
                root.update()

                frame.layer_stations_var.set(True)
                frame.layer_trade_var.set(True)
                frame.layer_cashin_var.set(True)
                frame.freshness_var.set("any")
                result_any = frame.reload_from_playerdb()
                root.update_idletasks()

                self.assertTrue(bool(result_any.get("ok")))
                self.assertGreaterEqual(int(result_any.get("nodes") or 0), 2)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_stations")), 0)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_trade")), 0)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_cashin")), 0)

                # Toggle trade layer off -> trade overlay markers should disappear.
                frame.layer_trade_var.set(False)
                result_no_trade = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertTrue(bool(result_no_trade.get("ok")))
                self.assertEqual(len(frame.map_canvas.find_withtag("layer_trade")), 0)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_stations")), 0)

                # Freshness filter should drop old system and keep only fresh one.
                frame.layer_trade_var.set(True)
                frame.freshness_var.set("<=6h")
                result_fresh = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertEqual(int(result_fresh.get("nodes") or 0), 1)
                node_names = {str(n.system_name) for n in (frame._nodes or {}).values()}
                self.assertEqual(node_names, {"F20_FLT_FRESH"})
                status = str(frame.map_status_var.get() or "").lower()
                self.assertIn("freshness", status)
                self.assertIn("layers", status)

                # Empty-state when Travel off (still no crash, clear status).
                frame.layer_travel_var.set(False)
                result_travel_off = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertFalse(bool(result_travel_off.get("travel_enabled")))
                self.assertEqual(int(result_travel_off.get("nodes") or 0), 0)
                self.assertIn("warstwa travel jest wylaczona", str(frame.map_status_var.get()).lower())
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
        self.assertIn("_passes_freshness_filter", content)
        self.assertIn("_compute_layer_flags_for_nodes", content)
        self.assertIn("layer_stations", content)
        self.assertIn("layer_trade", content)
        self.assertIn("layer_cashin", content)

    def test_layer_flags_use_batched_station_lookup_when_available(self) -> None:
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

        class _FakeProvider:
            def __init__(self) -> None:
                self.batch_calls = 0
                self.single_calls = 0

            def get_system_action_flags(self, **_kwargs):
                return {
                    "f20_batch_a": {"has_exobio": True, "has_exploration": False, "last_action_ts": "2026-02-27T10:00:00Z"},
                }, {"ok": True}

            def get_station_layer_flags_for_systems(self, **_kwargs):
                self.batch_calls += 1
                return {
                    "addr:101": {
                        "stations_count": 2,
                        "has_market": True,
                        "has_cashin": True,
                    },
                    "name:f20_batch_b": {
                        "stations_count": 1,
                        "has_market": False,
                        "has_cashin": True,
                    },
                }, {"ok": True}

            def get_stations_for_system(self, **_kwargs):
                self.single_calls += 1
                return [], {"ok": True}

        provider = _FakeProvider()
        frame = None
        try:
            frame = JournalMapTab(root, data_provider=provider)
            rows = [
                {"key": "NODE_A", "system_name": "F20_BATCH_A", "system_address": 101},
                {"key": "NODE_B", "system_name": "F20_BATCH_B"},
            ]
            flags = frame._compute_layer_flags_for_nodes(rows)

            self.assertEqual(provider.batch_calls, 1)
            self.assertEqual(provider.single_calls, 0)
            self.assertTrue(bool(flags["NODE_A"]["has_station"]))
            self.assertTrue(bool(flags["NODE_A"]["has_market"]))
            self.assertTrue(bool(flags["NODE_A"]["has_cashin"]))
            self.assertTrue(bool(flags["NODE_A"]["has_exobio"]))
            self.assertEqual(int(flags["NODE_A"]["stations_count"]), 2)
            self.assertTrue(bool(flags["NODE_B"]["has_station"]))
            self.assertFalse(bool(flags["NODE_B"]["has_market"]))
            self.assertTrue(bool(flags["NODE_B"]["has_cashin"]))
            self.assertEqual(int(flags["NODE_B"]["stations_count"]), 1)
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

    def test_filter_change_hides_tooltip_to_avoid_stale_layer_badges(self) -> None:
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
            frame = JournalMapTab(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            frame.set_graph_data(
                nodes=[{"key": "N1", "system_name": "F20_TOOLTIP", "x": 0.0, "y": 0.0}],
                edges=[],
            )
            frame._node_layer_flags = {"N1": {"has_station": True, "stations_count": 1}}
            node = frame._nodes.get("N1")
            self.assertIsNotNone(node)

            frame.layer_stations_var.set(True)
            frame._show_map_tooltip(node, sx=24, sy=24)  # type: ignore[arg-type]
            self.assertTrue(bool(frame._tooltip_visible))
            self.assertIn("Stations", str(frame._tooltip_text_cache or ""))
            self.assertGreater(len(frame.map_canvas.find_withtag("map_tooltip")), 0)

            # Simulate filter/layer change with no-op reload path.
            frame.reload_from_playerdb = lambda: {"ok": True}  # type: ignore[assignment]
            frame.layer_stations_var.set(False)
            frame._on_filter_changed()

            self.assertFalse(bool(frame._tooltip_visible))
            self.assertEqual(str(frame._tooltip_text_cache or ""), "")
            self.assertEqual(len(frame.map_canvas.find_withtag("map_tooltip")), 0)
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

    def test_filter_changes_are_debounced_into_single_reload(self) -> None:
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
            frame = JournalMapTab(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            frame._cancel_pending_after_jobs()
            frame._cancel_filter_reload_debounce()
            frame._filter_reload_debounce_ms = 20

            reload_calls: list[str] = []
            frame.reload_from_playerdb = lambda: (reload_calls.append("reload") or {"ok": True})  # type: ignore[assignment]

            frame._on_filter_changed()
            frame._on_filter_changed()
            frame._on_filter_changed()
            root.update()
            self.assertEqual(reload_calls, [])

            time.sleep(0.06)
            root.update()
            self.assertEqual(reload_calls, ["reload"])
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
