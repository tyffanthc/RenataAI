from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import config


@dataclass(frozen=True)
class PiperPaths:
    bin_path: str
    model_path: str
    config_path: Optional[str]
    source: str  # "settings" | "appdata"


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


def _has_user_settings() -> bool:
    for key in ("tts.piper_bin", "tts.piper_model_path", "tts.piper_config_path"):
        value = str(config.get(key, "")).strip()
        if value:
            return True
    return False


def _resolve_appdata_voicepack() -> Optional[PiperPaths]:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    base = os.path.join(appdata, "RenataAI", "voice", "piper")
    bin_path = os.path.join(base, "piper.exe")
    models_dir = os.path.join(base, "models")
    model_path = os.path.join(models_dir, "pl_PL-gosia-medium.onnx")
    config_path = os.path.join(models_dir, "pl_PL-gosia-medium.json")
    if os.path.isfile(bin_path) and os.path.isfile(model_path) and os.path.isfile(config_path):
        return PiperPaths(bin_path=bin_path, model_path=model_path, config_path=config_path, source="appdata")
    if os.path.isfile(bin_path) and os.path.isdir(models_dir):
        try:
            for name in os.listdir(models_dir):
                if not name.lower().endswith(".onnx"):
                    continue
                candidate = os.path.join(models_dir, name)
                candidate_cfg = os.path.splitext(candidate)[0] + ".json"
                if os.path.isfile(candidate) and os.path.isfile(candidate_cfg):
                    return PiperPaths(
                        bin_path=bin_path,
                        model_path=candidate,
                        config_path=candidate_cfg,
                        source="appdata",
                    )
        except Exception:
            return None
    return None


def select_piper_paths(*, use_appdata: bool) -> Optional[PiperPaths]:
    if _has_user_settings():
        bin_path = _resolve_piper_bin()
        model_path = _resolve_model_path()
        if bin_path and model_path:
            return PiperPaths(
                bin_path=bin_path,
                model_path=model_path,
                config_path=_resolve_config_path(),
                source="settings",
            )
        return None
    if use_appdata:
        return _resolve_appdata_voicepack()
    return None


def speak(text: str, *, paths: Optional[PiperPaths] = None) -> bool:
    if os.name != "nt":
        return False

    selected = paths or select_piper_paths(use_appdata=False)
    if not selected:
        return False

    bin_path = selected.bin_path
    model_path = selected.model_path
    config_path = selected.config_path

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
