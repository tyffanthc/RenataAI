from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import time
from typing import Any, Dict

STATE_SCHEMA_VERSION = 1
STATE_LAYER_KEYS = ("ui_state", "preferences", "domain_state", "anti_spam_state")


# Legacy runtime defaults used by config.STATE.
LEGACY_DOMAIN_STATE_DEFAULTS: Dict[str, Any] = {
    "sys": "Nieznany",
    "trasa": [],
    "rtr_data": {},
    "idx": 0,
    "receptura": None,
    "inventory": {},
    "ciala_tot": 0,
    "ciala_odk": 0,
    "milestones": [],
    "station": None,
    "is_docked": False,
    "route_mode": "idle",
    "route_target": "",
    "route_progress_percent": 0,
    "route_next_system": "",
    "route_is_off_route": False,
}

_DEFAULT_STATE_CONTRACT: Dict[str, Any] = {
    "schema_version": STATE_SCHEMA_VERSION,
    "ui_state": {},
    "preferences": {},
    "domain_state": copy.deepcopy(LEGACY_DOMAIN_STATE_DEFAULTS),
    "anti_spam_state": {},
}

_PII_BLOCKLIST = {
    "commander_name",
    "cmdr_name",
    "player_name",
    "user_name",
    "username",
    "email",
    "account_id",
    "user_id",
    "machine_id",
    "hwid",
    "ip",
    "ip_address",
}

_MAX_DEPTH = 6
_MAX_COLLECTION = 512
_MAX_STR_LEN = 1024

RESTART_LOSS_AUDIT: Dict[str, Dict[str, str]] = {
    "exobio_sample_state": {
        "decision": "persist",
        "reason": "Sample continuity must survive restarts (1/3 -> 2/3 flow).",
    },
    "fss_progress_and_first_discovery_flags": {
        "decision": "persist",
        "reason": "Avoid duplicate callouts and preserve discovery continuity.",
    },
    "dss_high_value_footfall_callout_flags": {
        "decision": "persist",
        "reason": "Callout dedup should survive short restart windows.",
    },
    "route_milestone_progress_cache": {
        "decision": "persist",
        "reason": "Route-awareness UX should continue after restart.",
    },
    "trade_jackpot_cache": {
        "decision": "persist",
        "reason": "Avoid repeated jackpot spam after restart.",
    },
    "smuggler_warned_targets": {
        "decision": "persist",
        "reason": "Warn-once behavior should not reset immediately.",
    },
    "dispatcher_debouncer_windows": {
        "decision": "persist",
        "reason": "Anti-spam windows need continuity with short TTL.",
    },
    "combat_survival_pattern_runtime": {
        "decision": "session-only",
        "reason": "Transient combat patterning should not outlive session context.",
    },
}


def default_state_contract() -> Dict[str, Any]:
    return copy.deepcopy(_DEFAULT_STATE_CONTRACT)


def default_runtime_domain_state() -> Dict[str, Any]:
    return copy.deepcopy(LEGACY_DOMAIN_STATE_DEFAULTS)


def restart_loss_audit_contract() -> Dict[str, Dict[str, str]]:
    return copy.deepcopy(RESTART_LOSS_AUDIT)


def _safe_schema_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _is_state_contract_payload(payload: Dict[str, Any]) -> bool:
    if "schema_version" in payload:
        return True
    return any(key in payload for key in STATE_LAYER_KEYS)


def _is_blocked_key(raw_key: str) -> bool:
    return raw_key in _PII_BLOCKLIST


