from __future__ import annotations

import os
import queue
import tempfile
import unittest
from unittest.mock import patch

from app.main_loop import MainLoop
from logic.utils import MSG_QUEUE


class F28ExplorationValueRecoveryWindowAndDiagnosticsTests(unittest.TestCase):
    def _drain_queue(self) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        while True:
            try:
                out.append(MSG_QUEUE.get_nowait())
            except queue.Empty:
                break
        return out

    def setUp(self) -> None:
        self._drain_queue()

    def tearDown(self) -> None:
        self._drain_queue()

    def test_bootstrap_value_recovery_emits_short_diagnostic_log_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Journal.test.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"timestamp":"2026-02-25T20:00:00Z","event":"Location","StarSystem":"F28_BOOTSTRAP_SYS"}\n')
                f.write('{"timestamp":"2026-02-25T20:00:01Z","event":"Scan","StarSystem":"F28_BOOTSTRAP_SYS","BodyName":"F28_BOOTSTRAP_SYS A","BodyType":"Star","StarType":"K","WasDiscovered":false}\n')
                f.write('{"timestamp":"2026-02-25T20:00:02Z","event":"SAAScanComplete","StarSystem":"F28_BOOTSTRAP_SYS","BodyName":"F28_BOOTSTRAP_SYS B"}\n')

            loop = MainLoop(gui_ref=None, log_dir=tmp)
            with patch("app.main_loop.powiedz") as say_mock:
                loop._bootstrap_state(path, max_lines=50)

            queue_items = self._drain_queue()
            logs = [str(payload) for kind, payload in queue_items if kind == "log"]
            self.assertTrue(any("[BOOTSTRAP] Value recovery:" in line for line in logs))
            line = next(line for line in logs if "[BOOTSTRAP] Value recovery:" in line)
            self.assertIn("Scan counted:", line)
            self.assertIn("DSS upgrade applied:", line)
            self.assertIn("DSS skipped (missing prior Scan):", line)
            # bootstrap still performs startup voice/log flow elsewhere; this test only checks diagnostics line exists.
            self.assertTrue(say_mock.called)


if __name__ == "__main__":
    unittest.main()

