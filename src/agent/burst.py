"""Burst-aware DM dispatcher.

When the boss DMs several messages in quick succession, we don't want
N parallel agent rounds with N separate replies. This wrapper:

  - serialises per-chat work via an asyncio.Lock,
  - buffers each new message,
  - cancels the in-flight handler (if any),
  - spawns a fresh handler that processes the whole buffered batch
    as a single turn,
  - signals batch_size>1 to the agent so its system prompt nudges it
    to self-review prior tool effects before acting again.

DM-only by design: group chats only trigger on @mention so burstiness
is not a real UX problem there.

Side-effect contract: cancellation can interrupt at any await point,
including mid tool-round. Tool effects already persisted to SQLite /
Lark / outbound_messages survive — the replacement turn is expected to
discover them (list_reminders / list_tasks / get_communication_log) and
update/delete instead of duplicating. We do not snapshot-and-rollback.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Awaitable, Callable

from src.channels.base import IncomingMessage

logger = logging.getLogger("agent.burst")

_in_flight: dict[str, asyncio.Task] = {}
_in_flight_batch: dict[str, list[IncomingMessage]] = {}
_pending: dict[str, list[IncomingMessage]] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(chat_id: str) -> asyncio.Lock:
    lk = _locks.get(chat_id)
    if lk is None:
        lk = asyncio.Lock()
        _locks[chat_id] = lk
    return lk


def _merge(batch: list[IncomingMessage]) -> IncomingMessage:
    """Combine N messages from the same DM into one logical turn."""
    last = batch[-1]
    texts = [m.text for m in batch if m.text]
    merged_text = "\n".join(texts)
    merged_attachments: list = []
    for m in batch:
        merged_attachments.extend(m.attachments or [])
    return replace(last, text=merged_text, attachments=merged_attachments)


Runner = Callable[[IncomingMessage, int], Awaitable[None]]


async def dispatch(incoming: IncomingMessage, runner: Runner) -> None:
    """Burst-aware entry. `runner(merged_message, batch_size)` is called
    exactly once per coalesced batch."""
    chat_id = incoming.chat_id

    async with _lock_for(chat_id):
        cur = _in_flight.get(chat_id)
        if cur is not None and not cur.done():
            # Claim the in-flight batch BEFORE yielding to `await cur`,
            # otherwise the cancelled task's own `finally` block can race
            # us and pop _in_flight_batch first, losing those messages.
            old_batch = _in_flight_batch.pop(chat_id, [])
            cur.cancel()
            try:
                await cur
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "[burst chat:%s] superseded task raised on cancel", chat_id,
                )
            if old_batch:
                _pending[chat_id] = old_batch + _pending.get(chat_id, [])
                logger.info(
                    "[burst chat:%s] re-buffered %d msg(s) from cancelled task",
                    chat_id, len(old_batch),
                )

        _pending.setdefault(chat_id, []).append(incoming)

        batch = _pending.pop(chat_id, [])
        if not batch:
            return
        merged = _merge(batch)
        batch_size = len(batch)
        task = asyncio.create_task(runner(merged, batch_size))
        _in_flight[chat_id] = task
        _in_flight_batch[chat_id] = list(batch)

    # Lock released — any newer message can now supersede us.
    try:
        await task
    except asyncio.CancelledError:
        pass  # superseded by a later burst, expected
    except Exception:
        logger.exception("[burst chat:%s] handler raised", chat_id)
    finally:
        if _in_flight.get(chat_id) is task:
            _in_flight.pop(chat_id, None)
            _in_flight_batch.pop(chat_id, None)
