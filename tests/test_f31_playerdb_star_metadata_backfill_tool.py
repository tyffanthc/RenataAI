from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from tools.playerdb_backfill_star_metadata import run_backfill


class F31PlayerDbStarMetadataBackfillToolTests(unittest.TestCase):
    def test_backfill_updates_star_metadata_from_journal_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "db", "player_local.db")
            log_dir = os.path.join(tmp, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "Journal.2026-02-28T120000.01.log")

            events = [
                {
                    "event": "FSDJump",
                    "timestamp": "2026-02-28T12:00:00Z",
                    "StarSystem": "F31_BF_NEUTRON",
                    "SystemAddress": 771001,
                    "SystemId64": 771001,
                    "StarPos": [1.0, 2.0, 3.0],
                    "StarClass": "N",
                },
                {
                    "event": "Scan",
                    "timestamp": "2026-02-28T12:01:00Z",
                    "StarSystem": "F31_BF_HOLE",
                    "SystemAddress": 771002,
                    "SystemId64": 771002,
                    "BodyType": "Star",
                    "BodyName": "F31_BF_HOLE A",
                    "StarType": "Black Hole",
                },
            ]
            with open(log_path, "w", encoding="utf-8") as handle:
                for ev in events:
                    handle.write(json.dumps(ev, ensure_ascii=False) + "\n")

            out = run_backfill(db_path=db_path, log_dir=log_dir)
            self.assertTrue(bool(out.get("ok")))
            self.assertEqual(int(out.get("updated_systems") or 0), 2)

            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                neutron = conn.execute(
                    "SELECT primary_star_type, is_neutron, is_black_hole FROM systems WHERE system_name=?",
                    ("F31_BF_NEUTRON",),
                ).fetchone()
                self.assertIsNotNone(neutron)
                self.assertEqual(str(neutron["primary_star_type"] or ""), "N")
                self.assertEqual(int(neutron["is_neutron"] or 0), 1)
                self.assertEqual(int(neutron["is_black_hole"] or 0), 0)

                hole = conn.execute(
                    "SELECT primary_star_type, is_neutron, is_black_hole FROM systems WHERE system_name=?",
                    ("F31_BF_HOLE",),
                ).fetchone()
                self.assertIsNotNone(hole)
                self.assertEqual(str(hole["primary_star_type"] or ""), "Black Hole")
                self.assertEqual(int(hole["is_neutron"] or 0), 0)
                self.assertEqual(int(hole["is_black_hole"] or 0), 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

