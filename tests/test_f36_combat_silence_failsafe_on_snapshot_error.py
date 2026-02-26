from __future__ import annotations

import unittest
from unittest.mock import patch

from logic import insight_dispatcher


class F36CombatSilenceFailsafeOnSnapshotErrorTests(unittest.TestCase):
    def test_snapshot_read_error_enables_combat_silence_failsafe(self) -> None:
        with patch("app.state.app_state.get_mode_state_snapshot", side_effect=RuntimeError("snapshot failed")):
            active = insight_dispatcher._is_combat_silence_active({})
        self.assertTrue(active, "On snapshot error dispatcher should fail safe and keep silence active.")


if __name__ == "__main__":
    unittest.main()

