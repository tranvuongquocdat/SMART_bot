"""
Compatibility shim — delegates to `src.channels.telegram.TelegramMessenger`.

Callers across the codebase still import `from src.services import telegram`
and call `telegram.send(...)`, `telegram.start_polling(on_message)`, etc.
That API is preserved here; under the hood it drives a singleton
`TelegramMessenger` instance so there's exactly one HTTP client + polling loop.

Refactor plan: incrementally migrate callers to `ctx.messenger.send_message(...)`
and eventually delete this module.
"""
from __future__ import annotations

import logging
from typing import Callable

from src.channels.telegram import TelegramMessenger
from src.channels.base import IncomingMessage

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


async def send(
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    save_history: bool = True,
) -> int | None:
    out = await get_messenger().send_message(
        str(chat_id),
        text,
        format=_fmt_from_parse_mode(parse_mode),
        save_history=save_history,
    )
    return int(out.message_id) if out.message_id else None


# Alias kept for code paths still using the longer name.
send_message = send


async def edit_message(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str = "Markdown",
) -> None:
    await get_messenger().edit_message(
        str(chat_id), str(message_id), text, format=_fmt_from_parse_mode(parse_mode)
    )


# --- Group admin (legacy int args) ------------------------------------------

async def get_chat_member(chat_id: int, user_id: int) -> dict:
    return await get_messenger().get_chat_member(str(chat_id), str(user_id))


async def add_chat_member(chat_id: int, user_id: int) -> bool:
    return await get_messenger().add_chat_member(str(chat_id), str(user_id))


async def set_chat_title(chat_id: int, title: str) -> bool:
    return await get_messenger().set_chat_title(str(chat_id), title)


async def set_chat_description(chat_id: int, description: str) -> bool:
    return await get_messenger().set_chat_description(str(chat_id), description)


async def pin_chat_message(chat_id: int, message_id: int) -> bool:
    return await get_messenger().pin_chat_message(str(chat_id), str(message_id))


async def unpin_all_chat_messages(chat_id: int) -> bool:
    return await get_messenger().unpin_all_chat_messages(str(chat_id))


async def ban_chat_member(chat_id: int, user_id: int) -> bool:
    return await get_messenger().ban_chat_member(str(chat_id), str(user_id))


async def unban_chat_member(chat_id: int, user_id: int) -> bool:
    return await get_messenger().unban_chat_member(str(chat_id), str(user_id))


async def create_invite_link(chat_id: int, member_limit: int = 1, expire_hours: int = 24) -> str:
    return await get_messenger().create_invite_link(
        str(chat_id), member_limit=member_limit, expire_hours=expire_hours
    )


async def get_chat_administrators(chat_id: int) -> list[dict]:
    return await get_messenger().get_chat_administrators(str(chat_id))


async def get_bot_id() -> int | None:
    bid = await get_messenger().get_bot_id()
    return int(bid) if bid else None


# --- Polling bridge: old positional callback → IncomingMessage --------------
# agent.handle_message still uses the legacy signature. Convert IncomingMessage
# back to positional args so nothing in agent.py has to change until Phase 0
# moves all callers to the new API.

async def start_polling(on_message: Callable) -> None:
    async def _bridge(msg: IncomingMessage) -> None:
        reply_to = None
        if msg.reply_to_sender_id:
            reply_to = {
                "id": int(msg.reply_to_sender_id),
                "name": "",        # legacy callback didn't carry this reliably
                "username": "",
            }
        try:
            await on_message(
                msg.text or "",
                int(msg.chat_id),
                int(msg.sender_id) if msg.sender_id else None,
                msg.chat_type == "group",
                msg.is_mentioned,
                msg.group_name,
                sender_name=msg.sender_name,
                mentions=msg.mentions,
                username_mentions=msg.username_mentions,
                reply_to=reply_to,
                new_members=msg.new_members,
            )
        except Exception:
            logger.exception("on_message handler failed")

    await get_messenger().start(_bridge)


def stop_polling() -> None:
    m = _messenger
    if m is not None:
        m._polling = False


async def close_telegram() -> None:
    global _messenger
    if _messenger is not None:
        await _messenger.stop()
        _messenger = None
