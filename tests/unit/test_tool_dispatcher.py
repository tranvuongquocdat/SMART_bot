import asyncio
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from src.tools import registry
from src.tools.base import ToolContext, ToolResult
from src.tools.dispatcher import ToolDispatcher
from src.tools.registry import tool


@dataclass
class FakeCall:
    id: str
    name: str
    arguments: dict


@pytest.fixture(autouse=True)
def _clear_registry():
    snap = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(snap)


def _ctx() -> ToolContext:
    return ToolContext(
        boss_id=1,
        boss_role="boss",
        pool=None,
        qdrant=None,
        bus=None,
        memory=None,
        retriever_factory=None,
        llm=None,
        trace_id="t",
        span_id="s",
    )


@pytest.mark.asyncio
async def test_parallel_batch_runs_concurrently():
    started: list[float] = []

    @tool(
        name="p_a",
        description="",
        parameters={"type": "object", "properties": {}},
        parallel_safe=True,
    )
    async def _a(ctx):
        loop = asyncio.get_event_loop()
        started.append(loop.time())
        await asyncio.sleep(0.05)
        return ToolResult(content="a")

    @tool(
        name="p_b",
        description="",
        parameters={"type": "object", "properties": {}},
        parallel_safe=True,
    )
    async def _b(ctx):
        loop = asyncio.get_event_loop()
        started.append(loop.time())
        await asyncio.sleep(0.05)
        return ToolResult(content="b")

    disp = ToolDispatcher(pool=None)
    calls = [FakeCall("1", "p_a", {}), FakeCall("2", "p_b", {})]
    with patch(
        "src.tools.dispatcher.ToolCallLogRepo"
    ) as mock_repo:
        mock_repo.return_value.insert = _async_noop
        results = await disp.call_batch(calls, _ctx())
    names = {r[0] for r in results}
    assert names == {"1", "2"}
    # Both started within 10ms of each other → ran in parallel
    assert abs(started[0] - started[1]) < 0.02


@pytest.mark.asyncio
async def test_timeout_recorded_as_error():
    @tool(
        name="slow",
        description="",
        parameters={"type": "object", "properties": {}},
        timeout_s=0,
    )
    async def _slow(ctx):
        await asyncio.sleep(0.5)
        return ToolResult(content="ok")

    disp = ToolDispatcher(pool=None)
    with patch("src.tools.dispatcher.ToolCallLogRepo") as mock_repo:
        mock_repo.return_value.insert = _async_noop
        results = await disp.call_batch([FakeCall("1", "slow", {})], _ctx())
    assert results[0][1].error == "timeout"


async def _async_noop(**_kwargs):
    return 0
