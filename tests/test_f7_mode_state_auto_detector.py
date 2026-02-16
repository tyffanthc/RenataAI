import queue
import time
import unittest

import config
from app.state import app_state
from logic.utils import MSG_QUEUE


def _drain_queue() -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    try:
        while True:
            item = MSG_QUEUE.get_nowait()
            if isinstance(item, tuple) and len(item) == 2:
                items.append((item[0], item[1]))
    except queue.Empty:
        return items


class ModeStateAutoDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        _drain_queue()
        self._saved_snapshot = app_state.get_mode_state_snapshot()
        self._saved_is_docked = bool(getattr(app_state, "is_docked", False))
        self._saved_state_keys = {
            "mode_id": config.STATE.get("mode_id"),
            "mode_source": config.STATE.get("mode_source"),
            "mode_confidence": config.STATE.get("mode_confidence"),
            "mode_since": config.STATE.get("mode_since"),
            "mode_ttl": config.STATE.get("mode_ttl"),
            "is_docked": config.STATE.get("is_docked"),
        }
        self._saved_signals = {}
        for name in (
            "_mode_signal_docked",
            "_mode_signal_combat_active",
            "_mode_signal_combat_last_ts",
            "_mode_signal_hardpoints_since",
            "_mode_signal_exploration_active",
            "_mode_signal_exploration_last_ts",
            "_mode_signal_mining_active",
            "_mode_signal_mining_last_ts",
            "_mode_signal_mining_loadout",
            "_mode_last_emit_signature",
        ):
            self._saved_signals[name] = getattr(app_state, name)

        with app_state.lock:
            app_state.mode_id = "NORMAL"
            app_state.mode_source = "AUTO"
            app_state.mode_confidence = 0.60
            app_state.mode_since = time.time()
            app_state.mode_ttl = None
            app_state.is_docked = False
            app_state._mode_signal_docked = False
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = 0.0
            app_state._mode_signal_hardpoints_since = None
            app_state._mode_signal_exploration_active = False
            app_state._mode_signal_exploration_last_ts = 0.0
            app_state._mode_signal_mining_active = False
            app_state._mode_signal_mining_last_ts = 0.0
            app_state._mode_signal_mining_loadout = False
            app_state._mode_last_emit_signature = ""
            app_state._persist_mode_state_locked()
        app_state.publish_mode_state(force=True)
        _drain_queue()

    def tearDown(self) -> None:
        with app_state.lock:
            app_state.mode_id = str(self._saved_snapshot.get("mode_id") or "NORMAL")
            app_state.mode_source = str(self._saved_snapshot.get("mode_source") or "AUTO")
            app_state.mode_confidence = float(self._saved_snapshot.get("mode_confidence") or 0.60)
            app_state.mode_since = float(self._saved_snapshot.get("mode_since") or time.time())
            ttl = self._saved_snapshot.get("mode_ttl")
            app_state.mode_ttl = float(ttl) if ttl is not None else None
            app_state.is_docked = self._saved_is_docked
            for key, value in self._saved_signals.items():
                setattr(app_state, key, value)
            app_state._persist_mode_state_locked()

        for key, value in self._saved_state_keys.items():
            if value is None:
                config.STATE.pop(key, None)
            else:
                config.STATE[key] = value
        app_state.publish_mode_state(force=True)
        _drain_queue()

    def test_docked_and_undocked_auto_switch(self) -> None:
        app_state.update_mode_signal_from_status({"Docked": True}, source="test.mode.docked")
        snap_docked = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_docked.get("mode_id"), "DOCKED")
        self.assertEqual(snap_docked.get("mode_source"), "AUTO")

        app_state.update_mode_signal_from_journal({"event": "Undocked"}, source="test.mode.undocked")
        snap_undocked = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_undocked.get("mode_id"), "NORMAL")

    def test_exploration_detected_from_fss_focus(self) -> None:
        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 9},
            source="test.mode.fss",
        )
        snap = app_state.get_mode_state_snapshot()
        self.assertEqual(snap.get("mode_id"), "EXPLORATION")
        self.assertGreaterEqual(float(snap.get("mode_confidence") or 0.0), 0.8)

    def test_combat_priority_over_docked(self) -> None:
        app_state.update_mode_signal_from_status({"Docked": True}, source="test.mode.docked")
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"risk_status": "RISK_HIGH", "in_combat": True},
            source="test.mode.combat",
        )
        snap = app_state.get_mode_state_snapshot()
        self.assertEqual(snap.get("mode_id"), "COMBAT")
        self.assertEqual(snap.get("mode_ttl"), 45.0)

    def test_mining_detected_from_loadout_and_ring(self) -> None:
        app_state.update_mode_signal_from_journal(
            {
                "event": "Loadout",
                "Modules": [
                    {"Slot": "HugeHardpoint1", "Item": "hpt_mininglaser_fixed_small"},
                    {"Slot": "UtilityMount1", "Item": "hpt_shieldbooster_size0_class1"},
                ],
            },
            source="test.mode.loadout",
        )
        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 0, "InRing": True},
            source="test.mode.ring",
        )
        snap = app_state.get_mode_state_snapshot()
        self.assertEqual(snap.get("mode_id"), "MINING")

    def test_priority_exploration_over_mining(self) -> None:
        app_state.update_mode_signal_from_journal(
            {
                "event": "Loadout",
                "Modules": [{"Slot": "Hardpoint1", "Item": "hpt_mininglaser_fixed_small"}],
            },
            source="test.mode.loadout",
        )
        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 0, "InRing": True},
            source="test.mode.ring",
        )
        snap_mining = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_mining.get("mode_id"), "MINING")

        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 9, "InRing": True},
            source="test.mode.fss_priority",
        )
        snap_exploration = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_exploration.get("mode_id"), "EXPLORATION")

        emitted = [item for item in _drain_queue() if item[0] == "mode_state"]
        self.assertTrue(emitted)


if __name__ == "__main__":
    unittest.main()
