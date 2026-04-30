"""
Compatibility shim — delegates to `src.channels.telegram.TelegramMessenger`.

Callers across the codebase still import `from src.channels import telegram_singleton as telegram`
and call `telegram.send(...)`, `telegram.start_polling(on_message)`, etc.
That API is preserved here; under the hood it drives a singleton
`TelegramMessenger` instance so there's exactly one HTTP client + polling loop.

Refactor plan: incrementally migrate callers to `ctx.messenger.send_message(...)`
and eventually delete this module.
"""
from __future__ import annotations

import logging

from src.channels.telegram import TelegramMessenger

logger = logging.getLogger("telegram")

_messenger: TelegramMessenger | None = None


def get_messenger() -> TelegramMessenger:
    if _messenger is None:
        raise RuntimeError("telegram not initialized — call init_telegram(token) first")
    return _messenger


async def init_telegram(token: str) -> None:
    global _messenger
    _messenger = TelegramMessenger(token)
    await _messenger.init()


# --- Legacy send/edit API — keeps int chat_ids + parse_mode naming ----------

def _fmt_from_parse_mode(parse_mode: str) -> str:
    p = (parse_mode or "").lower()
    if p == "markdown":
        return "markdown"
    if p == "html":
        return "html"
    return "plain"


def _looks_like_uuid(s: str) -> bool:
    """Heuristic: 36-char string with 4 hyphens at the canonical positions."""
    s = str(s)
    if len(s) != 36:
        return False
    return s[8] == "-" and s[13] == "-" and s[18] == "-" and s[23] == "-"


async def _to_internal_chat_id(chat_id_raw: str) -> str:
    """Accept either external Telegram numeric chat id (legacy) or internal UUID.

    Returns an `internal_chat_id` (conversation table). When the UUID is a
    person internal id (e.g. a boss id passed by `send_reminder`), we map
    it to the DM conversation by looking up the person's external Telegram
    id and resolving / creating the matching DM `conversation` row.
    """
    from src import db
    s = str(chat_id_raw)
    if _looks_like_uuid(s):
        # Already a conversation id?
        if await db.lookup_external_for_conversation(s):
            return s
        # Person id → map to that person's DM conversation.
        ext = await db.lookup_external_for_person(s)
        if ext:
            provider, external_id = ext
            return await db.resolve_or_create_conversation(provider, external_id, "dm", "")
        return s  # unknown UUID; let the API call fail loudly

    # Numeric external id — Telegram convention: negative = (super)group, positive = DM.
    try:
        chat_type = "group" if int(s) < 0 else "dm"
    except (TypeError, ValueError):
        chat_type = "dm"
    return await db.resolve_or_create_conversation("telegram", s, chat_type, "")


async def _to_internal_user_id(user_id_raw: str) -> str:
    """Accept either external Telegram numeric user id or internal UUID.
    Returns the internal person id."""
    s = str(user_id_raw)
    if _looks_like_uuid(s):
        return s
    from src import db
    return await db.resolve_or_create_person("telegram", s, "", "")


async def _messenger_for(internal_chat_id: str):
    """Return the channel that owns this conversation, falling back to Telegram."""
    from src import db
    from src.channels import registry
    ext = await db.lookup_external_for_conversation(internal_chat_id)
    if ext:
        provider = ext[0]
        if provider != "telegram":
            m = registry.get(provider)
            if m is not None:
                return m
    return get_messenger()


async def send(
    chat_id: str,
    text: str,
    parse_mode: str = "Markdown",
    save_history: bool = True,
) -> int | str | None:
    internal = await _to_internal_chat_id(chat_id)
    messenger = await _messenger_for(internal)
    out = await messenger.send_message(
        internal,
        text,
        format=_fmt_from_parse_mode(parse_mode),
        save_history=save_history,
    )
    if not out.message_id:
        return None
    try:
        return int(out.message_id)
    except (TypeError, ValueError):
        return out.message_id


# Alias kept for code paths still using the longer name.
send_message = send


async def edit_message(
    chat_id: str,
    message_id: int,
    text: str,
    parse_mode: str = "Markdown",
) -> None:
    from src.channels.base import UnsupportedOperation
    internal = await _to_internal_chat_id(chat_id)
    messenger = await _messenger_for(internal)
    try:
        await messenger.edit_message(
            internal, str(message_id), text, format=_fmt_from_parse_mode(parse_mode)
        )
    except UnsupportedOperation:
        # Channels without edit (e.g. Zalo) — degrade to a fresh send.
        await messenger.send_message(
            internal, text, format=_fmt_from_parse_mode(parse_mode), save_history=False,
        )


# --- Group admin (legacy int args) ------------------------------------------

async def get_chat_member(chat_id: str, user_id: str) -> dict:
    return await get_messenger().get_chat_member(
        await _to_internal_chat_id(chat_id), await _to_internal_user_id(user_id)
    )


async def add_chat_member(chat_id: str, user_id: str) -> bool:
    return await get_messenger().add_chat_member(
        await _to_internal_chat_id(chat_id), await _to_internal_user_id(user_id)
    )


async def set_chat_title(chat_id: str, title: str) -> bool:
    return await get_messenger().set_chat_title(await _to_internal_chat_id(chat_id), title)


async def set_chat_description(chat_id: str, description: str) -> bool:
    return await get_messenger().set_chat_description(
        await _to_internal_chat_id(chat_id), description
    )


async def pin_chat_message(chat_id: str, message_id: int) -> bool:
    return await get_messenger().pin_chat_message(
        await _to_internal_chat_id(chat_id), str(message_id)
    )


async def unpin_all_chat_messages(chat_id: str) -> bool:
    return await get_messenger().unpin_all_chat_messages(await _to_internal_chat_id(chat_id))


async def ban_chat_member(chat_id: str, user_id: str) -> bool:
    return await get_messenger().ban_chat_member(
        await _to_internal_chat_id(chat_id), await _to_internal_user_id(user_id)
    )


async def unban_chat_member(chat_id: str, user_id: str) -> bool:
    return await get_messenger().unban_chat_member(
        await _to_internal_chat_id(chat_id), await _to_internal_user_id(user_id)
    )


async def create_invite_link(chat_id: str, member_limit: int = 1, expire_hours: int = 24) -> str:
    return await get_messenger().create_invite_link(
        await _to_internal_chat_id(chat_id), member_limit=member_limit, expire_hours=expire_hours
    )


async def get_chat_administrators(chat_id: str) -> list[dict]:
    return await get_messenger().get_chat_administrators(await _to_internal_chat_id(chat_id))


async def get_bot_id() -> int | None:
    bid = await get_messenger().get_bot_id()
    return int(bid) if bid else None


# Phase 5b removed the polling bridge: main.py now wires
# `messenger.start(router.handle)` directly. The outbound shims (send/edit
# and group-admin helpers) above are kept until every caller migrates to the
# messenger instance from `AppContainer.messengers["telegram"]`.


def stop_polling() -> None:
    m = _messenger
    if m is not None:
        m._polling = False


async def close_telegram() -> None:
    global _messenger
    if _messenger is not None:
        await _messenger.stop()
        _messenger = None
