"""ChatRunRegistry — hàng đợi tuần tự + hủy theo hội thoại."""
from __future__ import annotations

import asyncio

import pytest

from src.services.chat_runs import ChatRunRegistry


@pytest.mark.asyncio
async def test_runs_serialize_per_key():
    reg = ChatRunRegistry()
    order: list[int] = []

    async def step(i: int, delay: float):
        await asyncio.sleep(delay)
        order.append(i)

    t1 = reg.submit("k", step(1, 0.05))
    t2 = reg.submit("k", step(2, 0.0))  # nhanh hơn nhưng phải chờ lượt 1
    await asyncio.gather(t1, t2)
    assert order == [1, 2]


@pytest.mark.asyncio
async def test_keys_run_independently():
    reg = ChatRunRegistry()
    order: list[str] = []

    async def step(name: str, delay: float):
        await asyncio.sleep(delay)
        order.append(name)

    ta = reg.submit("a", step("a-slow", 0.05))
    tb = reg.submit("b", step("b-fast", 0.0))
    await asyncio.gather(ta, tb)
    assert order == ["b-fast", "a-slow"]


@pytest.mark.asyncio
async def test_cancel_stops_running_and_queued():
    reg = ChatRunRegistry()
    done: list[int] = []

    async def step(i: int):
        await asyncio.sleep(0.2)
        done.append(i)

    t1 = reg.submit("k", step(1))
    t2 = reg.submit("k", step(2))
    await asyncio.sleep(0.01)
    assert reg.running("k") is True
    assert reg.cancel("k") == 2
    await asyncio.gather(t1, t2, return_exceptions=True)
    assert done == []
    assert reg.running("k") is False


@pytest.mark.asyncio
async def test_chain_continues_after_cancelled_predecessor():
    reg = ChatRunRegistry()
    done: list[int] = []

    async def step(i: int, delay: float = 0.0):
        await asyncio.sleep(delay)
        done.append(i)

    t1 = reg.submit("k", step(1, 0.2))
    await asyncio.sleep(0.01)
    reg.cancel("k")
    await asyncio.gather(t1, return_exceptions=True)
    t2 = reg.submit("k", step(2))
    await t2
    assert done == [2]
