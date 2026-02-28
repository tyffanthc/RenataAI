from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional

import config
from logic.utils.renata_log import log_event_throttled

_RUNTIME_FILES = (
    "piper_phonemize.dll",
    "espeak-ng.dll",
    "onnxruntime.dll",
    "onnxruntime_providers_shared.dll",
)
_RUNTIME_DIRS = ("espeak-ng-data",)
_PIPER_SUBPROCESS_TIMEOUT_SEC = 15.0
_PIPER_WINSOUND_PLAYBACK_TIMEOUT_SEC = 45.0
_WINSOUND_PLAYBACK_GUARD_LOCK = threading.Lock()
_WINSOUND_HUNG_WORKER: Optional[threading.Thread] = None


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


def _is_runtime_ready(bin_path: Optional[str]) -> bool:
    if not bin_path or not os.path.isfile(bin_path):
        return False
    base = os.path.dirname(bin_path)
    for filename in _RUNTIME_FILES:
        if not os.path.isfile(os.path.join(base, filename)):
            return False
    for dirname in _RUNTIME_DIRS:
        if not os.path.isdir(os.path.join(base, dirname)):
            return False
    return True


def _resolve_model_path() -> Optional[str]:
    model = _resolve_path(config.get("tts.piper_model_path"))
    if model:
        return model
    return None


def _resolve_config_path() -> Optional[str]:
    return _resolve_path(config.get("tts.piper_config_path"))


def _has_valid_user_paths() -> bool:
    bin_path = _resolve_piper_bin()
    model_path = _resolve_model_path()
    config_path = _resolve_config_path()
    return bool(bin_path and model_path and config_path and _is_runtime_ready(bin_path))


def _resolve_appdata_voicepack() -> Optional[PiperPaths]:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    base = os.path.join(appdata, "RenataAI", "voice", "piper")
    bin_path = os.path.join(base, "piper.exe")
    models_dir = os.path.join(base, "models")
    model_path = os.path.join(models_dir, "pl_PL-gosia-medium.onnx")
    config_path = os.path.join(models_dir, "pl_PL-gosia-medium.json")
    if (
        _is_runtime_ready(bin_path)
        and os.path.isfile(model_path)
        and os.path.isfile(config_path)
    ):
        return PiperPaths(bin_path=bin_path, model_path=model_path, config_path=config_path, source="appdata")
    if _is_runtime_ready(bin_path) and os.path.isdir(models_dir):
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
            log_event_throttled(
                "piper_appdata_models_scan",
                60.0,
                "WARN",
                "piper: appdata models scan failed",
                base=os.path.basename(base),
            )
            return None
    return None


def select_piper_paths(*, use_appdata: bool) -> Optional[PiperPaths]:
    if _has_valid_user_paths():
        return PiperPaths(
            bin_path=_resolve_piper_bin(),
            model_path=_resolve_model_path(),
            config_path=_resolve_config_path(),
            source="settings",
        )
    if use_appdata:
        return _resolve_appdata_voicepack()
    return None


def _play_wav_with_timeout(wav_path: str, *, timeout_sec: float) -> bool:
    import winsound
    global _WINSOUND_HUNG_WORKER

    try:
        timeout = float(timeout_sec)
    except Exception:
        timeout = _PIPER_WINSOUND_PLAYBACK_TIMEOUT_SEC

    if timeout <= 0:
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        return True

    with _WINSOUND_PLAYBACK_GUARD_LOCK:
        hung = _WINSOUND_HUNG_WORKER
        if hung is not None and hung.is_alive():
            log_event_throttled(
                "piper_winsound_playback_still_hung",
                15.0,
                "WARN",
                "piper: skipping playback while previous winsound worker is still hung",
            )
            return False
        _WINSOUND_HUNG_WORKER = None

    playback_error: list[Exception] = []

    def _runner() -> None:
        try:
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        except Exception as exc:
            playback_error.append(exc)

    worker = threading.Thread(target=_runner, name="RenataPiperPlaySound", daemon=True)
    worker.start()
    worker.join(timeout=timeout)

    if worker.is_alive():
        with _WINSOUND_PLAYBACK_GUARD_LOCK:
            _WINSOUND_HUNG_WORKER = worker
        try:
            winsound.PlaySound(None, getattr(winsound, "SND_PURGE", 0))
        except Exception:
            pass
        log_event_throttled(
            "piper_winsound_playback_timeout",
            15.0,
            "WARN",
            "piper: winsound playback timeout",
            timeout_sec=timeout,
        )
        return False

    if playback_error:
        raise playback_error[0]
    with _WINSOUND_PLAYBACK_GUARD_LOCK:
        if _WINSOUND_HUNG_WORKER is worker:
            _WINSOUND_HUNG_WORKER = None
    return True


def speak(text: str, *, paths: Optional[PiperPaths] = None) -> bool:
    if os.name != "nt":
        return False

    selected = paths or select_piper_paths(use_appdata=False)
    if not selected:
        return False

    bin_path = selected.bin_path
    model_path = selected.model_path
    config_path = selected.config_path
    if not _is_runtime_ready(bin_path):
        return False

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
        log_event_throttled(
            "piper_length_scale_config",
            60.0,
            "WARN",
            "piper: invalid tts.piper_length_scale; using default",
            value=config.get("tts.piper_length_scale", None),
        )
    try:
        sentence_silence = float(config.get("tts.piper_sentence_silence", 0.2))
        if sentence_silence >= 0:
            cmd.extend(["--sentence_silence", str(sentence_silence)])
    except Exception:
        log_event_throttled(
            "piper_sentence_silence_config",
            60.0,
            "WARN",
            "piper: invalid tts.piper_sentence_silence; using default",
            value=config.get("tts.piper_sentence_silence", None),
        )

    try:
        startupinfo = None
        creationflags = 0
        # Keep Piper fully in background on Windows to avoid focus-steal/console popups.
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        result = subprocess.run(
            cmd,
            input=text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            timeout=_PIPER_SUBPROCESS_TIMEOUT_SEC,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        if result.returncode != 0 or not os.path.isfile(wav_path):
            return False

        if not _play_wav_with_timeout(wav_path, timeout_sec=_PIPER_WINSOUND_PLAYBACK_TIMEOUT_SEC):
            return False
        return True
    except Exception as exc:
        log_event_throttled(
            "piper_speak_exception",
            15.0,
            "WARN",
            "piper: speak pipeline failed",
            error=f"{type(exc).__name__}: {exc}",
            source=str(getattr(selected, "source", "") or ""),
        )
        return False
    finally:
        try:
            os.remove(wav_path)
        except Exception:
            log_event_throttled(
                "piper_wav_cleanup",
                60.0,
                "WARN",
                "piper: temporary wav cleanup failed",
                path=os.path.basename(wav_path),
            )
