from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import config

PROFILE_FREE = "FREE"
PROFILE_PRO = "PRO"

CAP_VOICE_STT = "capabilities.voice_stt"
CAP_UI_EXTENDED_TABS = "capabilities.ui_extended_tabs"
CAP_SETTINGS_FULL = "capabilities.settings_full"
CAP_TTS_ADVANCED_POLICY = "capabilities.tts_advanced_policy"

CAPABILITY_KEYS = (
    CAP_VOICE_STT,
    CAP_UI_EXTENDED_TABS,
    CAP_SETTINGS_FULL,
    CAP_TTS_ADVANCED_POLICY,
)

_PROFILE_DEFAULTS: dict[str, dict[str, bool]] = {
    PROFILE_FREE: {
        CAP_VOICE_STT: False,
        CAP_UI_EXTENDED_TABS: False,
        CAP_SETTINGS_FULL: False,
        CAP_TTS_ADVANCED_POLICY: False,
    },
    PROFILE_PRO: {
        CAP_VOICE_STT: True,
        CAP_UI_EXTENDED_TABS: True,
        CAP_SETTINGS_FULL: True,
        CAP_TTS_ADVANCED_POLICY: True,
    },
}


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "pro"}:
        return True
    if text in {"0", "false", "no", "off", "free"}:
        return False
    return default


def normalize_profile(raw_profile: Any) -> str:
    value = str(raw_profile or "").strip().upper()
    if value == PROFILE_PRO:
        return PROFILE_PRO
    return PROFILE_FREE


def resolve_profile(settings: Mapping[str, Any] | None = None) -> str:
    payload = settings if settings is not None else config.config.as_dict()
    explicit_profile = payload.get("plan.profile")
    if explicit_profile:
        return normalize_profile(explicit_profile)
    free_policy = _to_bool(payload.get("features.tts.free_policy_enabled"), True)
    return PROFILE_FREE if free_policy else PROFILE_PRO


@dataclass(frozen=True)
class CapabilitiesSnapshot:
    profile: str
    values: Mapping[str, bool]

    def has(self, capability_key: str) -> bool:
        return bool(self.values.get(capability_key, False))

    def as_dict(self) -> dict[str, bool]:
        return dict(self.values)


def resolve_capabilities(settings: Mapping[str, Any] | None = None) -> CapabilitiesSnapshot:
    payload = settings if settings is not None else config.config.as_dict()
    profile = resolve_profile(payload)
    merged = dict(_PROFILE_DEFAULTS.get(profile, _PROFILE_DEFAULTS[PROFILE_FREE]))

    if "features.tts.free_policy_enabled" in payload:
        free_policy = _to_bool(
            payload.get("features.tts.free_policy_enabled"),
            profile == PROFILE_FREE,
        )
        merged[CAP_TTS_ADVANCED_POLICY] = not free_policy
        if free_policy:
            merged[CAP_SETTINGS_FULL] = False
            merged[CAP_UI_EXTENDED_TABS] = False

    for key in CAPABILITY_KEYS:
        if key in payload:
            merged[key] = _to_bool(payload.get(key), merged.get(key, False))

    return CapabilitiesSnapshot(profile=profile, values=merged)


def has_capability(capability_key: str, settings: Mapping[str, Any] | None = None) -> bool:
    return resolve_capabilities(settings).has(capability_key)


def is_free_profile(settings: Mapping[str, Any] | None = None) -> bool:
    return resolve_profile(settings) == PROFILE_FREE


def is_pro_profile(settings: Mapping[str, Any] | None = None) -> bool:
    return resolve_profile(settings) == PROFILE_PRO


def capability_config_patch_from_free_policy(free_policy_enabled: bool) -> dict[str, Any]:
    profile = PROFILE_FREE if free_policy_enabled else PROFILE_PRO
    return {
        "plan.profile": profile,
        "features.tts.free_policy_enabled": bool(free_policy_enabled),
        CAP_SETTINGS_FULL: not bool(free_policy_enabled),
        CAP_UI_EXTENDED_TABS: not bool(free_policy_enabled),
        CAP_TTS_ADVANCED_POLICY: not bool(free_policy_enabled),
    }