def _sanitize_value(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return None

    if value is None:
        return None

    if isinstance(value, (bool, int)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value

    if isinstance(value, str):
        return value[:_MAX_STR_LEN]

    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            key_cf = key.casefold()
            if _is_blocked_key(key_cf):
                continue
            cleaned_key = key[:128]
            cleaned_value = _sanitize_value(raw_value, depth + 1)
            if cleaned_value is None and raw_value is not None:
                continue
            cleaned[cleaned_key] = cleaned_value
            if len(cleaned) >= _MAX_COLLECTION:
                break
        return cleaned

    if isinstance(value, (list, tuple, set)):
        cleaned_list = []
        for item in value:
            cleaned_item = _sanitize_value(item, depth + 1)
            if cleaned_item is None and item is not None:
                continue
            cleaned_list.append(cleaned_item)
            if len(cleaned_list) >= _MAX_COLLECTION:
                break
        return cleaned_list

    # Keep contract JSON-only.
    return None


def _sanitize_layer(layer_value: Any) -> Dict[str, Any]:
    if not isinstance(layer_value, dict):
        return {}
    cleaned = _sanitize_value(layer_value, depth=0)
    if isinstance(cleaned, dict):
        return cleaned
    return {}


def _merge_runtime_defaults(domain_state: Dict[str, Any]) -> Dict[str, Any]:
    merged = default_runtime_domain_state()
    merged.update(domain_state or {})
    return merged


def _migrate_v0_to_v1(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _is_state_contract_payload(payload):
        domain = payload.get("domain_state")
    else:
        domain = payload

    if not isinstance(domain, dict):
        domain = {}

    return {
        "schema_version": 1,
        "ui_state": payload.get("ui_state", {}) if isinstance(payload, dict) else {},
        "preferences": payload.get("preferences", {}) if isinstance(payload, dict) else {},
        "domain_state": domain,
        "anti_spam_state": payload.get("anti_spam_state", {}) if isinstance(payload, dict) else {},
    }


def migrate_state_contract_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return default_state_contract()

    contract_like = _is_state_contract_payload(payload)
    working = dict(payload)
    version = _safe_schema_int(working.get("schema_version"), default=0)

    if not contract_like:
        version = 0

    # Future schema we do not understand -> graceful fallback to known layers only.
    if version > STATE_SCHEMA_VERSION:
        fallback = default_state_contract()
        if contract_like:
            for layer in STATE_LAYER_KEYS:
                fallback[layer] = _sanitize_layer(working.get(layer))
        else:
            fallback["domain_state"] = _sanitize_layer(working)
        fallback["domain_state"] = _merge_runtime_defaults(fallback["domain_state"])
        return fallback

    if version <= 0:
        working = _migrate_v0_to_v1(working)
        version = 1

    # Placeholder for future explicit migrations.
    while version < STATE_SCHEMA_VERSION:
        version += 1

    normalized = {
        "schema_version": STATE_SCHEMA_VERSION,
        "ui_state": _sanitize_layer(working.get("ui_state")),
        "preferences": _sanitize_layer(working.get("preferences")),
        "domain_state": _merge_runtime_defaults(_sanitize_layer(working.get("domain_state"))),
        "anti_spam_state": _sanitize_layer(working.get("anti_spam_state")),
    }
    return normalized


def runtime_state_from_contract(payload: Any) -> Dict[str, Any]:
    contract = migrate_state_contract_payload(payload)
    return copy.deepcopy(contract.get("domain_state", {}))


def contract_with_runtime_state(base_contract: Any, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    contract = migrate_state_contract_payload(base_contract)
    contract["domain_state"] = _merge_runtime_defaults(_sanitize_layer(runtime_state))
    contract["schema_version"] = STATE_SCHEMA_VERSION
    return contract


def load_state_contract_file(path: str) -> Dict[str, Any]:
    if not path:
        return default_state_contract()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return default_state_contract()
    return migrate_state_contract_payload(payload)


def save_state_contract_file(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    contract = migrate_state_contract_payload(payload)
    if not path:
        return contract

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=f"{os.path.basename(path)}.",
        suffix=".tmp",
        dir=(directory or None),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(contract, handle, indent=2, ensure_ascii=False)

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                os.replace(tmp_path, path)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                if attempt >= 2:
                    raise
                time.sleep(0.03)
        if last_error is not None:
            raise last_error
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return contract
