from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class F21MapActionBadgesLayersLegendContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        t_a = _iso(now - timedelta(hours=2))
        t_b = _iso(now - timedelta(hours=1))

        # System A -> exploration cash-in (UC)
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": t_a,
                "StarSystem": "F21_BADGE_A",
                "SystemAddress": 211001,
                "SystemId64": 211001,
                "StarPos": [0.0, 0.0, 0.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": t_a,
                "StarSystem": "F21_BADGE_A",
                "SystemAddress": 211001,
                "StationName": "Alpha Port",
                "StationType": "Orbis Starport",
                "MarketID": 21100101,
                "DistFromStarLS": 700,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": t_a,
                "StarSystem": "F21_BADGE_A",
                "StationName": "Alpha Port",
                "MarketID": 21100101,
                "Items": [{"Name_Localised": "Gold", "BuyPrice": 7000, "SellPrice": 11000}],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "SellExplorationData",
                "timestamp": t_a,
                "StarSystem": "F21_BADGE_A",
                "StationName": "Alpha Port",
                "TotalEarnings": 123456,
            },
            path=db_path,
        )

        # System B -> exobio cash-in (Vista)
        player_local_db.ingest_journal_event(
            {
                "event": "FSDJump",
                "timestamp": t_b,
                "StarSystem": "F21_BADGE_B",
                "SystemAddress": 211002,
                "SystemId64": 211002,
                "StarPos": [15.0, 0.0, 5.0],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": t_b,
                "StarSystem": "F21_BADGE_B",
                "SystemAddress": 211002,
                "StationName": "Vista Base",
                "StationType": "Coriolis Starport",
                "MarketID": 21100201,
                "DistFromStarLS": 1600,
                "StationServices": ["Commodities", "Vista Genomics"],
            },
            path=db_path,
        )
        player_local_db.ingest_market_json(
            {
                "timestamp": t_b,
                "StarSystem": "F21_BADGE_B",
                "StationName": "Vista Base",
                "MarketID": 21100201,
                "Items": [{"Name_Localised": "Silver", "BuyPrice": 3500, "SellPrice": 5400}],
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "SellOrganicData",
                "timestamp": t_b,
                "StarSystem": "F21_BADGE_B",
                "StationName": "Vista Base",
                "TotalEarnings": 654321,
            },
            path=db_path,
        )

    def test_action_badges_layers_legend_and_zoom_gating(self) -> None:
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
                root.geometry("1280x760")
                root.update()

                frame.layer_stations_var.set(True)
                frame.layer_trade_var.set(True)
                frame.layer_cashin_var.set(True)
                frame.layer_exobio_var.set(True)
                frame.layer_exploration_var.set(True)
                frame.layer_incidents_var.set(True)  # future-ready / no data in playerdb baseline
                frame.layer_combat_var.set(True)     # future-ready / no data in playerdb baseline
                result = frame.reload_from_playerdb()
                root.update_idletasks()

                self.assertTrue(bool(result.get("ok")))
                self.assertGreaterEqual(int(result.get("nodes") or 0), 2)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_exobio")), 0)
                self.assertGreater(len(frame.map_canvas.find_withtag("layer_exploration")), 0)

                legend_text = str(frame.legend_text_var.get() or "")
                legend_text_l = legend_text.lower()
                self.assertIn("aktywne warstwy", legend_text_l)
                self.assertIn("exobio", legend_text_l)
                self.assertIn("eksploracji", legend_text_l)
                self.assertIn("incidents: brak danych", legend_text_l)
                self.assertIn("combat: brak danych", legend_text_l)

                # Collapsible legend section.
                self.assertFalse(bool(frame.legend_collapsed_var.get()))
                frame._toggle_legend()
                self.assertTrue(bool(frame.legend_collapsed_var.get()))
                self.assertEqual(str(frame.legend_body_frame.winfo_manager() or ""), "")
                frame._toggle_legend()
                self.assertFalse(bool(frame.legend_collapsed_var.get()))
                self.assertEqual(str(frame.legend_body_frame.winfo_manager() or ""), "grid")

                # Zoom-gated readability: action badges hidden on very low zoom.
                frame.view_scale = 0.35
                frame._redraw_scene()
                root.update_idletasks()
                self.assertEqual(len(frame.map_canvas.find_withtag("layer_exobio")), 0)
                self.assertEqual(len(frame.map_canvas.find_withtag("layer_exploration")), 0)
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
