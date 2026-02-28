from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import config
from logic import cache_store
from logic.tts import piper_tts


class _FakeTmpWav:
    def __init__(self, path: str) -> None:
        self.name = path

    def close(self) -> None:
        return None


class F60ReleaseHygieneSecurityRegressionsTests(unittest.TestCase):
    def test_piper_cleanup_log_uses_filename_only(self) -> None:
        selected = piper_tts.PiperPaths(
            bin_path="C:/fake/piper.exe",
            model_path="C:/fake/model.onnx",
            config_path="C:/fake/model.json",
            source="appdata",
        )
        leaked_path = "C:/Users/SecretUser/AppData/Local/Temp/renata-sensitive-voice.wav"

        with (
            patch("logic.tts.piper_tts._is_runtime_ready", return_value=True),
            patch("logic.tts.piper_tts.tempfile.NamedTemporaryFile", return_value=_FakeTmpWav(leaked_path)),
            patch("logic.tts.piper_tts.subprocess.run", return_value=subprocess.CompletedProcess(args=["piper"], returncode=1)),
            patch("logic.tts.piper_tts.os.remove", side_effect=PermissionError("denied")),
            patch("logic.tts.piper_tts.log_event_throttled") as throttled_log,
            patch("logic.tts.piper_tts.config.get", side_effect=lambda _key, default=None: default),
        ):
            ok = piper_tts.speak("test", paths=selected)

        self.assertFalse(ok)
        cleanup_calls = [c for c in throttled_log.call_args_list if c.args and c.args[0] == "piper_wav_cleanup"]
        self.assertEqual(len(cleanup_calls), 1)
        logged_path = str(cleanup_calls[0].kwargs.get("path") or "")
        self.assertEqual(logged_path, "renata-sensitive-voice.wav")
        self.assertNotIn("SecretUser", logged_path)
        self.assertNotIn("/", logged_path)
        self.assertNotIn("\\", logged_path)

    def test_cache_logs_do_not_expose_full_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_root = os.path.join(tmp_dir, "src")
            dst_root = os.path.join(tmp_dir, "dst")
            os.makedirs(src_root, exist_ok=True)
            os.makedirs(dst_root, exist_ok=True)
            src_file = os.path.join(src_root, "secret-market.json")
            with open(src_file, "w", encoding="utf-8") as f:
                f.write("{}")

            with (
                patch("logic.cache_store.shutil.move", side_effect=PermissionError("blocked")),
                patch("logic.cache_store.log_event_throttled") as throttled_log,
            ):
                moved = cache_store._merge_tree_no_overwrite(src_root, dst_root)

            self.assertEqual(moved, 0)
            move_calls = [c for c in throttled_log.call_args_list if c.args and c.args[0] == "cache.migrate.move_file"]
            self.assertEqual(len(move_calls), 1)
            self.assertEqual(str(move_calls[0].kwargs.get("src") or ""), "secret-market.json")
            self.assertEqual(str(move_calls[0].kwargs.get("dst") or ""), "secret-market.json")

            child_dir = os.path.join(src_root, "nested")
            os.makedirs(child_dir, exist_ok=True)
            with (
                patch("logic.cache_store.os.rmdir", side_effect=PermissionError("blocked")),
                patch("logic.cache_store.log_event_throttled") as throttled_log,
            ):
                cache_store._prune_empty_dirs(src_root)

            path_values = [str(c.kwargs.get("path") or "") for c in throttled_log.call_args_list if "path" in c.kwargs]
            self.assertTrue(path_values)
            for item in path_values:
                self.assertNotIn("/", item)
                self.assertNotIn("\\", item)

    def test_renata_user_home_dir_logs_mkdir_failure_without_full_path(self) -> None:
        leaked_path = "C:/Users/SecretUser/RenataAI"
        with (
            patch("config._renata_user_home_dir", return_value=leaked_path),
            patch("config.os.makedirs", side_effect=PermissionError("denied")),
            patch("config._log_config_warning") as warn_mock,
        ):
            out = config.renata_user_home_dir()

        self.assertEqual(out, leaked_path)
        warn_mock.assert_called_once()
        self.assertEqual(str(warn_mock.call_args.kwargs.get("directory") or ""), "RenataAI")

    def test_config_write_is_atomic_and_preserves_previous_file_on_dump_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = os.path.join(tmp_dir, "user_settings.json")
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump({"language": "pl"}, f)

            manager = config.ConfigManager(settings_path=settings_path)
            with patch("config.json.dump", side_effect=RuntimeError("dump failed")):
                with self.assertRaises(RuntimeError):
                    manager.save({"language": "en"})

            with open(settings_path, "r", encoding="utf-8") as f:
                persisted = json.load(f)
            self.assertEqual(str(persisted.get("language") or ""), "pl")

            leftovers = [name for name in os.listdir(tmp_dir) if name.startswith("user_settings_") and name.endswith(".tmp")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
