"""with_retry retries httpx network errors and HTTP 5xx; never retries Lark business errors."""
from unittest.mock import AsyncMock

import httpx
import pytest

import src.infrastructure.lark_client as lark


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://x.test")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


async def test_with_retry_recovers_on_5xx():
    fn = AsyncMock(side_effect=[_http_error(503), "ok"])
    result = await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert result == "ok"
    assert fn.call_count == 2


async def test_with_retry_retries_network_error():
    fn = AsyncMock(side_effect=[httpx.ConnectError("boom"), "ok"])
    result = await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert result == "ok"


async def test_with_retry_does_not_retry_business_error():
    fn = AsyncMock(side_effect=Exception("Lark error: 1254 - permission denied"))
    with pytest.raises(Exception, match="Lark error"):
        await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert fn.call_count == 1


async def test_with_retry_does_not_retry_4xx():
    fn = AsyncMock(side_effect=_http_error(403))
    with pytest.raises(httpx.HTTPStatusError):
        await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert fn.call_count == 1


async def test_with_retry_gives_up_after_attempts():
    fn = AsyncMock(side_effect=[_http_error(503), _http_error(503), _http_error(503)])
    with pytest.raises(httpx.HTTPStatusError):
        await lark.with_retry(fn, attempts=2, backoff=0.0)
    # attempts=2 means: initial try + up to 2 retries = 3 total calls
    assert fn.call_count == 3
