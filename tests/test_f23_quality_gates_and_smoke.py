from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.events import fuel_events
from logic.event_handler import EventHandler
from gui import window_focus


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def deiconify(self) -> None:
        self.calls.append("deiconify")

    def lift(self) -> None:
        self.calls.append("lift")

    def focus_set(self) -> None:
        self.calls.append("focus_set")

    def focus_force(self) -> None:
        self.calls.append("focus_force")

    def title(self) -> str:
        return "RuntimeSmoke"


class F23QualityGatesAndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_warned = fuel_events.LOW_FUEL_WARNED
        self._saved_pending = fuel_events.LOW_FUEL_FLAG_PENDING
        self._saved_pending_ts = fuel_events.LOW_FUEL_FLAG_PENDING_TS
        self._saved_initialized = bool(getattr(fuel_events, "_FUEL_STATUS_INITIALIZED", False))
        self._saved_seen_valid = bool(getattr(fuel_events, "_FUEL_SEEN_VALID_SAMPLE", False))
        fuel_events.LOW_FUEL_WARNED = False
        fuel_events.LOW_FUEL_FLAG_PENDING = False
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = 0.0
        fuel_events._FUEL_STATUS_INITIALIZED = False
        fuel_events._FUEL_SEEN_VALID_SAMPLE = False

    def tearDown(self) -> None:
        fuel_events.LOW_FUEL_WARNED = self._saved_warned
        fuel_events.LOW_FUEL_FLAG_PENDING = self._saved_pending
        fuel_events.LOW_FUEL_FLAG_PENDING_TS = self._saved_pending_ts
        fuel_events._FUEL_STATUS_INITIALIZED = self._saved_initialized
        fuel_events._FUEL_SEEN_VALID_SAMPLE = self._saved_seen_valid

    def test_smoke_f23_focus_policy_blocks_runtime_force_but_keeps_user_dialog_focus(self) -> None:
        win_runtime = _FakeWindow()
        blocked = window_focus.request_window_focus(
            win_runtime,
            source="f23.smoke.runtime",
            user_initiated=False,
            force=True,
        )
        self.assertFalse(blocked)
        self.assertEqual(win_runtime.calls, [])

        win_runtime_front = _FakeWindow()
        blocked_front = window_focus.bring_window_to_front(
            win_runtime_front,
            source="f23.smoke.runtime.front",
            user_initiated=False,
            deiconify=True,
            request_focus=True,
            force_focus=False,
        )
        self.assertFalse(blocked_front)
        self.assertEqual(win_runtime_front.calls, [])

        win_dialog = _FakeWindow()
        ok = window_focus.bring_window_to_front(
            win_dialog,
            source="f23.smoke.user_dialog",
            user_initiated=True,
            deiconify=True,
            request_focus=True,
            force_focus=False,
        )
        self.assertTrue(ok)
        self.assertEqual(win_dialog.calls, ["deiconify", "lift", "focus_set"])

    def test_smoke_f23_event_router_emits_playerdb_updated_for_journal_and_market(self) -> None:
        handler = EventHandler()
        queued: list[tuple[str, object]] = []

        with (
            patch("logic.event_handler.player_local_db.ingest_journal_event") as ingest_journal,
            patch("logic.event_handler.player_local_db.ingest_market_json") as ingest_market,
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
            patch("logic.event_handler.MSG_QUEUE.put", side_effect=lambda item: queued.append(item)),
            patch("logic.event_handler.cargo_value_estimator.update_market_snapshot"),
            patch("logic.event_handler.trade_events.handle_market_data"),
        ):
            ingest_journal.return_value = None
            ingest_market.return_value = None

            handler.handle_event(
                '{"event":"FSDJump","timestamp":"2026-02-23T12:00:00Z","StarSystem":"F23_SMOKE_SYS","SystemAddress":1,"StarPos":[0,0,0]}'
            )
            handler.on_market_update(
                {
                    "timestamp": "2026-02-23T12:01:00Z",
                    "StarSystem": "F23_SMOKE_SYS",
                    "StationName": "Smoke Port",
                    "MarketID": 123,
                    "Items": [{"Name_Localised": "Gold", "SellPrice": 10000}],
                }
            )

        playerdb_msgs = [item for item in queued if isinstance(item, tuple) and item and item[0] == "playerdb_updated"]
        self.assertGreaterEqual(len(playerdb_msgs), 2)
        payloads = [dict(item[1]) for item in playerdb_msgs if isinstance(item[1], dict)]
        self.assertTrue(any(str(p.get("event_name")) == "FSDJump" for p in payloads))
        self.assertTrue(any(str(p.get("event_name")) == "Market" for p in payloads))

    def test_smoke_f23_scan_ingests_star_metadata_and_emits_playerdb_updated(self) -> None:
        handler = EventHandler()
        queued: list[tuple[str, object]] = []

        with (
            patch("logic.event_handler.player_local_db.ingest_star_metadata_event") as ingest_star_meta,
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
            patch("logic.event_handler.MSG_QUEUE.put", side_effect=lambda item: queued.append(item)),
            patch("app.state.app_state.system_value_engine.analyze_scan_event"),
            patch("logic.event_handler.exploration_fss_events.handle_scan"),
            patch("logic.event_handler.exploration_dss_events.handle_dss_target_hint"),
        ):
            ingest_star_meta.return_value = {"ok": True, "primary_star_type": "M"}
            handler.handle_event(
                '{"event":"Scan","timestamp":"2026-02-23T12:02:00Z","StarSystem":"F23_SCAN_META_SYS","SystemAddress":11,"BodyType":"Star","StarType":"M"}'
            )

        ingest_star_meta.assert_called_once()
        playerdb_msgs = [item for item in queued if isinstance(item, tuple) and item and item[0] == "playerdb_updated"]
        self.assertGreaterEqual(len(playerdb_msgs), 1)
        payloads = [dict(item[1]) for item in playerdb_msgs if isinstance(item[1], dict)]
        self.assertTrue(any(str(p.get("event_name")) == "Scan" for p in payloads))

    def test_smoke_f23_fuel_transient_guard_and_real_alert(self) -> None:
        uncertain_status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 0.08},
            "FuelCapacity": {},
        }
        real_low_status = {
            "Docked": False,
            "LowFuel": False,
            "Fuel": {"FuelMain": 2.0},
            "FuelCapacity": {"Main": 20.0},
            "StarSystem": "F23_SMOKE_FUEL",
        }

        with (
            patch("logic.events.fuel_events.emit_insight", return_value=True) as emit_mock,
            patch.object(fuel_events.DEBOUNCER, "can_send", return_value=True),
        ):
            fuel_events.handle_status_update(uncertain_status)
            fuel_events.handle_status_update(uncertain_status)
            self.assertEqual(emit_mock.call_count, 0)
            self.assertFalse(bool(fuel_events.LOW_FUEL_FLAG_PENDING))
            self.assertFalse(bool(fuel_events.LOW_FUEL_WARNED))

            fuel_events.handle_status_update(real_low_status)

        self.assertEqual(emit_mock.call_count, 1)
        self.assertTrue(bool(fuel_events.LOW_FUEL_WARNED))


if __name__ == "__main__":
    unittest.main()
