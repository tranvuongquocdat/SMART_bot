from src.llm.base import ChatMessage


def mark_cache_breakpoint(messages: list[ChatMessage], hint: str | None) -> list[ChatMessage]:
    """Set cache_breakpoint=True on last message of stable prefix."""
    if not hint:
        return messages
    boundary_role = {
        "after_system": "system",
        "after_semantic_memory": "user",
        "after_group_note": "user",
    }
    target = boundary_role.get(hint, "system")
    for i, m in enumerate(messages[:4]):
        if m.role == target:
            messages[i].cache_breakpoint = True
    return messages
