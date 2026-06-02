import asyncio

import pytest

from src.channels.web.sse import SSEHub


@pytest.mark.asyncio
async def test_publish_to_attached_client_receives_event():
    hub = SSEHub()
    client = hub.attach("u-001")
    await hub.publish("u-001", {"kind": "msg", "text": "hi"})
    ev = await asyncio.wait_for(client.queue.get(), timeout=0.5)
    assert ev["text"] == "hi"


@pytest.mark.asyncio
async def test_publish_to_no_clients_is_noop():
    hub = SSEHub()
    await hub.publish("u-nobody", {"kind": "msg"})  # must not raise


@pytest.mark.asyncio
async def test_broadcast_publishes_to_all_recipients():
    hub = SSEHub()
    c1 = hub.attach("u-1")
    c2 = hub.attach("u-2")
    await hub.broadcast(["u-1", "u-2"], {"kind": "msg", "text": "hi"})
    assert (await asyncio.wait_for(c1.queue.get(), 0.5))["text"] == "hi"
    assert (await asyncio.wait_for(c2.queue.get(), 0.5))["text"] == "hi"


@pytest.mark.asyncio
async def test_detach_stops_delivery():
    hub = SSEHub()
    client = hub.attach("u-1")
    hub.detach(client)
    await hub.publish("u-1", {"kind": "msg"})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client.queue.get(), 0.1)
