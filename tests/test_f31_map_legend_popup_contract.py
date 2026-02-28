from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from logic import player_local_db
from logic.personal_map_data_provider import MapDataProvider


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _collect_label_texts(widget) -> list[str]:
    texts: list[str] = []
    try:
        for child in widget.winfo_children():
            try:
                if child.winfo_class() == "Label":
                    texts.append(str(child.cget("text") or ""))
            except Exception:
                pass
            texts.extend(_collect_label_texts(child))
    except Exception:
        return texts
    return texts


class F31MapLegendPopupContractTests(unittest.TestCase):
    def _seed_playerdb(self, db_path: str) -> None:
        now = datetime.now(timezone.utc)
        ts = _iso(now - timedelta(hours=1))
        player_local_db.ingest_journal_event(
            {
                "event": "Location",
                "timestamp": ts,
                "StarSystem": "F31_LEGEND_ALPHA",
                "SystemAddress": 881001,
                "SystemId64": 881001,
                "StarPos": [0.0, 0.0, 0.0],
                "StarClass": "G",
            },
            path=db_path,
        )
        player_local_db.ingest_journal_event(
            {
                "event": "Docked",
                "timestamp": ts,
                "StarSystem": "F31_LEGEND_ALPHA",
                "SystemAddress": 881001,
                "StationName": "Legend Port",
                "StationType": "Orbis Starport",
                "MarketID": 88100101,
                "StationServices": ["Commodities", "Universal Cartographics"],
            },
            path=db_path,
        )

    def test_legend_popup_stars_and_no_zoom_text(self) -> None:
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

                frame.reload_from_playerdb()
                root.update_idletasks()

                legend_text = str(frame.legend_text_var.get() or "").lower()
                self.assertNotIn("zoom", legend_text)
                self.assertIn("[o]", legend_text)
                self.assertIn("aktywne warstwy", legend_text)

                self.assertTrue(hasattr(frame, "legend_star_info_btn"))
                frame._show_star_legend_popup()
                root.update_idletasks()

                popup = getattr(frame, "_star_legend_popup", None)
                self.assertIsNotNone(popup)
                self.assertTrue(bool(popup.winfo_exists()))
                labels = [x.strip().lower() for x in _collect_label_texts(popup) if x.strip()]
                joined = " | ".join(labels)
                self.assertIn("legenda gwiazd", joined)
                self.assertIn("neutron", joined)
                self.assertIn("black hole", joined)

                frame._hide_star_legend_popup(force=True)
                root.update_idletasks()
                self.assertIsNone(getattr(frame, "_star_legend_popup", None))
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

