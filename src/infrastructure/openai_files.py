"""OpenAI Files API wrapper.

Uploads use purpose='user_data' with expires_after=30 days so OpenAI
auto-deletes orphan files. Caller does not need cleanup cron.

Retry policy: 3 attempts on 5xx / 429 / network with exponential backoff.
4xx other than 429 raises immediately (bad input).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIError, RateLimitError

logger = logging.getLogger("openai_files")

_BACKOFFS = (0.2, 1.0, 5.0)
_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RateLimitError, APIConnectionError, APIError,
)
_EXPIRES_SECONDS = 30 * 24 * 3600


async def upload(
    client: Any, path: str | Path, mime: str, filename: str,
) -> str:
    """Upload a local file, return OpenAI file_id."""
    path = Path(path)
    last_exc: Exception | None = None
    for i, backoff in enumerate((0.0,) + _BACKOFFS):
        if backoff:
            await asyncio.sleep(backoff)
        try:
            with path.open("rb") as fh:
                resp = await client.files.create(
                    file=(filename, fh, mime),
                    purpose="user_data",
                    expires_after={
                        "anchor": "created_at",
                        "seconds": _EXPIRES_SECONDS,
                    },
                )
            return resp.id
        except _RETRY_EXCEPTIONS as e:
            last_exc = e
            status = getattr(e, "status_code", None)
            if status and 400 <= status < 500 and status != 429:
                raise
            logger.warning(
                "openai_files.upload attempt %d for %s failed: %s",
                i + 1, filename, e,
            )
    assert last_exc is not None
    raise last_exc


async def delete(client: Any, file_id: str) -> None:
    """Best-effort delete; logs but never raises."""
    try:
        await client.files.delete(file_id)
    except Exception as e:
        logger.warning("openai_files.delete(%s) failed: %s", file_id, e)
