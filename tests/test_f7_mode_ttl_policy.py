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


class ModeTtlPolicyTests(unittest.TestCase):
    _TTL_KEYS = (
        "mode.ttl.combat_sec",
        "mode.ttl.exploration_sec",
        "mode.ttl.mining_sec",
    )

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

        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self._saved_ttl_settings = {}
        if isinstance(settings, dict):
            for key in self._TTL_KEYS:
                self._saved_ttl_settings[key] = settings.get(key)
            settings["mode.ttl.combat_sec"] = 45.0
            settings["mode.ttl.exploration_sec"] = 120.0
            settings["mode.ttl.mining_sec"] = 90.0

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

        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        if isinstance(settings, dict):
            for key, value in self._saved_ttl_settings.items():
                if value is None:
                    settings.pop(key, None)
                else:
                    settings[key] = value

        app_state.publish_mode_state(force=True)
        _drain_queue()

    def test_combat_ttl_hold_and_expire(self) -> None:
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"in_combat": True, "risk_status": "RISK_HIGH"},
            source="test.ttl.combat.signal",
        )
        snap_enter = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_enter.get("mode_id"), "COMBAT")
        self.assertEqual(snap_enter.get("mode_ttl"), 45.0)

        with app_state.lock:
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = time.time() - 30.0
        app_state.refresh_mode_state(source="test.ttl.combat.hold")
        snap_hold = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_hold.get("mode_id"), "COMBAT")

        with app_state.lock:
            app_state._mode_signal_combat_last_ts = time.time() - 60.0
        app_state.refresh_mode_state(source="test.ttl.combat.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_expired.get("mode_id"), "NORMAL")
        self.assertIsNone(snap_expired.get("mode_ttl"))

    def test_exploration_ttl_resets_on_new_signal(self) -> None:
        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 9},
            source="test.ttl.exploration.focus",
        )
        snap_enter = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_enter.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_enter.get("mode_ttl"), 120.0)

        with app_state.lock:
            app_state._mode_signal_exploration_active = False
            app_state._mode_signal_exploration_last_ts = time.time() - 110.0
            old_ts = app_state._mode_signal_exploration_last_ts
        app_state.refresh_mode_state(source="test.ttl.exploration.hold")
        snap_hold = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_hold.get("mode_id"), "EXPLORATION")

        app_state.update_mode_signal_from_runtime(
            "exploration_summary",
            {"headline": "ttl reset"},
            source="test.ttl.exploration.runtime",
        )
        with app_state.lock:
            refreshed_ts = app_state._mode_signal_exploration_last_ts
            app_state._mode_signal_exploration_active = False
            app_state._mode_signal_exploration_last_ts = time.time() - 130.0
        self.assertGreater(refreshed_ts, old_ts)

        app_state.refresh_mode_state(source="test.ttl.exploration.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_expired.get("mode_id"), "NORMAL")

    def test_mining_ttl_hold_and_expire(self) -> None:
        app_state.update_mode_signal_from_journal(
            {
                "event": "Loadout",
                "Modules": [{"Slot": "Hardpoint1", "Item": "hpt_mininglaser_fixed_small"}],
            },
            source="test.ttl.mining.loadout",
        )
        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 0, "InRing": True},
            source="test.ttl.mining.ring",
        )
        snap_enter = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_enter.get("mode_id"), "MINING")
        self.assertEqual(snap_enter.get("mode_ttl"), 90.0)

        with app_state.lock:
            app_state._mode_signal_mining_active = False
            app_state._mode_signal_mining_last_ts = time.time() - 80.0
        app_state.refresh_mode_state(source="test.ttl.mining.hold")
        snap_hold = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_hold.get("mode_id"), "MINING")

        with app_state.lock:
            app_state._mode_signal_mining_last_ts = time.time() - 100.0
        app_state.refresh_mode_state(source="test.ttl.mining.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_expired.get("mode_id"), "NORMAL")

    def test_ttl_config_override_is_applied(self) -> None:
        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self.assertIsInstance(settings, dict)
        settings = settings or {}
        settings["mode.ttl.exploration_sec"] = 10.0

        app_state.update_mode_signal_from_status(
            {"Docked": False, "GuiFocus": 9},
            source="test.ttl.override.focus",
        )
        snap_enter = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_enter.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_enter.get("mode_ttl"), 10.0)

        with app_state.lock:
            app_state._mode_signal_exploration_active = False
            app_state._mode_signal_exploration_last_ts = time.time() - 12.0
        app_state.refresh_mode_state(source="test.ttl.override.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_expired.get("mode_id"), "NORMAL")


if __name__ == "__main__":
    unittest.main()
