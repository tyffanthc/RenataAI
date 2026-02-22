from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from typing import Any, Optional, Tuple, Dict

import config
from logic import utils

_CACHE_ROOT_MIGRATION_DONE = False


def _merge_tree_no_overwrite(src_dir: str, dst_dir: str) -> int:
    moved = 0
    for root, _dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dst_root = dst_dir if rel in {".", ""} else os.path.join(dst_dir, rel)
        os.makedirs(dst_root, exist_ok=True)
        for name in files:
            src = os.path.join(root, name)
            dst = os.path.join(dst_root, name)
            try:
                if os.path.exists(dst):
                    continue
                shutil.move(src, dst)
                moved += 1
            except Exception:
                continue
    return moved


def _prune_empty_dirs(path: str) -> None:
    if not os.path.isdir(path):
        return
    for root, dirs, _files in os.walk(path, topdown=False):
        for d in dirs:
            full = os.path.join(root, d)
            try:
                os.rmdir(full)
            except Exception:
                pass
    try:
        os.rmdir(path)
    except Exception:
        pass


def _migrate_legacy_appdata_cache_if_needed(base_appdata: str) -> None:
    global _CACHE_ROOT_MIGRATION_DONE
    if _CACHE_ROOT_MIGRATION_DONE:
        return
    _CACHE_ROOT_MIGRATION_DONE = True
    try:
        old_root = os.path.join(base_appdata, "Renata", "cache")
        new_root = os.path.join(base_appdata, "RenataAI", "cache")
        if not os.path.isdir(old_root):
            return
        os.makedirs(new_root, exist_ok=True)
        moved = _merge_tree_no_overwrite(old_root, new_root)
        _prune_empty_dirs(old_root)
        try:
            os.rmdir(os.path.join(base_appdata, "Renata"))
        except Exception:
            pass
        if moved > 0:
            utils.MSG_QUEUE.put(("log", f"[CACHE] migrated {moved} files to APPDATA\\\\RenataAI\\\\cache"))
    except Exception:
        return


def _default_cache_dir(app_name: str = "RenataAI") -> str:
    base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache")
    else:
        _migrate_legacy_appdata_cache_if_needed(base)
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

    def get(self, key: str, *, allow_expired: bool = False) -> Tuple[bool, Any | None, Dict[str, Any]]:
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
        created_at = file_meta.get("created_at")
        if created_at is not None:
            try:
                meta["data_age_seconds"] = max(0.0, time.time() - float(created_at))
            except Exception:
                pass

        if expires_at is not None and time.time() > float(expires_at):
            meta.update(file_meta)
            meta["reason"] = "expired"
            meta["stale"] = True
            if allow_expired:
                if config.get("debug_cache", False):
                    _emit_cache_status("INFO", "CACHE_HIT", "Cache stale hit")
                return True, data.get("value"), meta
            if config.get("debug_cache", False):
                _emit_cache_status("INFO", "CACHE_MISS", "Cache expired")
            return False, None, meta

        if config.get("debug_cache", False):
            _emit_cache_status("INFO", "CACHE_HIT", "Cache hit")
        meta.update(file_meta)
        meta["stale"] = False
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
            "ttl_seconds": float(ttl_seconds) if ttl_seconds is not None else None,
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
