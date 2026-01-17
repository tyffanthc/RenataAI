from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional, Tuple, Dict

import config
from logic import utils


def _default_cache_dir(app_name: str = "Renata") -> str:
    base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, app_name, "cache")


def _safe_filename(key: str, namespace: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"{namespace}_{digest}.json"


def _emit_cache_status(level: str, code: str, text: str | None = None) -> None:
    try:
        from gui import common as gui_common  # type: ignore

        gui_common.emit_status(
            level,
            code,
            text=text,
            source="cache",
            notify_overlay=False,
        )
    except Exception:
        msg = text or code
        utils.MSG_QUEUE.put(("log", f"[{level}] {code}: {msg}"))


class CacheStore:
    def __init__(
        self,
        namespace: str = "spansh",
        *,
        base_dir: Optional[str] = None,
        provider: Optional[str] = None,
        version: str = "v1",
    ) -> None:
        self.namespace = (namespace or "cache").strip()
        self.provider = provider or self.namespace
        self.version = version
        self.base_dir = base_dir or _default_cache_dir()

    def _path_for_key(self, key: str) -> str:
        filename = _safe_filename(key, self.namespace)
        return os.path.join(self.base_dir, self.namespace, filename)

    def get(self, key: str) -> Tuple[bool, Any | None, Dict[str, Any]]:
        meta: Dict[str, Any] = {"key": key}
        if not key:
            return False, None, meta

        path = self._path_for_key(str(key))
        if not os.path.exists(path):
            if config.get("debug_cache", False):
                _emit_cache_status("INFO", "CACHE_MISS", "Cache miss")
            meta["reason"] = "not_found"
            return False, None, meta

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            _emit_cache_status("WARN", "CACHE_CORRUPT", "Cache corrupt")
            try:
                os.remove(path)
            except Exception:
                pass
            meta["reason"] = "corrupt"
            return False, None, meta

        file_meta = data.get("meta") or {}
        expires_at = file_meta.get("expires_at")
        if expires_at is not None and time.time() > float(expires_at):
            meta.update(file_meta)
            meta["reason"] = "expired"
            try:
                os.remove(path)
            except Exception:
                pass
            if config.get("debug_cache", False):
                _emit_cache_status("INFO", "CACHE_MISS", "Cache expired")
            return False, None, meta

        if config.get("debug_cache", False):
            _emit_cache_status("INFO", "CACHE_HIT", "Cache hit")
        meta.update(file_meta)
        return True, data.get("value"), meta

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float,
        meta: Dict[str, Any] | None = None,
    ) -> None:
        if not key:
            return

        created_at = time.time()
        expires_at = created_at + float(ttl_seconds) if ttl_seconds is not None else None
        entry_meta = {
            "key": key,
            "created_at": created_at,
            "expires_at": expires_at,
            "version": self.version,
            "provider": self.provider,
        }
        if meta:
            entry_meta.update(meta)

        path = self._path_for_key(str(key))
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = f"{path}.tmp"
            payload = {"meta": entry_meta, "value": value}
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            _emit_cache_status("WARN", "CACHE_WRITE_FAIL", "Cache write failed")

    def delete(self, key: str) -> None:
        if not key:
            return
        path = self._path_for_key(str(key))
        try:
            os.remove(path)
        except Exception:
            return
