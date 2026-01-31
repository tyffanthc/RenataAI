from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional

import config


def _resolve_path(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    path_value = str(path_value).strip()
    if not path_value:
        return None
    if os.path.isabs(path_value):
        return path_value if os.path.isfile(path_value) else None
    rel = os.path.join(config.BASE_DIR, path_value)
    if os.path.isfile(rel):
        return rel
    return None


def _resolve_piper_bin() -> Optional[str]:
    candidate = _resolve_path(config.get("tts.piper_bin"))
    if candidate:
        return candidate
    for name in ("piper.exe", "piper"):
        found = shutil.which(name)
        if found:
            return found
    fallback = os.path.join(config.BASE_DIR, "tools", "piper", "piper.exe")
    if os.path.isfile(fallback):
        return fallback
    return None


def _resolve_model_path() -> Optional[str]:
    model = _resolve_path(config.get("tts.piper_model_path"))
    if model:
        return model
    return None


def _resolve_config_path() -> Optional[str]:
    return _resolve_path(config.get("tts.piper_config_path"))


def speak(text: str) -> bool:
    if os.name != "nt":
        return False

    bin_path = _resolve_piper_bin()
    model_path = _resolve_model_path()
    if not bin_path or not model_path:
        return False

    config_path = _resolve_config_path()

    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()
    wav_path = tmp_wav.name

    cmd = [bin_path, "-m", model_path, "-f", wav_path]
    if config_path:
        cmd.extend(["-c", config_path])
    try:
        length_scale = float(config.get("tts.piper_length_scale", 1.0))
        if length_scale > 0:
            cmd.extend(["--length_scale", str(length_scale)])
    except Exception:
        pass
    try:
        sentence_silence = float(config.get("tts.piper_sentence_silence", 0.2))
        if sentence_silence >= 0:
            cmd.extend(["--sentence_silence", str(sentence_silence)])
    except Exception:
        pass

    try:
        result = subprocess.run(
            cmd,
            input=text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not os.path.isfile(wav_path):
            return False

        import winsound

        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        return True
    except Exception:
        return False
    finally:
        try:
            os.remove(wav_path)
        except Exception:
            pass
