from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from logic.event_handler import EventHandler, _apply_sell_value_domain_reset


class _DummyValueEngine:
    def __init__(self) -> None:
        self.domain_calls: list[tuple[str, str | None]] = []
        self.totals = {
            "c_cartography": 120.0,
            "c_exobiology": 80.0,
            "bonus_discovery": 30.0,
            "total": 230.0,
        }

    def calculate_totals(self) -> dict[str, float]:
        return dict(self.totals)

    def clear_value_domain(self, *, domain: str = "all", system_name: str | None = None) -> dict[str, int | str | None]:
        self.domain_calls.append((str(domain), (str(system_name) if system_name is not None else None)))
        if domain == "cartography":
            self.totals["c_cartography"] = 0.0
            self.totals["bonus_discovery"] = 10.0
        elif domain == "exobiology":
            self.totals["c_exobiology"] = 0.0
            self.totals["bonus_discovery"] = 20.0
        else:
            self.totals["c_cartography"] = 0.0
            self.totals["c_exobiology"] = 0.0
            self.totals["bonus_discovery"] = 0.0
        self.totals["total"] = (
            float(self.totals["c_cartography"])
            + float(self.totals["c_exobiology"])
            + float(self.totals["bonus_discovery"])
        )
        return {
            "systems_touched": 1 if system_name else 3,
            "scope": "single" if system_name else "all",
            "system_name": system_name,
        }


class F54EventHandlerSellValueDomainResetTests(unittest.TestCase):
    def test_apply_sell_value_domain_reset_handles_sell_exploration_data(self) -> None:
        engine = _DummyValueEngine()
        with (
            patch("app.state.app_state.system_value_engine", engine),
            patch("logic.event_handler.log_event") as log_event_mock,
        ):
            _apply_sell_value_domain_reset({"event": "SellExplorationData"})

        self.assertEqual(engine.domain_calls, [("cartography", None)])
        log_event_mock.assert_called_once()
        _args, kwargs = log_event_mock.call_args
        self.assertEqual(str(kwargs.get("domain")), "cartography")
        self.assertEqual(float(kwargs.get("before_total") or 0.0), 230.0)
        self.assertEqual(float(kwargs.get("after_total") or 0.0), 90.0)

    def test_apply_sell_value_domain_reset_handles_sell_organic_data(self) -> None:
        engine = _DummyValueEngine()
        with (
            patch("app.state.app_state.system_value_engine", engine),
            patch("logic.event_handler.log_event") as log_event_mock,
        ):
            _apply_sell_value_domain_reset({"event": "SellOrganicData"})

        self.assertEqual(engine.domain_calls, [("exobiology", None)])
        log_event_mock.assert_called_once()
        _args, kwargs = log_event_mock.call_args
        self.assertEqual(str(kwargs.get("domain")), "exobiology")
        self.assertEqual(float(kwargs.get("before_total") or 0.0), 230.0)
        self.assertEqual(float(kwargs.get("after_total") or 0.0), 140.0)

    def test_apply_sell_value_domain_reset_multisell_scopes_to_discovered_systems_when_available(self) -> None:
        engine = _DummyValueEngine()
        with (
            patch("app.state.app_state.system_value_engine", engine),
            patch("logic.event_handler.log_event") as log_event_mock,
        ):
            _apply_sell_value_domain_reset(
                {
                    "event": "MultiSellExplorationData",
                    "Discovered": [
                        {"SystemName": "SYS_A"},
                        ["SYS_B", 12345],
                        "SYS_A",
                    ],
                }
            )

        self.assertEqual(
            engine.domain_calls,
            [("cartography", "SYS_A"), ("cartography", "SYS_B")],
        )
        log_event_mock.assert_called_once()
        _args, kwargs = log_event_mock.call_args
        self.assertEqual(str(kwargs.get("domain")), "cartography")
        self.assertEqual(str(kwargs.get("reset_scope")), "scoped")
        self.assertEqual(int(kwargs.get("scoped_systems") or 0), 2)

    def test_handle_event_sell_triggers_snapshot_and_domain_reset(self) -> None:
        handler = EventHandler()
        line = json.dumps(
            {
                "event": "SellExplorationData",
                "timestamp": "2026-02-27T12:00:00Z",
                "TotalEarnings": 123456,
                "StarSystem": "F54_SYS",
            }
        )

        with (
            patch("logic.event_handler.player_local_db.ingest_journal_event", return_value={"ok": True}),
            patch("logic.event_handler._emit_playerdb_updated"),
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
            patch("logic.event_handler.MSG_QUEUE.put"),
            patch("app.state.app_state.update_mode_signal_from_journal"),
            patch("logic.event_handler.high_g_warning.handle_journal_event"),
            patch("logic.event_handler.survival_rebuy_awareness.handle_journal_event"),
            patch("logic.event_handler.combat_awareness.handle_journal_event"),
            patch("logic.event_handler._log_sell_value_snapshot") as snapshot_mock,
            patch("logic.event_handler._apply_sell_value_domain_reset") as reset_mock,
        ):
            handler.handle_event(line, gui_ref=None)

        snapshot_mock.assert_called_once()
        reset_mock.assert_called_once()

    def test_handle_event_multisell_triggers_snapshot_and_domain_reset(self) -> None:
        handler = EventHandler()
        line = json.dumps(
            {
                "event": "MultiSellExplorationData",
                "timestamp": "2026-02-27T12:10:00Z",
                "TotalEarnings": 654321,
                "StarSystem": "F54_SYS_MULTI",
            }
        )

        with (
            patch("logic.event_handler.player_local_db.ingest_journal_event", return_value={"ok": True}),
            patch("logic.event_handler._emit_playerdb_updated"),
            patch("logic.event_handler.build_logbook_feed_item", return_value=None),
            patch("logic.event_handler.MSG_QUEUE.put"),
            patch("app.state.app_state.update_mode_signal_from_journal"),
            patch("logic.event_handler.high_g_warning.handle_journal_event"),
            patch("logic.event_handler.survival_rebuy_awareness.handle_journal_event"),
            patch("logic.event_handler.combat_awareness.handle_journal_event"),
            patch("logic.event_handler._log_sell_value_snapshot") as snapshot_mock,
            patch("logic.event_handler._apply_sell_value_domain_reset") as reset_mock,
        ):
            handler.handle_event(line, gui_ref=None)

        snapshot_mock.assert_called_once()
        reset_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
