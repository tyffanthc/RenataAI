from __future__ import annotations

import json
import os
import queue
import tempfile
import unittest
from unittest.mock import patch

from logic import player_local_db
from logic.event_handler import EventHandler
from logic.personal_map_data_provider import MapDataProvider
from logic.utils import MSG_QUEUE


def _runtime_db_snapshot(path: str) -> tuple[bool, int, int]:
    try:
        st = os.stat(path)
        return (True, int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))))
    except FileNotFoundError:
        return (False, 0, 0)


class F29QualityGatesAndSmokeTests(unittest.TestCase):
    def _drain_queue(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        while True:
            try:
                out.append(MSG_QUEUE.get_nowait())
            except queue.Empty:
                break
        return out

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "db", "player_local.db")
        self._runtime_db_path = player_local_db.default_playerdb_path()
        self.assertNotEqual(os.path.abspath(self._db_path), os.path.abspath(self._runtime_db_path))
        self._runtime_before = _runtime_db_snapshot(self._runtime_db_path)
        self._default_path_patch = patch(
            "logic.player_local_db.default_playerdb_path",
            return_value=self._db_path,
        )
        self._default_path_patch.start()
        self._drain_queue()

    def tearDown(self) -> None:
        self._drain_queue()
        self._default_path_patch.stop()
        self._tmp.cleanup()

    def test_quality_gate_f29_eventhandler_replay_uses_temp_playerdb_and_leaves_runtime_db_untouched(self) -> None:
        router = EventHandler()
        events = [
            {
                "event": "Location",
                "timestamp": "2026-02-24T19:00:00Z",
                "StarSystem": "F29_SMOKE_ORIGIN",
                "SystemAddress": 29001001,
                "SystemId64": 29001001,
                "StarPos": [0.0, 0.0, 0.0],
            },
            {
                "event": "FSDJump",
                "timestamp": "2026-02-24T19:01:00Z",
                "StarSystem": "F29_SMOKE_TARGET",
                "SystemAddress": 29001002,
                "SystemId64": 29001002,
                "StarPos": [15.0, 0.0, 5.0],
                "JumpDist": 15.8,
            },
            {
                "event": "Docked",
                "timestamp": "2026-02-24T19:02:00Z",
                "StarSystem": "F29_SMOKE_TARGET",
                "SystemAddress": 29001002,
                "StationName": "F29 Smoke Port",
                "StationType": "Orbis Starport",
                "MarketID": 29002001,
                "DistFromStarLS": 420,
                "StationServices": ["Commodities", "Universal Cartographics", "Vista Genomics"],
            },
            {
                "event": "SellExplorationData",
                "timestamp": "2026-02-24T19:03:00Z",
                "StarSystem": "F29_SMOKE_TARGET",
                "StationName": "F29 Smoke Port",
                "TotalEarnings": 123456,
            },
            {
                "event": "SellOrganicData",
                "timestamp": "2026-02-24T19:04:00Z",
                "StarSystem": "F29_SMOKE_TARGET",
                "StationName": "F29 Smoke Port",
                "TotalEarnings": 654321,
            },
        ]
        for ev in events:
            router.handle_event(json.dumps(ev))
        router.on_market_update(
            {
                "timestamp": "2026-02-24T19:02:30Z",
                "StarSystem": "F29_SMOKE_TARGET",
                "StationName": "F29 Smoke Port",
                "MarketID": 29002001,
                "Items": [
                    {"Name_Localised": "Gold", "BuyPrice": 8400, "SellPrice": 12600},
                    {"Name_Localised": "Silver", "BuyPrice": 3200, "SellPrice": 5200},
                ],
            }
        )

        self.assertTrue(os.path.exists(self._db_path))
        self.assertGreater(int(os.path.getsize(self._db_path) or 0), 0)

        # F19/F29 feed path should still emit captain-logbook feed items.
        feed_items = [payload for kind, payload in self._drain_queue() if kind == "logbook_journal_feed"]
        self.assertGreaterEqual(len(feed_items), 4)

        # F20/F21 map provider path should default to the patched temp DB.
        provider = MapDataProvider()
        self.assertEqual(os.path.abspath(provider.db_path), os.path.abspath(self._db_path))

        nodes, _ = provider.get_system_nodes(time_range="all", source_filter="observed_only")
        self.assertTrue(any(str(r.get("system_name") or "") == "F29_SMOKE_TARGET" for r in nodes))

        stations, _ = provider.get_stations_for_system(system_name="F29_SMOKE_TARGET")
        self.assertTrue(any(str(r.get("station_name") or "") == "F29 Smoke Port" for r in stations))

        commodities, _ = provider.get_known_commodities(time_range="all", freshness_filter="any", limit=20)
        self.assertIn("Gold", [str(x) for x in commodities])

        history = player_local_db.query_cashin_history(service="all", limit=10, path=self._db_path)
        self.assertGreaterEqual(len(history), 2)

        self.assertEqual(_runtime_db_snapshot(self._runtime_db_path), self._runtime_before)

    def test_smoke_f29_tk_map_uses_patched_playerdb_without_touching_runtime_db(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        router = EventHandler()
        router.handle_event(
            json.dumps(
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-24T20:00:00Z",
                    "StarSystem": "F29_TK_SYS",
                    "SystemAddress": 29003001,
                    "SystemId64": 29003001,
                    "StarPos": [2.0, 0.0, 2.0],
                    "JumpDist": 8.2,
                }
            )
        )
        self._drain_queue()

        root = None
        frame = None
        try:
            root = tk.Tk()
            root.withdraw()
            from gui.tabs.journal_map import JournalMapTab

            frame = JournalMapTab(root, data_provider=MapDataProvider())
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            result = frame.reload_from_playerdb()
            root.update_idletasks()

            self.assertTrue(bool(result.get("ok")))
            self.assertGreaterEqual(int(result.get("nodes") or 0), 1)
            self.assertEqual(os.path.abspath(frame.data_provider.db_path), os.path.abspath(self._db_path))
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")
        finally:
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass
            try:
                if root is not None:
                    root.destroy()
            except Exception:
                pass

        self.assertEqual(_runtime_db_snapshot(self._runtime_db_path), self._runtime_before)


if __name__ == "__main__":
    unittest.main()

