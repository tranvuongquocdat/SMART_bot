"""Provider-agnostic Lark Chat ID resolution.

Lark People's "Chat ID" field stores the contact's external messenger id —
- Telegram users: signed numeric string ("999000001")
- Zalo users: alphanumeric string ("abc_xyz123")

Older code paths assumed Telegram and did `str(int(raw))` + hardcoded
`provider="telegram"` in `resolve_or_create_person`. That crashes on Zalo ids
and writes wrong-provider identity rows.

`resolve_lark_chat_id` is the one place every caller reading Chat ID from
Lark should go through: it looks up `external_identity` by external_id alone,
and falls back to inferring provider by shape only when the contact is
totally unknown.
"""
from __future__ import annotations


def infer_provider(chat_id: str) -> str:
    """Shape-based provider hint. Telegram ids are integers; everything else
    we treat as Zalo until a richer signal is available."""
    s = str(chat_id).strip()
    if not s:
        return "telegram"
    try:
        int(s)
        return "telegram"
    except (TypeError, ValueError):
        return "zalo"


async def resolve_lark_chat_id(raw: object, name: str = "") -> str | None:
    """Lark Chat ID (any provider) → internal person UUID.

    Returns None for empty/None input. For known contacts, uses the recorded
    provider from `external_identity`. For unknown contacts, infers provider
    by shape and creates an identity row.
    """
    from src import db  # avoid import cycle at module load
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    existing = await db.lookup_person_by_external_id(s)
    if existing:
        internal_id, _provider = existing
        return internal_id
    provider = infer_provider(s)
    return await db.resolve_or_create_person(provider, s, name or "", "")
