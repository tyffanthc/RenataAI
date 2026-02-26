from __future__ import annotations

import json
import unittest

from logic.events import exploration_bio_events as bio_events


class F41ExobioStateTupleKeyJsonRoundtripTests(unittest.TestCase):
    def setUp(self) -> None:
        bio_events.reset_bio_flags(persist=False)

    def tearDown(self) -> None:
        bio_events.reset_bio_flags(persist=False)

    def test_snapshot_payload_is_json_serializable_and_roundtrips_tuple_keys(self) -> None:
        key_in_progress = ("f41 system", "f41 system 1 a", "aleoida arcus")
        key_complete = ("f41 system", "f41 system 2 b", "bacterium aurasus")

        bio_events.EXOBIO_SAMPLE_COUNT = {
            key_in_progress: 2,
            key_complete: 3,
        }
        bio_events.EXOBIO_SAMPLE_COMPLETE = {key_complete}
        bio_events.EXOBIO_RANGE_READY_WARNED = {key_in_progress, key_complete}
        bio_events.EXOBIO_RANGE_TRACKERS = {
            key_in_progress: {
                "threshold_m": 500.0,
                "lat": 10.5,
                "lon": 20.5,
                "radius_m": 1000.0,
                "pending": True,
                "body": "F41 System 1 A",
                "system": "F41 System",
            },
            key_complete: {
                "threshold_m": 300.0,
                "lat": 11.0,
                "lon": 21.0,
                "pending": False,
                "body": "F41 System 2 B",
                "system": "F41 System",
            },
        }
        bio_events.EXOBIO_RECOVERY_UNCERTAIN_KEYS = {key_in_progress}
        bio_events.EXOBIO_LAST_STATUS_POS = {
            "lat": 10.5,
            "lon": 20.5,
            "radius_m": 1000.0,
            "body": "F41 System 1 A",
            "system": "F41 System",
            "ts": 1234567890.0,  # must not be persisted
        }

        payload = bio_events._snapshot_exobio_state_payload()

        # Regression target: tuple keys must be serialized to JSON-safe string keys.
        self.assertTrue(all(isinstance(k, str) for k in payload.get("sample_count_by_key", {}).keys()))
        self.assertTrue(all(isinstance(k, str) for k in payload.get("range_trackers", {}).keys()))
        self.assertNotIn("ts", dict(payload.get("last_status_pos") or {}))

        encoded = json.dumps(payload)
        self.assertIsInstance(encoded, str)
        decoded = json.loads(encoded)

        bio_events.reset_bio_flags(persist=False)
        stats = bio_events._apply_exobio_state_payload(decoded)

        self.assertGreaterEqual(int(stats.get("sample_keys") or 0), 2)
        self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key_in_progress, 0)), 2)
        self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key_complete, 0)), 3)
        self.assertIn(key_complete, bio_events.EXOBIO_SAMPLE_COMPLETE)
        self.assertIn(key_in_progress, bio_events.EXOBIO_RECOVERY_UNCERTAIN_KEYS)

        # Completed keys should not keep active trackers after restore.
        self.assertIn(key_in_progress, bio_events.EXOBIO_RANGE_TRACKERS)
        self.assertNotIn(key_complete, bio_events.EXOBIO_RANGE_TRACKERS)

        restored_pos = dict(bio_events.EXOBIO_LAST_STATUS_POS or {})
        self.assertEqual(restored_pos.get("body"), "f41 system 1 a")
        self.assertEqual(restored_pos.get("system"), "f41 system")
        self.assertNotIn("ts", restored_pos)


if __name__ == "__main__":
    unittest.main()
