"""
F16.1 Regression tests: Exobio state continuity across restart (16.1 patch).

Root cause fixed:
  _apply_exobio_state_payload used to restore last_status_pos["ts"] from the
  persisted state.  After a restart (>120 s), that timestamp caused
  _canonical_body_for_key to reject the stale position as a body-name fallback,
  producing a different key than the one stored in the persisted sample count.
  Result: count never reached 3, completion callout was never emitted.

Fix:
  * ts is no longer saved/restored in last_status_pos.
  * _canonical_body_for_key treats ts==0.0 as "no freshness constraint" for
    body-name matching (restored from persisted state), while _arm_range_tracker
    still requires ts<=30 s for distance tracking.

Tests:
  a) new session -> scan exobio -> restart -> state identical, key stable
  b) several records -> restart -> none lost / none duplicated
  c) empty persisted state -> no crash, correct defaults
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import config
from app.state import app_state
from logic.context_state_contract import default_state_contract
from logic.events import exploration_bio_events as bio_events
from logic.events import navigation_events


def _fresh_contract(path: str) -> None:
    config.STATE_FILE = path
    config.save_state_contract(default_state_contract())
    bio_events.reset_bio_flags(persist=True)


def _collect_sample_messages(emit_mock) -> list[str]:
    return [
        str(call.args[0])
        for call in emit_mock.call_args_list
        if call.kwargs.get("message_id") == "MSG.EXOBIO_SAMPLE_LOGGED"
    ]


class F161ExobioRestartContinuityTests(unittest.TestCase):
    """
    (a) New session -> scan exobio (numeric body only) -> restart -> state identical.

    Verifies the key-stability fix: after restart with status pos restored at ts=0.0,
    _canonical_body_for_key must still return the persisted body name and the count
    must continue from where it left off.
    """

    def test_a_numeric_body_key_survives_restart(self) -> None:
        """
        KEY STABILITY across restart when ScanOrganic has only numeric BodyID.

        Bug (pre-fix): persisted ts caused _canonical_body_for_key to reject the
        restored body name, producing a DIFFERENT key after restart (e.g. "3"
        instead of "f161 system 3").  Count never reached 3 -> no completion.

        Expected with the fix:
        - The same key is used pre- and post-restart (body name from restored pos).
        - count is correctly incremented from 1 -> 2 -> 3 across the restart.
        - 3/3 emits the "Mamy wszystko" completion callout.

        Note: events without StarSystem set event_uncertain=True, so samples 1 and 2
        emit "Kolejna próbka" (uncertain wording is correct / by design for ambiguous
        events).  The critical assertion is that count reaches 3 and completion fires.
        """
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f161_restart_a.json")
            try:
                _fresh_contract(tmp_path)
                app_state.current_system = "F161 System"

                # Simulate a live status position (player is on body "F161 System 3").
                # Status pos has a FRESH ts -- as it would be during a live session.
                bio_events.EXOBIO_LAST_STATUS_POS.update(
                    {
                        "lat": 10.0,
                        "lon": -20.0,
                        "radius_m": 2500000.0,
                        "body": "f161 system 3",
                        "system": "f161 system",
                        "ts": time.time(),
                    }
                )

                # First scan: ScanOrganic with numeric BodyID only (no BodyName, no StarSystem).
                # _canonical_body_for_key should use the fresh status pos -> "f161 system 3".
                # event_uncertain=True (no StarSystem) -> "Kolejna próbka" (by design).
                event_numeric = {
                    "event": "ScanOrganic",
                    "BodyID": 3,
                    "Species_Localised": "Bacterium Aurasus",
                }
                expected_key = ("f161 system", "f161 system 3", "bacterium aurasus")

                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as mock_emit,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event_numeric, gui_ref=None)
                    msgs = _collect_sample_messages(mock_emit)
                    self.assertEqual(len(msgs), 1, "Expected exactly one sample message (scan 1)")
                    # Uncertain wording because StarSystem absent -- correct behavior.
                    self.assertIn("próbka", msgs[0])

                self.assertEqual(
                    bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0),
                    1,
                    "Key with body name must have count=1 after first scan",
                )

                # ---- SIMULATE RESTART: wipe runtime memory, reload from contract ----
                bio_events.reset_bio_flags()
                self.assertEqual(bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0), 0)

                load_stats = bio_events.load_exobio_state_from_contract(force=True)
                self.assertTrue(load_stats.get("loaded"), "State should be loadable after restart")
                self.assertEqual(
                    bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0),
                    1,
                    "After restart, count must still be 1 for the correct (named) key",
                )

                # After restart: status pos is restored WITHOUT ts (ts must be absent).
                pos = bio_events.EXOBIO_LAST_STATUS_POS
                self.assertEqual(pos.get("body", ""), "f161 system 3", "Body name must survive restart")
                self.assertNotIn("ts", pos, "ts must NOT be in restored status pos (fix)")

                # Second scan: same numeric-only event.
                # BUG (pre-fix): ts was stale -> body name rejected -> key="3" -> count=0+1=1.
                # FIX: ts==0.0 sentinel -> body name accepted -> key="f161 system 3" -> count=1+1=2.
                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as mock_emit,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event_numeric, gui_ref=None)
                    msgs = _collect_sample_messages(mock_emit)
                    self.assertEqual(len(msgs), 1, "Expected one sample message (scan 2)")
                    self.assertIn("próbka", msgs[0])

                self.assertEqual(
                    bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0),
                    2,
                    "After restart + second scan, count must be 2 (not 1 as in bug)",
                )

                # Third scan: must emit completion callout (BUG: was silent pre-fix).
                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as mock_emit,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(50000.0, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event_numeric, gui_ref=None)
                    msgs = _collect_sample_messages(mock_emit)
                    self.assertEqual(len(msgs), 1, "Expected completion message at 3/3")
                    self.assertIn(
                        "Mamy wszystko",
                        msgs[0],
                        "3/3 must emit completion callout (was silent pre-fix)",
                    )

                self.assertIn(expected_key, bio_events.EXOBIO_SAMPLE_COMPLETE, "Key must be in COMPLETE set")

            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    """
    (b) Several records -> restart -> none lost, none duplicated.

    Verifies that multiple in-progress species all survive a restart with correct
    counts, and that the same events replayed a second time do not double-increment.
    """

    def test_b_multiple_species_survive_restart_without_duplication(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f161_restart_b.json")
            try:
                _fresh_contract(tmp_path)

                species_events = [
                    {
                        "event": "ScanOrganic",
                        "StarSystem": "F161B System",
                        "BodyName": "F161B System 1 A",
                        "Species_Localised": "Aleoida Arcus",
                    },
                    {
                        "event": "ScanOrganic",
                        "StarSystem": "F161B System",
                        "BodyName": "F161B System 2 B",
                        "Species_Localised": "Bacterium Aurasus",
                    },
                    {
                        "event": "ScanOrganic",
                        "StarSystem": "F161B System",
                        "BodyName": "F161B System 3 C",
                        "Species_Localised": "Cactoida Cortexum",
                    },
                ]
                keys = [
                    ("f161b system", "f161b system 1 a", "aleoida arcus"),
                    ("f161b system", "f161b system 2 b", "bacterium aurasus"),
                    ("f161b system", "f161b system 3 c", "cactoida cortexum"),
                ]

                # Scan each species twice.
                with (
                    patch("logic.events.exploration_bio_events.emit_insight"),
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    for ev in species_events:
                        bio_events.handle_exobio_progress(ev, gui_ref=None)
                    for ev in species_events:
                        bio_events.handle_exobio_progress(ev, gui_ref=None)

                for key in keys:
                    self.assertEqual(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0), 2, f"Expected 2 for {key}")

                # ---- SIMULATE RESTART ----
                bio_events.reset_bio_flags()
                load_stats = bio_events.load_exobio_state_from_contract(force=True)
                self.assertTrue(load_stats.get("loaded"))

                # All three species must survive with count=2.
                for key in keys:
                    self.assertEqual(
                        bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0),
                        2,
                        f"Key {key} lost count after restart",
                    )

                # Replaying the same events must NOT double-count (key already at 2 -> goes to 3
                # on first replay, not beyond).
                with (
                    patch("logic.events.exploration_bio_events.emit_insight"),
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    for ev in species_events:
                        bio_events.handle_exobio_progress(ev, gui_ref=None)

                for key in keys:
                    count = bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)
                    self.assertLessEqual(count, 3, f"Count must not exceed 3 for {key}")
                    self.assertGreaterEqual(count, 2, f"Count must not drop below 2 for {key}")

            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    """
    (c) Start with empty persisted state -> no crash, correct defaults.

    Verifies that loading from a state file that has no exobio payload does not
    raise and leaves all globals at their zero-defaults.
    """

    def test_c_empty_persisted_state_no_crash_correct_defaults(self) -> None:
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f161_restart_c.json")
            try:
                # Write a contract with no exobio key in anti_spam_state.
                _fresh_contract(tmp_path)

                # Load should succeed without crash and report loaded=False.
                bio_events.reset_bio_flags()
                result = bio_events.load_exobio_state_from_contract(force=True)
                self.assertFalse(result.get("loaded"), "Empty state must not report loaded=True")
                self.assertEqual(len(bio_events.EXOBIO_SAMPLE_COUNT), 0)
                self.assertEqual(len(bio_events.EXOBIO_SAMPLE_COMPLETE), 0)
                self.assertEqual(len(bio_events.EXOBIO_RANGE_TRACKERS), 0)

                # A scan event after empty-state load must work correctly (no crash,
                # first sample emitted as "Pierwsza próbka").
                event = {
                    "event": "ScanOrganic",
                    "StarSystem": "F161C System",
                    "BodyName": "F161C System 1 A",
                    "Species_Localised": "Aleoida Arcus",
                }
                key = ("f161c system", "f161c system 1 a", "aleoida arcus")

                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as mock_emit,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event, gui_ref=None)
                    msgs = _collect_sample_messages(mock_emit)
                    self.assertEqual(len(msgs), 1)
                    self.assertIn("Pierwsza próbka", msgs[0])

                self.assertEqual(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0), 1)

            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_c_bootstrap_with_empty_state_no_crash(self) -> None:
        """bootstrap_exobio_state_from_journal_lines with empty state and empty lines."""
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f161_bootstrap_empty.json")
            try:
                _fresh_contract(tmp_path)
                bio_events.reset_bio_flags()
                result = bio_events.bootstrap_exobio_state_from_journal_lines([], max_lines=100)
                self.assertIn("source", result)
                self.assertEqual(len(bio_events.EXOBIO_SAMPLE_COUNT), 0)
            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_d_bootstrap_location_reset_does_not_wipe_recovered_exobio_state(self) -> None:
        """
        Regression (BUGS_FIX 16.1):
        Bootstrap recovers exobio state first, then replays Location/FSDJump which calls
        reset_fss_progress(). That reset used to wipe exobio state via reset_bio_flags().
        """
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()
        old_bootstrap = bool(getattr(app_state, "bootstrap_replay", False))

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f161_bootstrap_location_preserve.json")
            try:
                _fresh_contract(tmp_path)
                app_state.current_system = "F161D System"

                # Build persisted exobio state: one sample already taken.
                with patch(
                    "logic.events.exploration_bio_events._estimate_collected_species_value",
                    return_value=(None, False),
                ):
                    bio_events.handle_exobio_progress(
                        {
                            "event": "ScanOrganic",
                            "StarSystem": "F161D System",
                            "BodyName": "F161D System 1 A",
                            "Species_Localised": "Aleoida Arcus",
                        },
                        gui_ref=None,
                    )
                expected_key = ("f161d system", "f161d system 1 a", "aleoida arcus")
                self.assertEqual(bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0), 1)

                # Simulate restart runtime memory wipe, then bootstrap recovery from contract.
                bio_events.reset_bio_flags()
                load_stats = bio_events.load_exobio_state_from_contract(force=True)
                self.assertTrue(load_stats.get("loaded"))
                self.assertEqual(bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0), 1)

                # Bootstrap replay of Location must NOT wipe recovered exobio state.
                app_state.bootstrap_replay = True
                navigation_events.handle_location_fsdjump_carrier(
                    {"event": "Location", "StarSystem": "F161D System"},
                    gui_ref=None,
                )
                self.assertEqual(
                    bio_events.EXOBIO_SAMPLE_COUNT.get(expected_key, 0),
                    1,
                    "bootstrap Location reset must preserve recovered exobio sample count",
                )

            finally:
                app_state.bootstrap_replay = old_bootstrap
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)

    def test_e_uncertain_sequence_key_survives_bootstrap_and_does_not_block_callouts(self) -> None:
        """
        Regression coverage for BUGS_FINDE suspicion:
        EXOBIO_RECOVERY_UNCERTAIN_KEYS restored from persisted state must not block
        2/3 or 3/3 exobio callouts after restart.
        """
        old_state_file = config.STATE_FILE
        old_contract = config.get_state_contract()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "f161_uncertain_restart.json")
            try:
                _fresh_contract(tmp_path)
                app_state.current_system = "F161E System"

                # First sample without StarSystem -> event_uncertain=True by design.
                event_numeric_uncertain = {
                    "event": "ScanOrganic",
                    "BodyID": 7,
                    "Species_Localised": "Aleoida Arcus",
                }
                key = ("f161e system", "7", "aleoida arcus")

                with (
                    patch("logic.events.exploration_bio_events.emit_insight"),
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event_numeric_uncertain, gui_ref=None)

                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)
                self.assertIn(
                    key,
                    bio_events.EXOBIO_RECOVERY_UNCERTAIN_KEYS,
                    "Uncertain sequence key should be tracked before restart",
                )

                # Simulate restart and bootstrap from persisted state.
                bio_events.reset_bio_flags()
                stats = bio_events.bootstrap_exobio_state_from_journal_lines([], max_lines=100)
                self.assertEqual(str(stats.get("source", "")), "state")
                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 1)
                self.assertIn(
                    key,
                    bio_events.EXOBIO_RECOVERY_UNCERTAIN_KEYS,
                    "Uncertain sequence key should be restored from persisted state",
                )

                # Second sample after restart: callout must still fire (neutral wording is expected).
                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(None, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event_numeric_uncertain, gui_ref=None)
                    msgs = _collect_sample_messages(emit_mock)
                    self.assertEqual(len(msgs), 1, "2/3 callout must not be blocked after restart")
                    self.assertIn("Kolejna próbka", msgs[0])

                self.assertEqual(int(bio_events.EXOBIO_SAMPLE_COUNT.get(key, 0)), 2)

                # Third sample after restart: completion callout must also fire.
                with (
                    patch("logic.events.exploration_bio_events.emit_insight") as emit_mock,
                    patch(
                        "logic.events.exploration_bio_events._estimate_collected_species_value",
                        return_value=(12345.0, False),
                    ),
                ):
                    bio_events.handle_exobio_progress(event_numeric_uncertain, gui_ref=None)
                    msgs = _collect_sample_messages(emit_mock)
                    self.assertEqual(len(msgs), 1, "3/3 completion callout must not be blocked")
                    self.assertIn("Mamy wszystko", msgs[0])

                self.assertIn(key, bio_events.EXOBIO_SAMPLE_COMPLETE)
                self.assertNotIn(
                    key,
                    bio_events.EXOBIO_RECOVERY_UNCERTAIN_KEYS,
                    "Completion should clear uncertainty tracking for the key",
                )

            finally:
                bio_events.reset_bio_flags()
                config.STATE_FILE = old_state_file
                config.save_state_contract(old_contract)


if __name__ == "__main__":
    unittest.unittest.main()
