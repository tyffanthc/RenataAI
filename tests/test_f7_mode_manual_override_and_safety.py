import queue
import time
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.insight_dispatcher import Insight, should_speak
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


class ModeManualOverrideAndSafetyTests(unittest.TestCase):
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

        self._saved_mode_overlay = getattr(app_state, "mode_overlay", None)
        self._saved_mode_combat_silence = bool(getattr(app_state, "mode_combat_silence", False))

        with app_state.lock:
            app_state.mode_id = "NORMAL"
            app_state.mode_source = "AUTO"
            app_state.mode_confidence = 0.60
            app_state.mode_since = time.time()
            app_state.mode_ttl = None
            app_state.mode_overlay = None
            app_state.mode_combat_silence = False
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
            app_state.mode_overlay = (
                str(self._saved_snapshot.get("mode_overlay"))
                if self._saved_snapshot.get("mode_overlay")
                else self._saved_mode_overlay
            )
            app_state.mode_combat_silence = bool(
                self._saved_snapshot.get("mode_combat_silence", self._saved_mode_combat_silence)
            )
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

    def test_manual_mode_blocks_auto_switch(self) -> None:
        snap_manual = app_state.set_mode_manual("EXPLORATION", source="test.mode.manual.exploration")
        self.assertEqual(snap_manual.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_manual.get("mode_source"), "MANUAL")

        app_state.update_mode_signal_from_status({"Docked": True}, source="test.mode.manual.docked")
        snap_after = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_after.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_after.get("mode_source"), "MANUAL")
        self.assertIsNone(snap_after.get("mode_overlay"))
        self.assertFalse(bool(snap_after.get("mode_combat_silence")))

    def test_manual_mode_uses_combat_safety_overlay_without_mode_change(self) -> None:
        app_state.set_mode_manual("EXPLORATION", source="test.mode.manual.exploration")
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"risk_status": "RISK_HIGH", "in_combat": True},
            source="test.mode.manual.combat",
        )
        snap_combat = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_combat.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_combat.get("mode_source"), "MANUAL")
        self.assertEqual(snap_combat.get("mode_overlay"), "COMBAT")
        self.assertTrue(bool(snap_combat.get("mode_combat_silence")))

        with app_state.lock:
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = time.time() - 60.0
        app_state.refresh_mode_state(source="test.mode.manual.combat.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_expired.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_expired.get("mode_source"), "MANUAL")
        self.assertIsNone(snap_expired.get("mode_overlay"))
        self.assertFalse(bool(snap_expired.get("mode_combat_silence")))

    def test_set_mode_auto_releases_manual_lock(self) -> None:
        app_state.set_mode_manual("EXPLORATION", source="test.mode.manual.exploration")
        snap_auto = app_state.set_mode_auto(source="test.mode.auto.release")
        self.assertEqual(snap_auto.get("mode_source"), "AUTO")

    def test_safety_overlay_enforces_combat_silence_for_dispatcher(self) -> None:
        app_state.set_mode_manual("EXPLORATION", source="test.mode.manual.exploration")
        insight = Insight(
            text="mode safety test",
            message_id="MSG.TEST_MODE_SAFETY",
            source="test_mode",
            context={
                "system": "TEST_MODE_SAFETY",
                "risk_status": "RISK_LOW",
                "var_status": "VAR_LOW",
                "trust_status": "TRUST_HIGH",
                "confidence": "high",
            },
            priority="P2_NORMAL",
            cooldown_scope="message",
            cooldown_seconds=0.0,
        )

        with patch("logic.insight_dispatcher._notify._should_speak_tts", return_value=True):
            self.assertTrue(should_speak(insight))
            app_state.update_mode_signal_from_runtime(
                "combat_awareness",
                {"risk_status": "RISK_HIGH", "in_combat": True},
                source="test.mode.manual.safety_dispatcher",
            )
            self.assertFalse(should_speak(insight))


if __name__ == "__main__":
    unittest.main()
