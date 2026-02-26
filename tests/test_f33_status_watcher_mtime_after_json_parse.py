from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.status_watchers import BaseWatcher


class F33StatusWatcherMtimeAfterJsonParseTests(unittest.TestCase):
    def test_transient_json_decode_error_does_not_mark_mtime_as_processed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "Status.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"ok": true}')

            watcher = BaseWatcher(
                path=path,
                handler=object(),
                gui_ref=None,
                app_state=None,
                config=None,
                poll_interval=0.0,
                label="TEST",
            )

            decode_err = json.JSONDecodeError("transient write", "", 0)
            with patch(
                "app.status_watchers.json.load",
                side_effect=[decode_err, {"ok": True}],
            ) as load_mock:
                first = watcher._load_json_safely()
                second = watcher._load_json_safely()

            self.assertIsNone(first, "First read should fail on transient JSON decode error.")
            self.assertEqual(second, {"ok": True}, "Second read with same mtime should retry and succeed.")
            self.assertEqual(load_mock.call_count, 2, "Watcher should retry parse for unchanged mtime after transient error.")


if __name__ == "__main__":
    unittest.main()

