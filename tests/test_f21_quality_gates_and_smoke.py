from __future__ import annotations

import os
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _DummyOwner:
    def map_get_available_entry_categories(self):
        return ["Exploracja/Skoki", "Mapa/Punkty"]

    def map_create_entry_for_system(self, system_name: str, *, category_path=None, edit_after=False):
        return {
            "ok": True,
            "entry_id": "F21_SMOKE_ENTRY",
            "system_name": system_name,
            "category_path": category_path,
            "edit_after": bool(edit_after),
        }


class _DummyNeutronVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value) -> None:
        self.value = str(value or "")


class _DummyNeutronTab:
    def __init__(self) -> None:
        self.var_start = _DummyNeutronVar()
        self.var_cel = _DummyNeutronVar()
        self.run_called = False

    def run_neutron(self):
        self.run_called = True


class _DummyApp:
    def __init__(self) -> None:
        self.tab_spansh = types.SimpleNamespace(tab_neutron=_DummyNeutronTab())
        self.status_calls: list[str] = []

    def show_status(self, msg: str) -> None:
        self.status_calls.append(str(msg))


class F21QualityGatesAndSmokeTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts_a = _iso(now - timedelta(hours=1))
        ts_b = _iso(now - timedelta(hours=3))

        # Systems
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts_a,
                "StarSystem": "F21_QG_ALPHA",
                "SystemAddress": 441001,
                "SystemId64": 441001,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": ts_b,
                "StarSystem": "F21_QG_BETA",
                "SystemAddress": 441002,
                "SystemId64": 441002,
                "StarPos": [14.0, 0.0, 4.0],
            },
            path=db_path,
        )

        # Stations + markets
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_a,
                "StarSystem": "F21_QG_ALPHA",
                "SystemAddress": 441001,
                "StationName": "Alpha Port",
                "StationType": "Orbis Starport",
                "MarketID": 44100101,
                "DistFromStarLS": 600,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_a,
                "StarSystem": "F21_QG_ALPHA",
                "StationName": "Alpha Port",
                "MarketID": 44100101,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 9000, "SellPrice": 12000},
                    {"Name_Localised": "Silver", "BuyPrice": 3000, "SellPrice": 5000},
                ],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "SellExplorationData",
                "timestamp": ts_a,
                "StarSystem": "F21_QG_ALPHA",
                "StationName": "Alpha Port",
                "TotalEarnings": 111111,
            },
            path=db_path,
        )

        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts_b,
                "StarSystem": "F21_QG_BETA",
                "SystemAddress": 441002,
                "StationName": "Beta Vista",
                "StationType": "Coriolis Starport",
                "MarketID": 44100201,
                "DistFromStarLS": 1400,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": ts_b,
                "StarSystem": "F21_QG_BETA",
                "StationName": "Beta Vista",
                "MarketID": 44100201,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000},
                    {"Name_Localised": "Palladium", "BuyPrice": 40000, "SellPrice": 52000},
                ],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "SellOrganicData",
                "timestamp": ts_b,
                "StarSystem": "F21_QG_BETA",
                "StationName": "Beta Vista",
                "TotalEarnings": 222222,
            },
            path=db_path,
        )

    def test_smoke_f21_map_ux_hover_zoom_ppm_and_trade_modal(self) -> None:
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
                frame = JournalMapTab(root, data_provider=provider, app=_DummyApp(), logbook_owner=_DummyOwner())
                frame.pack(fill="both", expand=True)
                root.update_idletasks()
                root.geometry("1320x820")
                root.update()

                # Enable richer overlays and load map.
                frame.layer_trade_var.set(True)
                frame.layer_cashin_var.set(True)
                frame.layer_exobio_var.set(True)
                frame.layer_exploration_var.set(True)
                result = frame.reload_from_playerdb()
                root.update_idletasks()
                self.assertTrue(bool(result.get("ok")))
                self.assertGreaterEqual(int(result.get("nodes") or 0), 2)

                # Tooltip on hover (simulate current node deterministically).
                any_key = next(iter(frame._nodes.keys()))
                node = frame._nodes[any_key]
                sx, sy = frame.world_to_screen(node.x, node.y)
                original_current_key = frame._canvas_current_node_key
                frame._canvas_current_node_key = lambda: any_key  # type: ignore[assignment]
                try:
                    frame._on_canvas_node_motion(types.SimpleNamespace(x=int(sx), y=int(sy)))
                    root.update_idletasks()
                    self.assertGreater(len(frame.map_canvas.find_withtag("map_tooltip")), 0)
                    tooltip_text_items = frame.map_canvas.find_withtag("map_tooltip_text")
                    self.assertGreaterEqual(len(tooltip_text_items), 1)
                    text = str(frame.map_canvas.itemcget(tooltip_text_items[0], "text") or "").lower()
                    self.assertIn("system:", text)
                    self.assertIn("last seen:", text)
                    self.assertIn("stacje:", text)
                finally:
                    frame._canvas_current_node_key = original_current_key  # type: ignore[assignment]

                # Zoom while tooltip visible should not crash and tooltip should be hidden/rebuilt safely.
                frame._on_canvas_mousewheel(types.SimpleNamespace(x=int(sx), y=int(sy), delta=120))
                root.update_idletasks()
                self.assertEqual(len(frame.map_canvas.find_withtag("map_tooltip")), 0)

                # PPM state setup on node should not crash and keeps assistant actions available.
                frame._map_ppm_node_key = any_key
                frame._map_ppm_rebuild_add_entry_menu()
                frame._map_ppm_set_menu_states()
                set_target_state = str(frame._map_context_menu.entrycget("Ustaw cel", "state"))
                self.assertEqual(set_target_state, "normal")

                # Trade Compare v2 modal and highlight by active row.
                frame._open_trade_commodity_picker()
                root.update_idletasks()
                frame._trade_picker_selected = {"Gold", "Silver"}
                frame._trade_picker_accept()
                root.update_idletasks()
                rows = frame.trade_compare_tree.get_children()
                self.assertGreaterEqual(len(rows), 2)
                frame.trade_compare_tree.selection_set(rows[0])
                frame._on_trade_compare_row_selected()
                root.update_idletasks()
                self.assertGreaterEqual(len(frame._trade_highlight_node_keys), 1)

                # No crash / readable final status.
                status = str(frame.map_status_var.get() or "")
                self.assertTrue(status.strip())
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
