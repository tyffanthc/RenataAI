from __future__ import annotations


def normalize_system_name(value: str | None) -> str:
    return (value or "").strip().lower()


def validate_via(
    value: str,
    existing: list[str],
    start: str,
    end: str,
    *,
    min_length_warn: int = 3,
) -> tuple[bool, str | None, bool]:
    normalized = normalize_system_name(value)
    if not normalized:
        return False, "empty", False

    start_norm = normalize_system_name(start)
    end_norm = normalize_system_name(end)
    if normalized and (normalized == start_norm or normalized == end_norm):
        return False, "start_or_end", False

    existing_norm = {normalize_system_name(item) for item in existing}
    if normalized in existing_norm:
        return False, "duplicate", False

    warn_short = len(value.strip()) < min_length_warn
    return True, None, warn_short
