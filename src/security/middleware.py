"""Rate-limit helper used inside route handlers.

Usage::

    await rate_check(request, f"login:{ip}", limit=5, window_sec=300)

Raises ``HTTPException(429)`` when the bucket is full so the route can simply
``await`` and return — no manual branching.
"""

from __future__ import annotations

from fastapi import HTTPException, Request


async def rate_check(
    request: Request, key: str, limit: int, window_sec: int
) -> None:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return  # no limiter wired (e.g. unit tests) — fail open
    if not await limiter.check(key, limit, window_sec):
        raise HTTPException(status_code=429, detail="rate limit")
