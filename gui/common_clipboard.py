from logic.route_clipboard import (
    compute_route_signature,
    format_route_for_clipboard,
    try_copy_to_clipboard,
)


def copy_text_to_clipboard(text: str, *, context: str = "context_menu") -> bool:
    if not text:
        return False
    result = try_copy_to_clipboard(text, context=context)
    return bool(result.get("ok"))
